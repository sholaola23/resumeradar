"""Read-only Claude review of one pull request, run by resumeradar-claude-review.yml.

It calls the Claude API (Messages API) directly instead of the Claude Code
GitHub Action. Anthropic's monthly API credit on Shola's Max plan covers the
Claude API but not Claude Code, so this keeps reviews on that credit
(support.claude.com/en/articles/17154008, checked 19 Nov 2026).

Claude gets three read-only tools (list, read, search) confined to pr-head/
and .review/ in the workspace. It cannot run commands, write files, reach the
network or post anything. Its final text is written to REVIEW_OUT, and a later
workflow step checks it for secrets and posts it.

Sign-in is workload identity federation: the GitHub Actions OIDC token is
swapped for a short-lived Claude token, so no API key is stored. A fresh
GitHub token is fetched each time the SDK needs one.

Environment:
  ANTHROPIC_FEDERATION_RULE_ID, ANTHROPIC_ORGANIZATION_ID,
  ANTHROPIC_SERVICE_ACCOUNT_ID, ANTHROPIC_WORKSPACE_ID  Console identifiers
  ACTIONS_ID_TOKEN_REQUEST_URL, ACTIONS_ID_TOKEN_REQUEST_TOKEN  set by GitHub
  PR, BASE, HEAD  pull request number and commits
  SKILL  path to the review checklist (from the default branch)
  REVIEW_OUT  where to write the review text
"""

import fnmatch
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import anthropic
from anthropic import WorkloadIdentityCredentials

MODEL = "claude-opus-5-5"
MAX_TURNS = 60
WORKSPACE = Path.cwd().resolve()
ALLOWED_ROOTS = [(WORKSPACE / "pr-head").resolve(), (WORKSPACE / ".review").resolve()]
MAX_READ_LINES = 2000
MAX_TOOL_CHARS = 60_000
MAX_SEARCH_HITS = 200

RUNTIME_NOTE = """\
How this review runs (this note overrides anything in the checklist about tools):
- You run on the Claude API with three read-only tools: list_files, read_file and search. They only see `pr-head/` (the change's code at the head commit) and `.review/` (the diff, file list, commits, PR text and earlier reviews). Paths are relative to the workspace, for example `pr-head/app.py` or `.review/diff.patch`.
- There are no subagents. Where the checklist says to run items or verify findings as subagents, do that work yourself with the tools, in the same order: find, then verify each candidate against the code, then write.
- Start by reading `.review/files.txt`, `.review/diff.patch`, `.review/commits.txt`, `.review/previous.txt` and `.review/pr-context.json`.
- Your final message is the review comment. End it with the verdict line exactly as the checklist says, as its own last line, with nothing after it (no code fence, no bold).
"""

TOOLS = [
    {
        "name": "list_files",
        "description": "List files under a directory in pr-head/ or .review/, recursively. Returns workspace-relative paths, one per line.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory, e.g. pr-head or pr-head/backend"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": f"Read a text file in pr-head/ or .review/. Returns numbered lines. At most {MAX_READ_LINES} lines per call; use offset to page.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, e.g. pr-head/app.py"},
                "offset": {"type": "integer", "description": "First line to return, 1-based. Use 1 to start."},
            },
            "required": ["path", "offset"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search",
        "description": f"Search file contents with a Python regular expression under a directory in pr-head/ or .review/. Returns path:line: text, at most {MAX_SEARCH_HITS} hits.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regular expression"},
                "path": {"type": "string", "description": "Directory or file to search, e.g. pr-head"},
                "glob": {"type": "string", "description": "Filename glob filter, e.g. *.py; use * for all files"},
            },
            "required": ["pattern", "path", "glob"],
            "additionalProperties": False,
        },
    },
]


def github_oidc_token() -> str:
    """Fetch a fresh GitHub Actions OIDC token for the Anthropic audience."""
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=https://api.anthropic.com"
    req = urllib.request.Request(
        url, headers={"Authorization": "bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["value"]


def confine(raw: str) -> Path:
    """Resolve a workspace-relative path and refuse anything outside the allowed roots."""
    path = (WORKSPACE / raw).resolve()
    for root in ALLOWED_ROOTS:
        if path == root or root in path.parents:
            if ".git" in path.relative_to(root).parts:
                raise PermissionError(f"{raw}: git metadata is not readable")
            return path
    raise PermissionError(f"{raw}: outside pr-head/ and .review/")


def rel(path: Path) -> str:
    return str(path.relative_to(WORKSPACE))


def walk(base: Path):
    if base.is_file():
        yield base
        return
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                confine(rel(p))
            except PermissionError:
                continue
            yield p


def tool_list_files(path: str) -> str:
    base = confine(path)
    if not base.exists():
        return f"{path}: not found"
    return "\n".join(rel(p) for p in walk(base)) or "(empty)"


def tool_read_file(path: str, offset: int) -> str:
    p = confine(path)
    if not p.is_file():
        return f"{path}: not a file"
    data = p.read_bytes()
    if b"\0" in data[:8192]:
        return f"{path}: binary file, not shown"
    lines = data.decode("utf-8", errors="replace").splitlines()
    start = max(offset, 1)
    chunk = lines[start - 1 : start - 1 + MAX_READ_LINES]
    out = "\n".join(f"{start + i}\t{line}" for i, line in enumerate(chunk))
    end = start - 1 + len(chunk)
    if end < len(lines):
        out += f"\n[lines {start}-{end} of {len(lines)}; call again with offset={end + 1}]"
    return out or f"{path}: no lines at offset {offset} (file has {len(lines)} lines)"


def tool_search(pattern: str, path: str, glob: str) -> str:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"bad pattern: {exc}"
    base = confine(path)
    hits = []
    for p in walk(base):
        if not fnmatch.fnmatch(p.name, glob or "*"):
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel(p)}:{n}: {line[:300]}")
                if len(hits) >= MAX_SEARCH_HITS:
                    return "\n".join(hits) + f"\n[stopped at {MAX_SEARCH_HITS} hits]"
    return "\n".join(hits) or "no matches"


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    try:
        if name == "list_files":
            out = tool_list_files(args["path"])
        elif name == "read_file":
            out = tool_read_file(args["path"], int(args["offset"]))
        elif name == "search":
            out = tool_search(args["pattern"], args["path"], args["glob"])
        else:
            return f"unknown tool {name}", True
    except (PermissionError, KeyError, ValueError, OSError) as exc:
        return str(exc), True
    if len(out) > MAX_TOOL_CHARS:
        out = out[:MAX_TOOL_CHARS] + "\n[output cut at 60,000 characters; narrow the request]"
    return out, False


def load_skill(path: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


def main() -> int:
    out_path = Path(os.environ["REVIEW_OUT"])
    out_path.write_text("", encoding="utf-8")
    client = anthropic.Anthropic(
        credentials=WorkloadIdentityCredentials(
            identity_token_provider=github_oidc_token,
            federation_rule_id=os.environ["ANTHROPIC_FEDERATION_RULE_ID"],
            organization_id=os.environ["ANTHROPIC_ORGANIZATION_ID"],
            service_account_id=os.environ["ANTHROPIC_SERVICE_ACCOUNT_ID"],
            workspace_id=os.environ["ANTHROPIC_WORKSPACE_ID"],
        ),
        timeout=900,
    )
    system = load_skill(os.environ["SKILL"]) + "\n\n" + RUNTIME_NOTE
    messages = [
        {
            "role": "user",
            "content": f"Review this change. pr={os.environ['PR']} base={os.environ['BASE']} head={os.environ['HEAD']}",
        }
    ]
    usage = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    final = None
    for turn in range(1, MAX_TURNS + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=system,
            tools=TOOLS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            cache_control={"type": "ephemeral"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
        u = message.usage
        usage["input"] += u.input_tokens or 0
        usage["cache_read"] += u.cache_read_input_tokens or 0
        usage["cache_write"] += u.cache_creation_input_tokens or 0
        usage["output"] += u.output_tokens or 0
        messages.append({"role": "assistant", "content": message.content})
        if message.stop_reason == "tool_use":
            results = []
            for block in message.content:
                if block.type == "tool_use":
                    text, is_error = run_tool(block.name, dict(block.input))
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error}
                    )
            messages.append({"role": "user", "content": results})
            continue
        final = message
        break
    print(f"turns={turn} usage={json.dumps(usage)}", file=sys.stderr)
    if final is None:
        print(f"stopped after {MAX_TURNS} turns without a final answer", file=sys.stderr)
        return 0
    print(f"stop_reason={final.stop_reason} model={final.model}", file=sys.stderr)
    if final.stop_reason == "refusal":
        return 0
    text = "\n\n".join(b.text for b in final.content if b.type == "text").strip()
    out_path.write_text(text + "\n" if text else "", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

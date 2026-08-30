# data/

Generated artifacts read by the web app at request time.

## hiring_signal.json

Written by `scripts/refresh_hiring_signal.py`, served by
`backend/hiring_signal.py` on the role pages.

**Do not commit fixture data.** Running the refresh script with `--mock`
produces placeholder entries (kubernetes/terraform/jenkins repeated across
every role) purely to test the wiring. That data is nonsense for most roles
and would appear on 15 public pages as claims about the job market.

Before committing this file, confirm:

- it was produced by a real run, not `--mock`
- `source` is `grok live x search`
- the entries are plausible for each role (a UX designer's list should not look
  like a DevOps engineer's)
- `generated_at` is recent — `backend/hiring_signal.py` stops rendering the
  block once the artifact is older than 14 days

The file is intentionally not gitignored: the weekly diff is the review gate
for AI-derived claims that go on public pages, so it belongs in version
control where a human reads it before it ships.

When the file is absent, `get_signal()` returns `None` and the role pages
render without the block. That is the safe default and the current state.

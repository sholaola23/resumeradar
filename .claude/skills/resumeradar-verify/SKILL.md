---
name: resumeradar-verify
description: Start ResumeRadar locally on sample data with every outside service faked, walk the changed flow in a browser at 375px and 1280px with axe, and report what was seen. Run before every commit handed over.
---

# ResumeRadar verify

The smoke test for any change. It starts the app on this machine with Claude, Resend and Beehiiv faked and a private Redis, so it spends no AI credit and sends no email. Then it walks the flows in `docs/feature-map.md` the way a user would. CI runs the same check on every PR ("User check" job).

If it is slow or flaky, fix that first. Never retry or skip a failing flow until it passes.

## 1. Set up (once per machine)

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd tests/user-check && bun install --frozen-lockfile
bun x playwright install chromium   # skip in a Claude cloud session: Chromium is already there
```

`redis-server` must be installed (`apt-get install redis-server` or `brew install redis`). Never set `CV_BUILDER_ENABLED`; the launcher removes it anyway.

## 2. Walk the changed flow

Pick the rows in `docs/feature-map.md` your change touches and run their tests by name, from `tests/user-check`:

```sh
bun x playwright test -g "Cover letter"          # one feature (a describe block)
bun x playwright test -g "email the report|Share" # several (a case-sensitive regex)
bun x playwright test                            # everything, about 1.5 minutes
```

Playwright starts `serve.py` itself on port 5055 (change it with `USER_CHECK_PORT`) and stops it after.

To keep a screenshot of every checked page at both widths, add `USER_CHECK_SCREENSHOTS=shots`. In a cloud session, save them under `/mnt/project-files/<task>/` so QA can see them.

To look around by hand, run `../../.venv/bin/python serve.py 5055` and open `http://127.0.0.1:5055`. The fake inbox is at `/__user-check/outbox`. These `/__user-check/` routes exist only in the launcher, never in production.

## 3. If the change adds or changes a flow

- Add or update its test in `flows.spec.ts`, inside the `test.describe` for that feature, and name the test in the feature map row's "Covered by" column.
- Update the row in `docs/feature-map.md` in the same commit.
- If the flow calls a new outside service, fake it in `serve.py`. The network guard fails the check on any connection off this machine, so an unfaked service shows up as a red run.
- Prove the new test by breaking the flow once and watching it go red.

## 4. Report what you saw

Paste the last lines of the run (`N passed`), name the flows walked, and list anything that is PENDING in the feature map for those flows. A failure prints the step, the axe rule or the console error, and leaves a screenshot under `test-results/`.

## What it can't check

Real Claude replies, real email delivery, real Beehiiv sign-ups, Cloudflare visitor addresses and anything on Render. The feature map marks these PENDING.

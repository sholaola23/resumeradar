# One payment per generated CV

A payment or bundle credit unlocks the immutable generated CV. PDF, Word,
combined exports and retries do not consume more credits. Existing access
windows remain: 72 hours for a single purchase; remaining plan time for bundles.
A newly generated CV has a new token and needs its own payment or credit.

Bundle debit and entitlement creation execute together in Redis Lua. Repeats
with different request IDs still charge once. Repeats never extend expiry.
Bundle-funded entitlements retain their bundle owner so deleting a refunded
bundle also blocks its downloads. Existing legacy paid flags remain supported
until their current expiry. The three-download cap is removed; endpoint rate
limits remain. Single-purchase paid flags now match the 72-hour data window.

The payment return shows download status in the visible preview step, with
free PDF/Word buttons and same-tab recovery. Server checks remain authoritative;
local recovery data never grants access. New checkout attempts for an already
paid CV return a download instead of creating another payment session.

## Quality benchmark

`tests/recommendation_benchmark.py` contains 12 hand-labelled synthetic scenarios:
cloud gaps, tool alternatives, career change, skill denial, negative outcomes,
punctuated technical names, optional skills, excluded requirements, data gaps,
stemming errors, unsupported nontechnical work, and international names.

An optional private `cv_content.py` adds two synthetic job specifications tested
against one real CV. Only experience/capability sections are read, using literal
parsing; the source is never executed. No private CV content or contact fields
are committed. Multiple roles for one CV do not count as multiple applicants.

Initial result: 10/14 cases passed. The failures exposed terminal-list alternative
handling and missing Tableau/Spark vocabulary. After correction: 14/14 passed.
This is a development regression benchmark, not a held-out or representative
accuracy study. It checks expected priority labels, source grounding, exclusion
of supported skills/alternatives, and abstention for unsupported vocabulary.
The optional `--live-staging` mode sends only three synthetic cases for manual
review of AI advice; it never sends the private CV.

Run the benchmark with:

```sh
.venv/bin/python tests/recommendation_benchmark.py
.venv/bin/python -m unittest tests.test_repeat_downloads
```

Payment regressions use a disposable Redis server on a private Unix socket:
concurrent unlocks, exhausted bundles, new CVs, expiry preservation, invalid CVs,
more than three downloads, format changes, refund revocation, and duplicate
checkout avoidance. No real billing accounts are used by these tests.

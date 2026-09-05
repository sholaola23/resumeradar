# Free scan and download polish

Approved scope, 5 September 2026: make the free scan useful without paying or
subscribing, and clarify the existing purchased-CV download experience.

The homepage leads with the free scan. All results and report actions are shown
immediately, including when an old `gate=modal` URL is used. The newsletter is
optional and follows the complete report. The paid rewrite offer appears once,
after the free edit/rescan action; the mobile sticky action now offers a free rescan.

The report leads with three writing improvements and job-backed requirements.
It distinguishes absent evidence from skills the person does not have. Rescanning
keeps the job description and compares keyword coverage and matched terms only
when the job hash and scoring version agree. The comparison baseline is kept in
page memory, not as another stored copy of the CV. Starting a different job clears
that baseline. Keyword changes can be expanded rather than overwhelming the score.

Single and bundle purchases share the completion screen. PDF is primary, Word is
secondary, and ZIP is optional. The server provides remaining access seconds from
the CV, paid entitlement and owning bundle expiry, where available. Downloads do
not extend those deadlines. An unavailable deadline is not replaced by a guessed
date. Expired access points users to saved downloads or emailed copies; recovery
also keeps the chosen template. Checkout explains the single-CV 72-hour window,
and bundle quantities are labelled CV credits.

Verification: 36 Python tests, four JavaScript tests and 464 offline QA checks.
Local Chrome checks covered complete free results without signup, same-job rescan
comparison, purchased completion/deadline, and expired access. The local fixture
used synthetic data and disposable Redis, without service credentials. A scoped
500px-wide Chrome window capture checked the entry page and comparison layout;
this is not a substitute for testing on physical mobile devices.

Actual CV previews inside template selection remain a later iteration, as proposed.

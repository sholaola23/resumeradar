# Approved product improvements — 5 September 2026

Implemented in the existing Flask and vanilla JavaScript application.

- Custom match estimate with an insufficient-evidence state; action verbs no longer boost the match score.
- Explicit skill denials excluded without discarding achievements such as “without downtime”; international names retain formatting points.
- Recommendations use source sentences, requirement headings, and explicit tool alternatives.
- Full CV preview before paid export; edits use regeneration so preview and export stay consistent.
- AI Pro labeling; bundles and writing tools are secondary expandable choices.
- Direct homepage scan action and testimonials below the scanner.
- Same-job, same-scoring-version history comparisons; absent scores stay absent in reports.
- Anonymous journey attribution and 90-day analytics retention; payment/download truth stays on the server.

Validation: 28 Python regression tests, 3 JavaScript regression tests, 460 existing offline QA checks, syntax checks, and local browser checks (390px mobile preview and purchase flow).
Browser builder checks use synthetic AI output; they do not establish live AI quality or payment-provider behavior.

Limitations: deterministic vocabulary and sentence cues remain heuristic. Negation handling recognizes explicit lexical patterns; complex phrasing may need manual review. Alternative matching requires explicit lists. Before/after bullet comparison is available when structured original manual input exists. No new pricing, infrastructure, or production deployment was performed.

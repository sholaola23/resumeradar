"""
Shared public wording for ResumeRadar.

One source for the lines that appear on the site, in the emailed report and
in the PDF, so they cannot drift apart again. Keep these ASCII-only: the PDF
report uses a core font that only covers Latin-1.

PRIVACY_LINE describes what the code does today. If the code changes (file
clean-up in app.py scan_resume, the AI cache TTL in backend/ai_cache.py, or a
new place CV text is sent), this line and templates/privacy.html must change
with it, and any change to what it promises needs the owner's approval.
"""

STRAPLINE = "Make your experience clear."

PRIVACY_LINE = (
    "Your CV file is deleted as soon as it is read. "
    "Your CV text is sent to our AI provider to write your suggestions "
    "and is not saved by ResumeRadar. "
    "Results are cached for up to one hour, and nothing is sold."
)

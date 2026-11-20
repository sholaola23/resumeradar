"""Error text that is safe to write to the server logs.

An exception's message can quote the input that caused it, and on the scan
path that input is the user's CV or job description. The site promises that
"our server logs never include your CV text or the AI reply", so the scan,
email, PDF and AI handlers log only the error's type and, for API errors,
its HTTP status.
"""


def describe(error):
    """Return e.g. 'APIStatusError (status 429)' or 'KeyError'."""
    name = type(error).__name__
    status = getattr(error, 'status_code', None)
    return f"{name} (status {status})" if isinstance(status, int) else name

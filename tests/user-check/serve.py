"""Start ResumeRadar locally for the user check, with every outside service faked.

    python tests/user-check/serve.py [port]

This file is for tests only. Production runs `gunicorn app:app` (Procfile,
render.yaml), which never imports it, so nothing here can switch on in
production, whatever the environment variables say.

What it fakes, before the app is imported:
- Claude: backend.ai_analyzer.make_client returns FakeAnthropic, which gives
  canned replies. The real budget, cache and per-IP limit code still runs.
- Resend: resend.Emails.send saves each email to OUTBOX instead of sending.
- Beehiiv: requests.post to api.beehiiv.com is recorded in BEEHIIV, not sent.
- Redis: a private redis-server on 127.0.0.1 with no disk files, stopped
  when this process ends.
- Network guard: any connection that is not to this machine is refused and
  recorded in BLOCKED. The check fails if BLOCKED is not empty.

It adds routes under /__user-check/ that only exist in this process: the
outbox, the Beehiiv calls, the blocked list, a reset between tests and a
sample DOCX CV.

The sample CV and job description are made up (tests/user-check/fixtures.json).
Nothing here logs CV text.
"""

import atexit
import io
import ipaddress
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv('USER_CHECK_PORT', '5055'))

OUTBOX = []
BEEHIIV = []
BLOCKED = []
_lock = threading.Lock()


# ---------------------------------------------------------------- network guard

def _is_local(host):
    if host in ('localhost', '', None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _block(target):
    with _lock:
        BLOCKED.append(str(target))
    raise ConnectionRefusedError(f'user check: outside connection blocked ({target})')


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        _block(address)
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        _block(address)
    return _real_connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if isinstance(host, bytes):
        host = host.decode()
    if not _is_local(host):
        _block(host)
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.getaddrinfo = _guarded_getaddrinfo


# ---------------------------------------------------------------- private Redis

def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_redis():
    binary = shutil.which('redis-server')
    if not binary:
        sys.exit('user check: redis-server is not installed (apt-get install redis-server)')
    workdir = tempfile.mkdtemp(prefix='rr-user-check-redis-')
    port = _free_port()
    proc = subprocess.Popen(
        [binary, '--port', str(port), '--bind', '127.0.0.1', '--save', '', '--appendonly', 'no',
         '--dir', workdir, '--protected-mode', 'yes'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def _stop():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(workdir, ignore_errors=True)

    atexit.register(_stop)
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                return f'redis://127.0.0.1:{port}/0'
        except OSError:
            time.sleep(0.05)
    _stop()
    sys.exit('user check: redis-server did not start')


# ---------------------------------------------------------------- environment

# The builder must stay off, so never inherit a value for it.
os.environ.pop('CV_BUILDER_ENABLED', None)
# No real keys may reach this process. These dummies only satisfy "is it set?"
# checks; every service they would unlock is faked below.
os.environ.update({
    'ANTHROPIC_API_KEY': 'fake-user-check-key',
    'RESEND_API_KEY': 'fake-user-check-key',
    'BEEHIIV_API_KEY': 'fake-user-check-key',
    'BEEHIIV_PUBLICATION_ID': 'pub_fake_user_check',
    'FLASK_SECRET_KEY': secrets.token_hex(32),
    'AUDIT_HMAC_SECRET': secrets.token_hex(32),
    'PUBLIC_BASE_URL': f'http://127.0.0.1:{PORT}',
    'FLASK_ENV': 'production',
    'REDIS_URL': _start_redis(),
})
for name in ('STRIPE_SECRET_KEY', 'STRIPE_PRICE_ID', 'PAYSTACK_SECRET_KEY', 'RENDER'):
    os.environ.pop(name, None)

sys.path.insert(0, REPO)
os.chdir(REPO)


# ---------------------------------------------------------------- fake Claude

with open(os.path.join(HERE, 'fixtures.json'), encoding='utf-8') as fh:
    FIXTURES = json.load(fh)

SCAN_REPLY = json.dumps(FIXTURES['fake_ai']['scan'])


class _Message:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(type='text', text=text)]
        self.usage = types.SimpleNamespace(input_tokens=1200, output_tokens=300)


class _Messages:
    def create(self, model=None, max_tokens=None, messages=None, **_):
        prompt = messages[0]['content'] if messages else ''
        if 'cover_letter_points' in prompt:
            return _Message(SCAN_REPLY)
        if 'cover letter' in prompt.lower():
            return _Message(FIXTURES['fake_ai']['cover_letter'])
        if 'bullet' in prompt.lower():
            return _Message(FIXTURES['fake_ai']['bullet'])
        return _Message(FIXTURES['fake_ai']['summary'])


class FakeAnthropic:
    def __init__(self, *_, **__):
        self.messages = _Messages()


from backend import ai_analyzer  # noqa: E402

ai_analyzer.make_client = lambda api_key: FakeAnthropic()
ai_analyzer.Anthropic = FakeAnthropic


# ---------------------------------------------------------------- fake Resend

import resend  # noqa: E402


def _fake_resend_send(params, *_, **__):
    with _lock:
        OUTBOX.append({
            'to': list(params.get('to') or []),
            'subject': params.get('subject', ''),
            'text': params.get('text', ''),
            'html': params.get('html', ''),
            'attachments': [a.get('filename') for a in params.get('attachments') or []],
        })
    return {'id': f'fake-{len(OUTBOX)}'}


resend.Emails.send = staticmethod(_fake_resend_send)


# ---------------------------------------------------------------- fake Beehiiv

import requests  # noqa: E402

_real_post = requests.post


def _fake_post(url, *args, **kwargs):
    if 'api.beehiiv.com' in str(url):
        with _lock:
            BEEHIIV.append({'url': url, 'email': (kwargs.get('json') or {}).get('email')})
        return types.SimpleNamespace(status_code=201, text='{}', json=lambda: {})
    return _real_post(url, *args, **kwargs)


requests.post = _fake_post


# ---------------------------------------------------------------- the app

import app as resumeradar  # noqa: E402
from flask import jsonify, send_file  # noqa: E402

flask_app = resumeradar.app


@flask_app.get('/__user-check/outbox')
def _outbox():
    with _lock:
        return jsonify(OUTBOX)


@flask_app.get('/__user-check/beehiiv')
def _beehiiv():
    with _lock:
        return jsonify(BEEHIIV)


@flask_app.get('/__user-check/blocked')
def _blocked():
    with _lock:
        return jsonify(BLOCKED)


@flask_app.post('/__user-check/reset')
def _reset():
    """Each test starts as a new visitor: empty Redis, rate limits and fakes."""
    resumeradar._redis_client.flushdb()
    resumeradar.limiter.reset()
    with _lock:
        OUTBOX.clear()
        BEEHIIV.clear()
        BLOCKED.clear()
    return jsonify({'reset': True})


@flask_app.get('/__user-check/sample-cv.docx')
def _sample_docx():
    from docx import Document
    doc = Document()
    for line in FIXTURES['cv_text'].split('\n'):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='sample_cv.docx',
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# The user check's own routes skip the app's rate limits.
for _name in ('_outbox', '_beehiiv', '_blocked', '_reset', '_sample_docx'):
    resumeradar.limiter.exempt(flask_app.view_functions[_name])


if __name__ == '__main__':
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)  # no per-request lines
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print(f'user check server on http://127.0.0.1:{PORT} (all outside services faked)', flush=True)
    flask_app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False, threaded=True)

"""The user check's fakes (tests/user-check/serve.py) can never run in production.

Production starts `gunicorn app:app`. The fakes live only in serve.py, which
nothing in the app imports, so no environment variable can switch them on.
"""
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    from app import app  # noqa: E402

PROD_START = re.compile(r'gunicorn app:app\b')


def _read(path):
    with open(os.path.join(REPO, path), encoding='utf-8') as fh:
        return fh.read()


class UserCheckIsolationTest(unittest.TestCase):
    def test_production_starts_the_plain_app(self):
        self.assertRegex(_read('Procfile'), PROD_START)
        self.assertRegex(_read('render.yaml'), PROD_START)
        for path in ('Procfile', 'render.yaml'):
            self.assertNotIn('user-check', _read(path), path)
            self.assertNotIn('serve.py', _read(path), path)

    def test_app_code_never_loads_the_fakes(self):
        files = ['app.py'] + [
            os.path.join('backend', name)
            for name in os.listdir(os.path.join(REPO, 'backend')) if name.endswith('.py')
        ]
        for path in files:
            text = _read(path)
            self.assertNotIn('user-check', text, path)
            self.assertNotIn('user_check', text, path)
            self.assertNotIn('FakeAnthropic', text, path)

    def test_the_plain_app_has_no_user_check_routes(self):
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertFalse([r for r in rules if r.startswith('/__user-check')], rules)
        with app.test_client() as client:
            self.assertEqual(client.get('/__user-check/outbox').status_code, 404)


# Loads serve.py's setup (fakes, guard, private Redis) without starting the
# server, then tries an outside call through a proxy on this machine.
_PROXY_PROBE = r"""
import runpy, sys
path = sys.argv[1]
sys.argv = [path, '5099']
mod = runpy.run_path(path, run_name='user_check_probe')
import requests
try:
    requests.get('https://example.com/', timeout=5)
    print('REACHED')
except Exception:
    pass
print('BLOCKED', len(mod['BLOCKED']))
"""


@unittest.skipUnless(shutil.which('redis-server'), 'serve.py needs redis-server')
class UserCheckNetworkGuardTest(unittest.TestCase):
    def test_a_local_proxy_cannot_carry_outside_calls_past_the_guard(self):
        env = dict(os.environ, HTTPS_PROXY='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9',
                   HTTP_PROXY='http://127.0.0.1:9', NO_PROXY='', no_proxy='')
        out = subprocess.run(
            [sys.executable, '-c', _PROXY_PROBE, os.path.join(REPO, 'tests', 'user-check', 'serve.py')],
            env=env, capture_output=True, text=True, timeout=60, cwd=REPO,
        )
        out = out.stdout + out.stderr[-2000:]
        self.assertNotIn('REACHED', out)
        self.assertRegex(out, r'BLOCKED [1-9]')


if __name__ == '__main__':
    unittest.main()

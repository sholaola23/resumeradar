"""The "Email me this report" link beside the score opens the same dialog as the Email report button."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ScoreEmailLinkTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
        self.js = (ROOT / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')

    def test_link_sits_in_the_score_card(self):
        card = self.html[self.html.index('id="scoreCard"'):self.html.index('id="aiRestNote"')]
        self.assertIn('id="scoreEmailBtn">Email me this report</button>', card)

    def test_both_buttons_open_the_same_dialog(self):
        self.assertIn("emailReportBtn.addEventListener('click', openEmailModal)", self.js)
        self.assertRegex(self.js, r"scoreEmailBtn\.addEventListener\('click', openEmailModal\)")
        body = re.search(r'function openEmailModal\(\) \{(.*?)\n    \}', self.js, re.S).group(1)
        self.assertIn('modalReturnFocus = document.activeElement', body)
        self.assertIn("emailModal.style.display = 'flex'", body)


if __name__ == '__main__':
    unittest.main()

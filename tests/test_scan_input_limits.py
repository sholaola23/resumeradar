"""/api/scan rejects oversized text before the keyword engine runs."""
import io
import os
import unittest
from unittest.mock import patch

from docx import Document

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as product

JD = "We need Python AWS Docker Kubernetes experience, required for this role. " * 10
CV = "Built Python services on AWS with Docker and Kubernetes for five years. " * 10


def _docx_bytes(text):
    doc = Document()
    for i in range(0, len(text), 2000):
        doc.add_paragraph(text[i:i + 2000])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class ScanInputLimitTests(unittest.TestCase):
    def setUp(self):
        product.app.config['TESTING'] = True
        product.limiter.enabled = False
        self.client = product.app.test_client()

    def tearDown(self):
        product.limiter.enabled = True

    def _scan(self, data, **kw):
        return self.client.post('/api/scan', data=data, **kw)

    def test_oversized_job_description_rejected_fast(self):
        big = "Python AWS Docker required. " * 20_000  # ~560k chars
        with patch.object(product, 'extract_keywords_from_text') as kw:
            resp = self._scan({'job_description': big, 'resume_text': CV})
            kw.assert_not_called()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('job description is too long', resp.get_json()['error'])

    def test_oversized_pasted_cv_rejected(self):
        big = "Python " * (product.MAX_RESUME_CHARS // 7 + 10)
        with patch.object(product, 'extract_keywords_from_text') as kw:
            resp = self._scan({'job_description': JD, 'resume_text': big})
            kw.assert_not_called()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('CV text is too long', resp.get_json()['error'])

    def test_oversized_uploaded_cv_rejected_and_file_removed(self):
        text = "Python AWS Docker Kubernetes delivery. " * 2000  # ~78k chars
        before = set(os.listdir(product.UPLOAD_FOLDER))
        with patch.object(product, 'extract_keywords_from_text') as kw:
            resp = self._scan(
                {'job_description': JD,
                 'resume_file': (io.BytesIO(_docx_bytes(text)), 'cv.docx')},
                content_type='multipart/form-data')
            kw.assert_not_called()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('more text than a CV', resp.get_json()['error'])
        self.assertEqual(set(os.listdir(product.UPLOAD_FOLDER)), before)

    def test_inputs_at_the_limit_still_scan(self):
        jd = (JD * 100)[:product.MAX_JOB_DESCRIPTION_CHARS]
        cv = (CV * 200)[:product.MAX_RESUME_CHARS]
        with patch.object(product, 'get_ai_suggestions', return_value={}):
            resp = self._scan({'job_description': jd, 'resume_text': cv})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:300])
        self.assertTrue(resp.get_json()['success'])


if __name__ == '__main__':
    unittest.main()

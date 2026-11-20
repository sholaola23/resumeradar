"""PDF parsing stops early on files far heavier than a CV (QA on PR 34)."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fpdf import FPDF
from pypdf import PdfReader

from backend import resume_parser

LINE = "Python AWS Docker Kubernetes Terraform delivery leadership " * 6


def _write(pdf):
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(bytes(pdf.output()))
    return path


def _dense_pdf(lines_per_page, pages):
    """QA's repro: tiny overlapping text, small file, huge page content."""
    p = FPDF()
    p.set_auto_page_break(False)
    p.set_font("Helvetica", size=1)
    for _ in range(pages):
        p.add_page()
        for i in range(lines_per_page):
            p.text(5, 5 + (i % 280), LINE)
    return _write(p)


def _normal_cv_pdf():
    p = FPDF()
    p.set_auto_page_break(True, 10)
    p.set_font("Helvetica", size=10)
    for _ in range(3):
        p.add_page()
        for _ in range(50):
            p.cell(0, 5, "Led Python services on AWS with Docker, cutting costs 20%.",
                   new_x="LMARGIN", new_y="NEXT")
    return _write(p)


class PdfBudgetTests(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            os.remove(path)

    def _path(self, path):
        self.paths.append(path)
        return path

    def test_qa_repro_rejected_quickly(self):
        # 400 lines x 50 pages: ~0.13MB file, ~7.6MB of page content.
        path = self._path(_dense_pdf(400, 50))
        start = time.time()
        text, err = resume_parser.extract_text_from_pdf(path)
        self.assertLess(time.time() - start, 2)
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_text_budget_stops_extraction(self):
        # Content check lifted, so the running text count must catch it.
        path = self._path(_dense_pdf(400, 50))
        with patch.object(resume_parser, "MAX_PDF_CONTENT_BYTES", 10**9):
            start = time.time()
            text, err = resume_parser.extract_text_from_pdf(path)
        self.assertLess(time.time() - start, 2)
        self.assertIsNone(text)
        self.assertIn("more text than a CV", err)

    def test_time_budget_stops_extraction(self):
        path = self._path(_normal_cv_pdf())
        with patch.object(resume_parser, "PDF_EXTRACT_SECONDS", -1):
            text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_normal_cv_text_unchanged(self):
        path = self._path(_normal_cv_pdf())
        text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(err)
        plain = "\n".join(pg.extract_text() for pg in PdfReader(path).pages)
        self.assertEqual(text, resume_parser.clean_text(plain))


if __name__ == "__main__":
    unittest.main()

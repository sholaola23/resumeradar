"""PDF parsing stops early on files far heavier than a CV (QA on PR 34)."""
import os
import tempfile
import zlib
import unittest
from unittest.mock import patch

from fpdf import FPDF
from pypdf import PageObject, PdfReader

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


def _nested_form_pdf(inner_mb, fm1_resources=b"/Resources << /XObject << /Fm2 5 0 R >> >>",
                     extra_objs=()):
    """Grok's repro on PR 34: the page draws form Fm1, and Fm1 draws Fm2
    through its own resources, so a page-level count never sees Fm2. Fm2 is
    megabytes of line drawing that compress to a few KB."""
    inner = zlib.compress(b"0 0 m 1 1 l S\n" * (inner_mb * 1024 * 1024 // 14), 9)
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /XObject << /Fm1 4 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] "
        + fm1_resources + b" /Length 8 >>\n"
        b"stream\n/Fm2 Do\nendstream",
        # pypdf skips a form with no resources, so Fm2 carries a font.
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Filter /FlateDecode "
        b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
        b"/BaseFont /Helvetica >> >> >> /Length %d >>\nstream\n" % len(inner) + inner + b"\nendstream",
        b"<< /Length 8 >>\nstream\n/Fm1 Do\nendstream",
        *extra_objs,
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, xref)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(out)
    return path


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

    # These assert the expensive work was skipped or cut short, not wall-clock
    # time, so a slow CI runner cannot make them flaky (Claude review, PR 34).
    def _extract_counting_pages(self, path):
        real = PageObject.extract_text
        with patch.object(PageObject, "extract_text", autospec=True,
                          side_effect=real) as calls:
            text, err = resume_parser.extract_text_from_pdf(path)
        return text, err, calls.call_count

    def test_qa_repro_rejected_quickly(self):
        # 400 lines x 50 pages: ~0.13MB file, ~7.6MB of page content.
        path = self._path(_dense_pdf(400, 50))
        text, err, pages_read = self._extract_counting_pages(path)
        self.assertEqual(pages_read, 0)  # rejected before extraction
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_text_budget_stops_extraction(self):
        # Content check lifted, so the running text count must catch it.
        path = self._path(_dense_pdf(400, 50))
        with patch.object(resume_parser, "MAX_PDF_CONTENT_BYTES", 10**9):
            text, err, pages_read = self._extract_counting_pages(path)
        self.assertLess(pages_read, 50)  # stopped part way through
        self.assertIsNone(text)
        self.assertIn("more text than a CV", err)

    def test_time_budget_stops_extraction(self):
        path = self._path(_normal_cv_pdf())
        with patch.object(resume_parser, "PDF_EXTRACT_SECONDS", -1):
            text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_nested_form_counted_against_content_cap(self):
        path = self._path(_nested_form_pdf(40))
        self.assertLess(os.path.getsize(path), 1024 * 1024)
        text, err, pages_read = self._extract_counting_pages(path)
        self.assertEqual(pages_read, 0)  # rejected before extraction
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_nested_form_via_parent_resources_counted(self):
        # Fm1 has no /Resources of its own but borrows them through /Parent,
        # which pypdf follows when it draws Fm1 (Claude review on PR 45).
        path = self._path(_nested_form_pdf(
            40, fm1_resources=b"/Parent 7 0 R",
            extra_objs=(b"<< /Resources << /XObject << /Fm2 5 0 R >> >> >>",)))
        text, err, pages_read = self._extract_counting_pages(path)
        self.assertEqual(pages_read, 0)  # rejected before extraction
        self.assertIsNone(text)
        self.assertIn("more complex than we can process", err)

    def test_form_parent_cycle_rejected(self):
        # Fm1 is its own /Parent and has no /Resources: must not hang.
        path = self._path(_nested_form_pdf(1, fm1_resources=b"/Parent 4 0 R"))
        text, err, pages_read = self._extract_counting_pages(path)
        self.assertEqual(pages_read, 0)
        self.assertIsNone(text)
        self.assertIn("Could not read that PDF", err)

    def test_small_nested_form_still_parses(self):
        # A small nested form is under the cap: it must reach extraction
        # (graphics only, so the existing "empty" message comes back).
        path = self._path(_nested_form_pdf(1))
        text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertIn("empty", err)

    def test_time_budget_ignores_other_threads(self):
        # Under gunicorn's threads, wall-clock time keeps running while other
        # requests hold the GIL. Make the wall clock leap an hour on every
        # read: a wall-clock budget would trip, a CPU-time budget must not.
        real_time = resume_parser.time
        leaps = iter(range(0, 10**9, 3600))

        class LeapingClock:
            def __getattr__(self, name):
                return getattr(real_time, name)

            @staticmethod
            def monotonic():
                return float(next(leaps))

            time = perf_counter = monotonic

        path = self._path(_normal_cv_pdf())
        with patch.object(resume_parser, "time", LeapingClock()):
            text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(err)
        self.assertTrue(text)

    def test_normal_cv_text_unchanged(self):
        path = self._path(_normal_cv_pdf())
        text, err = resume_parser.extract_text_from_pdf(path)
        self.assertIsNone(err)
        plain = "\n".join(pg.extract_text() for pg in PdfReader(path).pages)
        self.assertEqual(text, resume_parser.clean_text(plain))


if __name__ == "__main__":
    unittest.main()

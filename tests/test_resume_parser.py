"""Tests for backend/resume_parser.py: file sniffing, DOCX safety checks,
PDF and DOCX extraction and the parse_resume entry point.

Files are built in a temporary folder for each test and deleted afterwards.
"""
import os
import struct
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO

from docx import Document
from fpdf import FPDF

from backend import resume_parser as parser

CV_LINE = "Jo Bloggs built Python services and led a team of five engineers"


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def path(self, name):
        return os.path.join(self._tmp.name, name)

    def write_bytes(self, name, data):
        path = self.path(name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def make_docx(self, paragraphs=(CV_LINE,), table=None):
        doc = Document()
        for text in paragraphs:
            doc.add_paragraph(text)
        if table:
            grid = doc.add_table(rows=len(table), cols=len(table[0]))
            for r, row in enumerate(table):
                for c, value in enumerate(row):
                    grid.cell(r, c).text = value
        path = self.path("cv.docx")
        doc.save(path)
        return path

    def make_pdf(self, pages=(CV_LINE,)):
        pdf = FPDF()
        pdf.set_font("Helvetica", size=12)
        for text in pages:
            pdf.add_page()
            if text:
                pdf.cell(0, 10, text)
        path = self.path("cv.pdf")
        pdf.output(path)
        return path

    def make_zip(self, members, compression=zipfile.ZIP_DEFLATED):
        path = self.path("cv.docx")
        with zipfile.ZipFile(path, "w", compression=compression) as zf:
            for name, data in members:
                zf.writestr(name, data)
        return path


class SniffTests(TempDirTestCase):
    def test_real_files_match_their_type(self):
        self.assertTrue(parser.sniff_matches(self.make_pdf(), "pdf"))
        self.assertTrue(parser.sniff_matches(self.make_docx(), "docx"))

    def test_pdf_header_may_follow_leading_bytes(self):
        path = self.write_bytes("cv.pdf", b"\x00" * 500 + b"%PDF-1.4 rest")
        self.assertTrue(parser.sniff_matches(path, "pdf"))

    def test_pdf_header_past_the_window_is_rejected(self):
        path = self.write_bytes("cv.pdf", b"\x00" * 1100 + b"%PDF-1.4 rest")
        self.assertFalse(parser.sniff_matches(path, "pdf"))

    def test_docx_magic_must_be_at_byte_zero(self):
        path = self.write_bytes("cv.docx", b" PK\x03\x04rest")
        self.assertFalse(parser.sniff_matches(path, "docx"))

    def test_renamed_file_is_rejected(self):
        self.assertFalse(parser.sniff_matches(self.make_pdf(), "docx"))
        self.assertFalse(parser.sniff_matches(self.make_docx(), "pdf"))

    def test_unknown_type_and_missing_file(self):
        self.assertFalse(parser.sniff_matches(self.make_pdf(), "txt"))
        self.assertFalse(parser.sniff_matches(self.path("missing.pdf"), "pdf"))


class DocxSafetyTests(TempDirTestCase):
    def test_real_docx_is_safe(self):
        self.assertEqual(parser._docx_zip_is_safe(self.make_docx()), (True, None))

    def test_too_many_entries(self):
        members = [(f"part{i}.xml", b"x") for i in range(parser.MAX_DOCX_ENTRIES + 1)]
        safe, message = parser._docx_zip_is_safe(self.make_zip(members, zipfile.ZIP_STORED))
        self.assertFalse(safe)
        self.assertIn("too many parts", message)

    def test_declared_size_over_the_limit(self):
        # Stored, so the ratio is 1 and the ratio check cannot catch it.
        members = [("word/document.xml", b"a" * (parser.MAX_DOCX_UNCOMPRESSED + 1))]
        safe, message = parser._docx_zip_is_safe(self.make_zip(members, zipfile.ZIP_STORED))
        self.assertFalse(safe)
        self.assertIn("expands to more than we can process", message)

    def test_compression_ratio_over_the_limit(self):
        safe, message = parser._docx_zip_is_safe(self.make_zip([("word/document.xml", b"\0" * 2_000_000)]))
        self.assertFalse(safe)
        self.assertIn("looks malformed", message)

    def test_unsupported_compression_method(self):
        path = self.make_zip([("word/document.xml", os.urandom(2000))], zipfile.ZIP_BZIP2)
        safe, message = parser._docx_zip_is_safe(path)
        self.assertFalse(safe)
        self.assertIn("unsupported compression method", message)

    def understate_sizes(self, path):
        """Rewrite every member's declared size to ten times its compressed
        size, so the archive passes the cheap stage-1 checks."""
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
        with open(path, "rb") as fh:
            data = bytearray(fh.read())
        for info in infos:
            fake = info.compress_size * 10
            struct.pack_into("<I", data, info.header_offset + 22, fake)
        offset = data.find(b"PK\x01\x02")
        for info in infos:
            struct.pack_into("<I", data, offset + 24, info.compress_size * 10)
            name_len, extra_len, comment_len = struct.unpack_from("<HHH", data, offset + 28)
            offset += 46 + name_len + extra_len + comment_len
        with open(path, "wb") as fh:
            fh.write(data)
        with zipfile.ZipFile(path) as zf:
            for info, original in zip(zf.infolist(), infos):
                self.assertEqual(info.file_size, original.compress_size * 10)

    def test_understated_sizes_are_caught_by_the_real_read(self):
        # Each member really expands to 6MB, 12MB in total, but the headers
        # claim far less. Stage 2 must count the real bytes and reject it.
        six_mb = b"\0" * (6 * 1024 * 1024)
        path = self.make_zip([("word/document.xml", six_mb), ("word/styles.xml", six_mb)])
        self.understate_sizes(path)
        safe, message = parser._docx_zip_is_safe(path)
        self.assertFalse(safe)
        self.assertIn("expands to more than we can process", message)

    def test_understated_single_member_is_still_rejected(self):
        # One member past the limit: zipfile stops at the raised size limit
        # and fails its CRC check, so the archive is rejected as invalid.
        path = self.make_zip([("word/document.xml", b"\0" * (parser.MAX_DOCX_UNCOMPRESSED + 1024 * 1024))])
        self.understate_sizes(path)
        safe, message = parser._docx_zip_is_safe(path)
        self.assertFalse(safe)
        self.assertIn("doesn't look like a valid DOCX", message)

    def test_not_a_zip(self):
        safe, message = parser._docx_zip_is_safe(self.write_bytes("cv.docx", b"PK\x03\x04 not really a zip"))
        self.assertFalse(safe)
        self.assertIn("doesn't look like a valid DOCX", message)


class DocxExtractionTests(TempDirTestCase):
    def test_paragraphs_and_tables_are_extracted(self):
        path = self.make_docx(paragraphs=(CV_LINE, "", "Skills"), table=[["Python", "Docker"], ["SQL", ""]])
        text, error = parser.extract_text_from_docx(path)
        self.assertIsNone(error)
        self.assertEqual(text, f"{CV_LINE}\nSkills\nPython | Docker\nSQL")

    def test_empty_docx(self):
        text, error = parser.extract_text_from_docx(self.make_docx(paragraphs=()))
        self.assertIsNone(text)
        self.assertIn("appears to be empty", error)

    def test_pdf_renamed_to_docx(self):
        text, error = parser.extract_text_from_docx(self.make_pdf())
        self.assertIsNone(text)
        self.assertIn("doesn't look like a valid DOCX", error)

    def test_unsafe_zip_stops_before_python_docx(self):
        text, error = parser.extract_text_from_docx(self.make_zip([("word/document.xml", b"\0" * 2_000_000)]))
        self.assertIsNone(text)
        self.assertIn("looks malformed", error)

    def test_safe_zip_that_is_not_a_docx(self):
        with redirect_stdout(StringIO()):
            text, error = parser.extract_text_from_docx(self.make_zip([("hello.txt", b"hello")]))
        self.assertIsNone(text)
        self.assertEqual(error, "Could not read that DOCX. Please try a different file or paste your resume text.")


class PdfExtractionTests(TempDirTestCase):
    def test_text_is_extracted(self):
        text, error = parser.extract_text_from_pdf(self.make_pdf())
        self.assertIsNone(error)
        self.assertEqual(text, CV_LINE)

    def test_pages_are_joined(self):
        text, error = parser.extract_text_from_pdf(self.make_pdf(pages=("Page one", "Page two")))
        self.assertIsNone(error)
        self.assertEqual(text, "Page one\nPage two")

    def test_page_limit(self):
        path = self.make_pdf(pages=[""] * (parser.MAX_PDF_PAGES + 1))
        text, error = parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertIn(f"has {parser.MAX_PDF_PAGES + 1} pages", error)

    def test_page_limit_allows_exactly_the_maximum(self):
        pages = ["Page"] + [""] * (parser.MAX_PDF_PAGES - 1)
        text, error = parser.extract_text_from_pdf(self.make_pdf(pages=pages))
        self.assertIsNone(error)
        self.assertEqual(text, "Page")

    def test_image_only_pdf(self):
        text, error = parser.extract_text_from_pdf(self.make_pdf(pages=("",)))
        self.assertIsNone(text)
        self.assertIn("images/scanned content", error)

    def test_docx_renamed_to_pdf(self):
        text, error = parser.extract_text_from_pdf(self.make_docx())
        self.assertIsNone(text)
        self.assertIn("doesn't look like a valid PDF", error)

    def test_broken_pdf_gives_a_generic_message(self):
        path = self.write_bytes("cv.pdf", b"%PDF-1.4\nthis is not a pdf body")
        with redirect_stdout(StringIO()):
            text, error = parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertEqual(error, "Could not read that PDF. Please try a different file or paste your resume text.")

    def test_password_protected_pdf(self):
        pdf = FPDF()
        pdf.set_encryption(owner_password="owner", user_password="user")
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, CV_LINE)
        path = self.path("locked.pdf")
        pdf.output(path)
        with redirect_stdout(StringIO()):
            text, error = parser.extract_text_from_pdf(path)
        self.assertIsNone(text)
        self.assertIn("password-protected", error)


class PasteAndCleanTests(unittest.TestCase):
    def test_clean_text_normalises_whitespace(self):
        raw = "  Jo   Bloggs\t \n\n\n\n  Python  developer  \n"
        self.assertEqual(parser.clean_text(raw), "Jo Bloggs\n\nPython developer")

    def test_empty_paste(self):
        for text in ("", "   \n  ", None):
            with self.subTest(text=text):
                result, error = parser.extract_text_from_paste(text)
                self.assertIsNone(result)
                self.assertIn("No resume text provided", error)

    def test_short_paste(self):
        result, error = parser.extract_text_from_paste(" ".join(["word"] * 19))
        self.assertIsNone(result)
        self.assertIn("too short", error)

    def test_twenty_words_is_enough(self):
        result, error = parser.extract_text_from_paste(" ".join(["word"] * 20))
        self.assertIsNone(error)
        self.assertEqual(len(result.split()), 20)


class ParseResumeTests(TempDirTestCase):
    LONG_TEXT = " ".join([CV_LINE] * 3)

    def test_pasted_text_wins_over_a_file(self):
        result = parser.parse_resume(file_path=self.make_pdf(), pasted_text=self.LONG_TEXT, file_type="pdf")
        self.assertEqual(result, {"text": self.LONG_TEXT, "error": None, "word_count": len(self.LONG_TEXT.split())})

    def test_dispatches_by_file_type(self):
        self.assertEqual(parser.parse_resume(file_path=self.make_pdf(), file_type="pdf")["text"], CV_LINE)
        self.assertEqual(parser.parse_resume(file_path=self.make_docx(), file_type="docx")["text"], CV_LINE)

    def test_unsupported_file_type(self):
        result = parser.parse_resume(file_path=self.make_pdf(), file_type="rtf")
        self.assertEqual(result, {"text": None, "error": "Unsupported file type: rtf", "word_count": 0})

    def test_nothing_provided(self):
        for kwargs in ({}, {"file_path": "x.pdf"}, {"file_type": "pdf"}):
            with self.subTest(kwargs=kwargs):
                result = parser.parse_resume(**kwargs)
                self.assertIsNone(result["text"])
                self.assertEqual(result["word_count"], 0)
                self.assertIn("No resume provided", result["error"])

    def test_errors_return_zero_words(self):
        result = parser.parse_resume(pasted_text="too short")
        self.assertEqual(result["word_count"], 0)
        self.assertIn("too short", result["error"])


if __name__ == "__main__":
    unittest.main()

"""
Resume Parser Module
Handles extraction of text from PDF, DOCX, and plain text resumes.
"""

import os
import re
from PyPDF2 import PdfReader
from docx import Document


def extract_text_from_pdf(file_path):
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        full_text = "\n".join(text_parts)

        if not full_text.strip():
            return None, "The PDF appears to be empty or contains only images/scanned content. Try pasting your resume text directly."

        return clean_text(full_text), None

    except Exception as e:
        return None, f"Could not read PDF file: {str(e)}"


def extract_text_from_docx(file_path):
    """Extract text from a DOCX file."""
    try:
        doc = Document(file_path)
        text_parts = []

        # Extract text from paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)

        # Also extract text from tables (common in resumes)
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    text_parts.append(" | ".join(row_text))

        full_text = "\n".join(text_parts)

        if not full_text.strip():
            return None, "The DOCX file appears to be empty. Try pasting your resume text directly."

        return clean_text(full_text), None

    except Exception as e:
        return None, f"Could not read DOCX file: {str(e)}"


def extract_text_from_paste(text):
    """Process pasted resume text."""
    if not text or not text.strip():
        return None, "No resume text provided. Please paste your resume content."

    cleaned = clean_text(text)

    if len(cleaned.split()) < 20:
        return None, "The pasted text seems too short to be a resume. Please paste your full resume content."

    return cleaned, None


def clean_text(text):
    """Clean and normalize extracted text."""
    # Replace multiple whitespace with single space (but preserve newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Replace multiple consecutive newlines with double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    # Remove leading/trailing whitespace from the whole text
    text = text.strip()
    return text


def parse_resume(file_path=None, pasted_text=None, file_type=None):
    """
    Main entry point for resume parsing.

    Args:
        file_path: Path to uploaded file (PDF or DOCX)
        pasted_text: Directly pasted resume text
        file_type: Type of file ('pdf', 'docx', or 'text')

    Returns:
        dict with 'text' (extracted text) and 'error' (error message if any)
    """
    if pasted_text:
        text, error = extract_text_from_paste(pasted_text)
    elif file_path and file_type:
        if file_type == 'pdf':
            text, error = extract_text_from_pdf(file_path)
        elif file_type == 'docx':
            text, error = extract_text_from_docx(file_path)
        else:
            text, error = None, f"Unsupported file type: {file_type}"
    else:
        text, error = None, "No resume provided. Please upload a file or paste your resume text."

    if error:
        return {"text": None, "error": error, "word_count": 0}

    word_count = len(text.split())

    return {
        "text": text,
        "error": None,
        "word_count": word_count
    }

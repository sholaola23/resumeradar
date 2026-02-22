"""
ResumeRadar -- CV PDF Generator
Generates ATS-friendly resume PDFs in 3 templates: Classic, Modern, Minimal.
Uses fpdf2, Helvetica only, no graphics/icons. Follows report_generator.py patterns.

Design informed by:
- 4 real-world reference CVs (Billy Soomro, Osinachi Okpara, Ismail Oyeleke, Mayowa Ojo)
- 2025-2026 ATS best practices research (Jobscan, Indeed, Enhancv, CVCraft)

Key ATS formatting rules applied:
- Single-column layout only (no tables, no multi-column)
- Helvetica font (ATS-safe), minimum 10pt body text
- Standard section labels ATS parsers expect
- Skills section placed BEFORE experience (2025 skills-based hiring trend)
- Round filled bullet points (universally used in professional resumes)
- Proper text wrapping with consistent indentation
- No images, icons, graphics, or decorative elements
"""

from fpdf import FPDF


def _safe(text):
    """Replace Unicode characters that core PDF fonts can't handle."""
    if not text:
        return ""
    replacements = {
        '\u2014': '--',   # em dash
        '\u2013': '-',    # en dash
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2026': '...',  # ellipsis
        '\u2022': '-',    # bullet (fallback for inline text only)
        '\u2192': '->',   # right arrow
        '\u2190': '<-',   # left arrow
        '\u2713': '[x]',  # check mark
        '\u2717': '[ ]',  # cross mark
        '\u00a0': ' ',    # non-breaking space
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    try:
        text.encode('latin-1')
    except UnicodeEncodeError:
        text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text


TEMPLATES = ["classic", "modern", "minimal"]


def _flatten_skills(skills):
    """Normalize skills from either format into a flat list of strings.
    Scan flow returns: {"matched": [...], "missing": [...], "additional": [...]}
    Form flow returns: ["skill1", "skill2", ...]
    """
    if isinstance(skills, list):
        return [s for s in skills if isinstance(s, str) and s.strip()]
    elif isinstance(skills, dict):
        flat = []
        for key in ["matched", "additional", "missing"]:
            items = skills.get(key, [])
            if isinstance(items, list):
                for s in items:
                    if isinstance(s, str) and s.strip() and s not in flat:
                        flat.append(s)
        return flat
    return []


def generate_cv_pdf(cv_data, template="classic"):
    """
    Generate an ATS-friendly resume PDF.

    Args:
        cv_data: dict with personal, summary, experience, education, skills, certifications
        template: "classic", "modern", or "minimal"

    Returns:
        bytes: PDF file content
    """
    if template not in TEMPLATES:
        template = "classic"

    personal = cv_data.get("personal", {})
    summary = cv_data.get("summary", "")
    experience = cv_data.get("experience", [])
    education = cv_data.get("education", [])
    raw_skills = cv_data.get("skills", [])
    certifications = cv_data.get("certifications", [])

    # Normalize skills: scan flow returns {matched:[], missing:[], additional:[]}
    # form flow returns a flat list of strings
    skills = _flatten_skills(raw_skills)

    if template == "modern":
        return _render_modern(personal, summary, experience, education, skills, certifications)
    elif template == "minimal":
        return _render_minimal(personal, summary, experience, education, skills, certifications)
    else:
        return _render_classic(personal, summary, experience, education, skills, certifications)


# ============================================================
# SHARED HELPERS
# ============================================================

def _format_contact_line(personal, separator=" | "):
    """Build a contact info line from personal data."""
    parts = []
    if personal.get("email"):
        parts.append(personal["email"])
    if personal.get("phone"):
        parts.append(personal["phone"])
    if personal.get("location"):
        parts.append(personal["location"])
    if personal.get("linkedin"):
        parts.append(personal["linkedin"])
    if personal.get("portfolio"):
        parts.append(personal["portfolio"])
    return separator.join(parts)


def _format_date_range(entry):
    """Format start_date - end_date for experience entries."""
    start = entry.get("start_date", "")
    end = entry.get("end_date", "Present")
    if start and end:
        return f"{start} - {end}"
    elif start:
        return start
    return ""


def _render_bullet_point(pdf, text, indent_x=22, text_width=170, line_height=5.5, font_size=10):
    """Render a bullet with a filled circle and properly indented wrapped text.

    Draws a small filled circle at the bullet position, then renders the text
    with proper left margin so wrapped lines stay aligned with the first line.
    This matches the round bullet style seen in professional CV templates.
    """
    # Draw small filled circle as bullet
    r = 0.6  # radius in mm (1.2mm diameter — matches professional CV bullet size)
    cx = indent_x - 3  # center of bullet, 3mm left of text start
    cy = pdf.get_y() + line_height / 2  # vertically centered with first line of text
    pdf.set_fill_color(55, 65, 81)
    pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r, style='F')

    # Temporarily adjust left margin so wrapped lines stay indented
    old_l_margin = pdf.l_margin
    pdf.l_margin = indent_x
    pdf.set_x(indent_x)
    pdf.set_font('Helvetica', '', font_size)
    pdf.set_text_color(55, 65, 81)
    pdf.multi_cell(text_width, line_height, _safe(text), align='L')
    pdf.l_margin = old_l_margin


# ============================================================
# TEMPLATE 1: CLASSIC
# Traditional single-column, underline separators, standard corporate.
# Inspired by Ismail Oyeleke & Mayowa Ojo CV styles.
# ============================================================

def _render_classic(personal, summary, experience, education, skills, certifications):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    # -- Name (centered, 18pt bold) --
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(31, 41, 55)
    name = _safe(personal.get("full_name", ""))
    if name:
        pdf.cell(0, 10, name, new_x='LMARGIN', new_y='NEXT', align='C')

    # -- Contact line (centered, pipe-separated) --
    contact = _safe(_format_contact_line(personal))
    if contact:
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 6, contact, new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(4)

    # -- Professional Summary --
    if summary:
        _classic_section_header(pdf, "PROFESSIONAL SUMMARY")
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(0, 5.5, _safe(summary), align='L')
        pdf.ln(2)

    # -- Skills (placed BEFORE experience per 2025 ATS best practices) --
    if skills:
        _classic_section_header(pdf, "SKILLS")
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(0, 5.5, _safe(", ".join(skills)), align='L')
        pdf.ln(2)

    # -- Professional Experience --
    if experience:
        _classic_section_header(pdf, "PROFESSIONAL EXPERIENCE")
        for i, exp in enumerate(experience):
            title = _safe(exp.get("title", ""))
            company = _safe(exp.get("company", ""))
            dates = _safe(_format_date_range(exp))

            # Title, Company on left — dates right-aligned on same line
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(31, 41, 55)
            title_company = title
            if company:
                title_company += f", {company}"

            # Measure text to avoid overlap with dates
            tc_width = pdf.get_string_width(title_company)
            available = 180
            if dates:
                pdf.set_font('Helvetica', '', 10)
                date_width = pdf.get_string_width(dates) + 5
                text_space = available - date_width
                pdf.set_font('Helvetica', 'B', 11)
            else:
                text_space = available

            if tc_width <= text_space:
                # Fits on one line with date
                pdf.cell(text_space, 6, title_company)
                if dates:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 6, dates, new_x='LMARGIN', new_y='NEXT', align='R')
                else:
                    pdf.ln(6)
            else:
                # Too long — title on one line, date on next
                pdf.cell(0, 6, title_company, new_x='LMARGIN', new_y='NEXT')
                if dates:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 5, dates, new_x='LMARGIN', new_y='NEXT')

            # Bullets with filled circle (matching reference CV style)
            bullets = exp.get("bullets", [])
            for bullet in bullets:
                _render_bullet_point(pdf, bullet, indent_x=22, text_width=173)

            if i < len(experience) - 1:
                pdf.ln(3)
            else:
                pdf.ln(1)

    # -- Education --
    if education:
        _classic_section_header(pdf, "EDUCATION")
        for i, edu in enumerate(education):
            degree = _safe(edu.get("degree", ""))
            institution = _safe(edu.get("institution", ""))
            grad_date = _safe(edu.get("graduation_date", ""))
            details = _safe(edu.get("details", ""))

            # Degree, Institution on left — date right-aligned
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(31, 41, 55)
            deg_inst = degree
            if institution:
                deg_inst += f", {institution}"

            # Measure to avoid overlap
            deg_width = pdf.get_string_width(deg_inst)
            available = 180
            if grad_date:
                pdf.set_font('Helvetica', '', 10)
                date_width = pdf.get_string_width(grad_date) + 5
                text_space = available - date_width
                pdf.set_font('Helvetica', 'B', 11)
            else:
                text_space = available

            if deg_width <= text_space:
                pdf.cell(text_space, 6, deg_inst)
                if grad_date:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 6, grad_date, new_x='LMARGIN', new_y='NEXT', align='R')
                else:
                    pdf.ln(6)
            else:
                pdf.cell(0, 6, deg_inst, new_x='LMARGIN', new_y='NEXT')
                if grad_date:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 5, grad_date, new_x='LMARGIN', new_y='NEXT')

            if details:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(55, 65, 81)
                pdf.set_x(20)
                pdf.multi_cell(170, 5.5, details, align='L')

            if i < len(education) - 1:
                pdf.ln(3)
        pdf.ln(2)

    # -- Certifications --
    if certifications:
        _classic_section_header(pdf, "CERTIFICATIONS")
        for cert in certifications:
            cert_name = cert.get("name", "")
            issuer = cert.get("issuer", "")
            date = cert.get("date", "")
            line = cert_name
            if issuer:
                line += f" - {issuer}"
            if date:
                line += f" ({date})"
            _render_bullet_point(pdf, line, indent_x=22, text_width=173)

    return pdf.output()


def _classic_section_header(pdf, title):
    """Section header with full-width underline separator."""
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 7, _safe(title), new_x='LMARGIN', new_y='NEXT')
    # Full-width underline
    pdf.set_draw_color(31, 41, 55)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(15, y, 195, y)
    pdf.ln(3)


# ============================================================
# TEMPLATE 2: MODERN
# Blue accent line, uppercase headers, compact but readable.
# Inspired by Billy Soomro CV style with accent elements.
# ============================================================

def _render_modern(personal, summary, experience, education, skills, certifications):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)  # ATS minimum: 15mm (~0.6in)

    # -- Name (bold, blue accent, left-aligned) --
    pdf.set_font('Helvetica', 'B', 20)
    pdf.set_text_color(37, 99, 235)  # Primary blue
    name = _safe(personal.get("full_name", ""))
    if name:
        pdf.cell(0, 12, name, new_x='LMARGIN', new_y='NEXT')

    # -- Contact (stacked on 2 lines) --
    contact_parts = []
    if personal.get("email"):
        contact_parts.append(personal["email"])
    if personal.get("phone"):
        contact_parts.append(personal["phone"])
    if personal.get("location"):
        contact_parts.append(personal["location"])

    line2_parts = []
    if personal.get("linkedin"):
        line2_parts.append(personal["linkedin"])
    if personal.get("portfolio"):
        line2_parts.append(personal["portfolio"])

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(107, 114, 128)
    if contact_parts:
        pdf.cell(0, 5, _safe(" | ".join(contact_parts)), new_x='LMARGIN', new_y='NEXT')
    if line2_parts:
        pdf.cell(0, 5, _safe(" | ".join(line2_parts)), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(6)

    # -- Professional Summary --
    if summary:
        _modern_section_header(pdf, "PROFESSIONAL SUMMARY")
        _modern_accent_block(pdf, lambda: _modern_body_text(pdf, summary))
        pdf.ln(3)

    # -- Skills (placed BEFORE experience per 2025 ATS best practices) --
    if skills:
        _modern_section_header(pdf, "SKILLS")

        def render_skills():
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(55, 65, 81)
            pdf.multi_cell(0, 5.5, _safe(", ".join(skills)), align='L')

        _modern_accent_block(pdf, render_skills)

    # -- Experience --
    if experience:
        _modern_section_header(pdf, "EXPERIENCE")
        for i, exp in enumerate(experience):
            title = _safe(exp.get("title", ""))
            company = _safe(exp.get("company", ""))
            dates = _safe(_format_date_range(exp))

            def render_exp(t=title, c=company, d=dates, b=exp.get("bullets", [])):
                # Title | Company on one line
                pdf.set_font('Helvetica', 'B', 10)
                pdf.set_text_color(31, 41, 55)
                header_line = t
                if c:
                    header_line += f" | {c}"
                pdf.cell(0, 6, header_line, new_x='LMARGIN', new_y='NEXT')

                # Dates in regular weight below (not italic — ATS safety)
                if d:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 5, d, new_x='LMARGIN', new_y='NEXT')

                # Bullets with filled circles
                for bullet in b:
                    cur_margin = pdf.l_margin
                    _render_bullet_point(pdf, bullet, indent_x=cur_margin + 7,
                                         text_width=168, line_height=5.5, font_size=10)

            _modern_accent_block(pdf, render_exp)
            if i < len(experience) - 1:
                pdf.ln(3)

    # -- Education --
    if education:
        _modern_section_header(pdf, "EDUCATION")
        for edu in education:
            degree = _safe(edu.get("degree", ""))
            institution = _safe(edu.get("institution", ""))
            grad_date = _safe(edu.get("graduation_date", ""))
            details = _safe(edu.get("details", ""))

            def render_edu(dg=degree, inst=institution, gd=grad_date, det=details):
                pdf.set_font('Helvetica', 'B', 10)
                pdf.set_text_color(31, 41, 55)
                line = dg
                if inst:
                    line += f" | {inst}"
                pdf.cell(0, 6, line, new_x='LMARGIN', new_y='NEXT')
                if gd:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 5, gd, new_x='LMARGIN', new_y='NEXT')
                if det:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(55, 65, 81)
                    pdf.multi_cell(0, 5.5, det, align='L')

            _modern_accent_block(pdf, render_edu)

    # -- Certifications --
    if certifications:
        _modern_section_header(pdf, "CERTIFICATIONS")
        for cert in certifications:
            cert_name = cert.get("name", "")
            issuer = cert.get("issuer", "")
            date = cert.get("date", "")

            def render_cert(cn=cert_name, ci=issuer, cd=date):
                line = cn
                if ci:
                    line += f" - {ci}"
                if cd:
                    line += f" ({cd})"
                cur_margin = pdf.l_margin
                _render_bullet_point(pdf, line, indent_x=cur_margin + 7,
                                     text_width=168, line_height=5.5, font_size=10)

            _modern_accent_block(pdf, render_cert)

    return pdf.output()


def _modern_section_header(pdf, title):
    """Uppercase section header in blue, no underline."""
    pdf.ln(4)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 7, _safe(title), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)


def _modern_body_text(pdf, text):
    """Standard body text for modern template."""
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(55, 65, 81)
    pdf.multi_cell(0, 5.5, _safe(text), align='L')


def _modern_accent_block(pdf, render_fn):
    """Render content with a thin blue accent line on the left."""
    start_y = pdf.get_y()
    start_x = pdf.get_x()
    # Indent content slightly to make room for accent line
    pdf.set_x(start_x + 5)
    old_l_margin = pdf.l_margin
    pdf.l_margin = old_l_margin + 5
    render_fn()
    pdf.l_margin = old_l_margin
    end_y = pdf.get_y()
    # Draw accent line
    pdf.set_draw_color(37, 99, 235)
    pdf.set_line_width(0.5)
    pdf.line(start_x + 1, start_y, start_x + 1, end_y)
    pdf.ln(2)


# ============================================================
# TEMPLATE 3: MINIMAL
# Ultra-clean, generous whitespace, no separators or bullets.
# Executive / design-adjacent feel.
# ============================================================

def _render_minimal(personal, summary, experience, education, skills, certifications):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # -- Name (regular weight, 18pt — clean executive style) --
    pdf.set_font('Helvetica', '', 18)
    pdf.set_text_color(31, 41, 55)
    name = _safe(personal.get("full_name", ""))
    if name:
        pdf.cell(0, 10, name, new_x='LMARGIN', new_y='NEXT', align='C')

    # -- Contact as pipe-separated line --
    contact = _safe(_format_contact_line(personal, " | "))
    if contact:
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 5, contact, new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.ln(10)

    # -- Summary --
    if summary:
        _minimal_section_header(pdf, "Summary")
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(0, 6, _safe(summary), align='L')
        pdf.ln(6)

    # -- Skills (placed BEFORE experience per 2025 ATS best practices) --
    if skills:
        _minimal_section_header(pdf, "Skills")
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(0, 6, _safe(", ".join(skills)), align='L')
        pdf.ln(6)

    # -- Experience --
    if experience:
        _minimal_section_header(pdf, "Experience")
        for i, exp in enumerate(experience):
            title = _safe(exp.get("title", ""))
            company = _safe(exp.get("company", ""))
            dates = _safe(_format_date_range(exp))

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 6, title, new_x='LMARGIN', new_y='NEXT')

            sub_parts = []
            if company:
                sub_parts.append(company)
            if dates:
                sub_parts.append(dates)
            if sub_parts:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 5, " | ".join(sub_parts), new_x='LMARGIN', new_y='NEXT')

            pdf.ln(2)

            # Indented text blocks (no bullet symbols — minimal design)
            bullets = exp.get("bullets", [])
            for bullet in bullets:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(55, 65, 81)
                # Fix: set left margin so wrapped lines stay indented
                old_l_margin = pdf.l_margin
                pdf.l_margin = 25
                pdf.set_x(25)
                pdf.multi_cell(155, 6, _safe(bullet), align='L')
                pdf.l_margin = old_l_margin
                pdf.ln(1)

            if i < len(experience) - 1:
                pdf.ln(4)
            else:
                pdf.ln(2)

    # -- Education --
    if education:
        _minimal_section_header(pdf, "Education")
        for edu in education:
            degree = _safe(edu.get("degree", ""))
            institution = _safe(edu.get("institution", ""))
            grad_date = _safe(edu.get("graduation_date", ""))
            details = _safe(edu.get("details", ""))

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 6, degree, new_x='LMARGIN', new_y='NEXT')

            sub_parts = []
            if institution:
                sub_parts.append(institution)
            if grad_date:
                sub_parts.append(grad_date)
            if sub_parts:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 5, " | ".join(sub_parts), new_x='LMARGIN', new_y='NEXT')

            if details:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(55, 65, 81)
                old_l_margin = pdf.l_margin
                pdf.l_margin = 25
                pdf.set_x(25)
                pdf.multi_cell(155, 6, details, align='L')
                pdf.l_margin = old_l_margin
            pdf.ln(3)

    # -- Certifications --
    if certifications:
        _minimal_section_header(pdf, "Certifications")
        for cert in certifications:
            cert_name = _safe(cert.get("name", ""))
            issuer = _safe(cert.get("issuer", ""))
            date = _safe(cert.get("date", ""))
            line = cert_name
            if issuer:
                line += f" - {issuer}"
            if date:
                line += f" ({date})"
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(55, 65, 81)
            pdf.set_x(20)
            pdf.multi_cell(170, 6, line, align='L')

    return pdf.output()


def _minimal_section_header(pdf, title):
    """Simple bold header with generous spacing above, no separator."""
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 7, _safe(title), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

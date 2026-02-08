"""
ResumeRadar -- PDF Report Generator
Generates a branded, formatted PDF report from scan data using fpdf2.
"""

from fpdf import FPDF
from datetime import datetime
import io


def _safe(text):
    """Replace Unicode characters that core PDF fonts can't handle."""
    if not text:
        return text
    replacements = {
        '\u2014': '--',   # em dash
        '\u2013': '-',    # en dash
        '\u2018': "'",    # left single quote
        '\u2019': "'",    # right single quote
        '\u201c': '"',    # left double quote
        '\u201d': '"',    # right double quote
        '\u2026': '...',  # ellipsis
        '\u2022': '*',    # bullet
        '\u2192': '->',   # right arrow
        '\u2190': '<-',   # left arrow
        '\u2713': '[x]',  # check mark
        '\u2717': '[ ]',  # cross mark
        '\u00a0': ' ',    # non-breaking space
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-latin-1 characters
    try:
        text.encode('latin-1')
    except UnicodeEncodeError:
        text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text


class ResumeRadarPDF(FPDF):
    """Custom PDF class with ResumeRadar branding."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        """Add branded header to each page."""
        self.set_font('Helvetica', 'B', 18)
        self.set_text_color(37, 99, 235)  # Primary blue
        self.cell(0, 10, 'ResumeRadar', new_x='LMARGIN', new_y='NEXT')
        self.set_font('Helvetica', '', 10)
        self.set_text_color(107, 114, 128)  # Gray
        self.cell(0, 5, 'Beat the scan. Land the interview.', new_x='LMARGIN', new_y='NEXT')
        self.ln(4)
        # Divider line
        self.set_draw_color(229, 231, 235)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        """Add footer with branding and page number."""
        self.set_y(-20)
        self.set_draw_color(229, 231, 235)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(156, 163, 175)
        self.cell(0, 5, _safe(f'ResumeRadar Report  |  Built by Olushola Oladipupo  |  Page {self.page_no()}/{{nb}}'), align='C')

    def section_title(self, title, emoji=''):
        """Add a styled section title."""
        self.ln(4)
        self.set_font('Helvetica', 'B', 13)
        self.set_text_color(31, 41, 55)  # Dark gray
        self.cell(0, 8, _safe(title), new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(37, 99, 235)
        self.set_line_width(0.8)
        self.line(10, self.get_y() + 1, 80, self.get_y() + 1)
        self.ln(6)

    def body_text(self, text, bold=False):
        """Add body text with word wrapping."""
        style = 'B' if bold else ''
        self.set_font('Helvetica', style, 10)
        self.set_text_color(75, 85, 99)
        self.multi_cell(0, 5.5, _safe(text))
        self.ln(2)

    def stat_row(self, label, value, color=None):
        """Add a label-value stat row."""
        self.set_font('Helvetica', '', 10)
        self.set_text_color(107, 114, 128)
        self.cell(60, 6, _safe(label))
        if color:
            self.set_text_color(*color)
        else:
            self.set_text_color(31, 41, 55)
        self.set_font('Helvetica', 'B', 10)
        self.cell(0, 6, _safe(str(value)), new_x='LMARGIN', new_y='NEXT')

    def keyword_tag_line(self, category, keywords, tag_type='missing'):
        """Add a line of keywords for a category."""
        if not keywords:
            return
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(75, 85, 99)
        self.cell(0, 6, _safe(category), new_x='LMARGIN', new_y='NEXT')

        self.set_font('Helvetica', '', 9)
        if tag_type == 'missing':
            self.set_text_color(220, 38, 38)  # Red
        else:
            self.set_text_color(5, 150, 105)  # Green

        # Join keywords with commas and wrap
        keywords_text = ', '.join(keywords)
        self.multi_cell(0, 5, _safe(keywords_text))
        self.ln(3)


def generate_pdf_report(scan_data):
    """
    Generate a formatted PDF report from scan results.

    Args:
        scan_data: dict with match_score, category_scores, missing_keywords,
                   matched_keywords, ai_suggestions, ats_formatting, etc.

    Returns:
        bytes: The PDF file content as bytes.
    """
    pdf = ResumeRadarPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    now = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    ai = scan_data.get('ai_suggestions', {}) or {}
    ats = scan_data.get('ats_formatting', {}) or {}

    cat_labels = {
        'technical_skills': 'Technical Skills',
        'soft_skills': 'Soft Skills',
        'certifications': 'Certifications',
        'education': 'Education',
        'action_verbs': 'Action Verbs',
    }

    # -- Report Date --
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 5, _safe(f'Report generated: {now}'), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(6)

    # ==================================
    # ATS MATCH SCORE
    # ==================================
    score = scan_data.get('match_score', 0)

    # Score color
    if score >= 75:
        score_color = (5, 150, 105)   # Green
        score_label = 'Strong Match'
    elif score >= 50:
        score_color = (217, 119, 6)   # Amber
        score_label = 'Moderate Match'
    else:
        score_color = (220, 38, 38)   # Red
        score_label = 'Needs Improvement'

    # Big score display
    pdf.set_font('Helvetica', 'B', 42)
    pdf.set_text_color(*score_color)
    pdf.cell(50, 20, f'{score}%')
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 20, _safe(f'ATS Match Score -- {score_label}'), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    # Stats row
    pdf.stat_row('Keywords Matched:', str(scan_data.get('total_matched', 0)), (5, 150, 105))
    pdf.stat_row('Keywords Missing:', str(scan_data.get('total_missing', 0)), (220, 38, 38))
    pdf.stat_row('Total Job Keywords:', str(scan_data.get('total_job_keywords', 0)))
    pdf.ln(4)

    # ── AI Summary ──
    if ai.get('summary'):
        pdf.section_title('Summary')
        pdf.body_text(ai['summary'])

    # ══════════════════════════════════════════
    # CATEGORY BREAKDOWN
    # ══════════════════════════════════════════
    pdf.section_title('Category Breakdown', '')

    category_scores = scan_data.get('category_scores', {})
    for key, info in category_scores.items():
        if info.get('total', 0) == 0:
            continue

        cat_score = round(info.get('score', 0))
        matched = info.get('matched', 0)
        total = info.get('total', 0)
        label = cat_labels.get(key, key)

        # Color based on score
        if cat_score >= 75:
            bar_color = (5, 150, 105)
        elif cat_score >= 50:
            bar_color = (217, 119, 6)
        else:
            bar_color = (220, 38, 38)

        # Category name and score text
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(55, 65, 81)
        pdf.cell(90, 6, _safe(label))
        pdf.set_text_color(*bar_color)
        pdf.cell(0, 6, _safe(f'{cat_score}%  ({matched}/{total})'), new_x='LMARGIN', new_y='NEXT')

        # Progress bar background
        bar_x = 10
        bar_y = pdf.get_y() + 1
        bar_width = 190
        bar_height = 5

        pdf.set_fill_color(243, 244, 246)  # Gray background
        pdf.rect(bar_x, bar_y, bar_width, bar_height, 'F')

        # Progress bar fill
        fill_width = (cat_score / 100) * bar_width
        if fill_width > 0:
            pdf.set_fill_color(*bar_color)
            pdf.rect(bar_x, bar_y, fill_width, bar_height, 'F')

        pdf.ln(10)

    # ══════════════════════════════════════════
    # MISSING KEYWORDS
    # ══════════════════════════════════════════
    missing = scan_data.get('missing_keywords', {})
    missing_entries = {k: v for k, v in missing.items() if v and len(v) > 0}

    if missing_entries:
        pdf.section_title('Missing Keywords', '')
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(107, 114, 128)
        pdf.multi_cell(0, 5, 'These keywords appear in the job description but NOT in your resume. ATS systems are scanning for them.')
        pdf.ln(4)

        for cat, words in missing_entries.items():
            label = cat_labels.get(cat, cat)
            pdf.keyword_tag_line(label, words, 'missing')

    # ══════════════════════════════════════════
    # MATCHED KEYWORDS
    # ══════════════════════════════════════════
    matched = scan_data.get('matched_keywords', {})
    matched_entries = {k: v for k, v in matched.items() if v and len(v) > 0}

    if matched_entries:
        pdf.section_title('Matched Keywords', '')

        for cat, words in matched_entries.items():
            label = cat_labels.get(cat, cat)
            pdf.keyword_tag_line(label, words, 'matched')

    # ══════════════════════════════════════════
    # AI SUGGESTIONS
    # ══════════════════════════════════════════

    # Strengths
    strengths = ai.get('strengths', [])
    if strengths:
        pdf.section_title('Your Strengths', '')
        for s in strengths:
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(5, 150, 105)
            pdf.cell(8, 5.5, '+')
            pdf.set_text_color(75, 85, 99)
            pdf.multi_cell(0, 5.5, _safe(s))
            pdf.ln(1)

    # Key Improvements
    improvements = ai.get('critical_improvements', [])
    if improvements:
        pdf.section_title('Key Improvements', '')
        for item in improvements:
            priority = (item.get('priority', 'medium')).upper()
            section = item.get('section', '')
            issue = item.get('issue', '')
            suggestion = item.get('suggestion', '')

            # Priority badge
            if priority == 'HIGH':
                badge_color = (220, 38, 38)
            elif priority == 'MEDIUM':
                badge_color = (217, 119, 6)
            else:
                badge_color = (107, 114, 128)

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(*badge_color)
            pdf.set_x(10)
            pdf.cell(0, 5.5, _safe(f'[{priority}] {section}'), new_x='LMARGIN', new_y='NEXT')

            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(75, 85, 99)
            pdf.set_x(10)
            pdf.multi_cell(190, 5.5, _safe(issue))

            pdf.set_font('Helvetica', 'I', 10)
            pdf.set_text_color(37, 99, 235)
            pdf.set_x(10)
            pdf.multi_cell(190, 5.5, _safe(f'-> {suggestion}'))
            pdf.ln(4)

    # Keyword Suggestions
    kw_suggestions = ai.get('keyword_suggestions', [])
    if kw_suggestions:
        pdf.section_title('How to Add Missing Keywords', '')
        for item in kw_suggestions:
            keyword = item.get('keyword', '')
            where = item.get('where_to_add', '')
            how = item.get('how_to_add', '')

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 5.5, _safe(f'"{keyword}"  ->  {where}'), new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(107, 114, 128)
            pdf.multi_cell(0, 5, _safe(how))
            pdf.ln(3)

    # Quick Wins
    quick_wins = ai.get('quick_wins', [])
    if quick_wins:
        pdf.section_title('Quick Wins', '')
        for w in quick_wins:
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(75, 85, 99)
            pdf.multi_cell(0, 5.5, _safe(f'*  {w}'))
            pdf.ln(2)

    # ══════════════════════════════════════════
    # ATS FORMATTING CHECK
    # ══════════════════════════════════════════
    ats_issues = ats.get('issues', [])
    ats_tips = ats.get('tips', [])
    contact_info = ats.get('has_contact_info', {})

    if ats_issues or ats_tips or contact_info:
        pdf.section_title('ATS Formatting Check', '')

        # Contact info
        if contact_info:
            pdf.set_font('Helvetica', '', 10)
            checks = []
            for field in ['email', 'phone', 'linkedin']:
                found = contact_info.get(field, False)
                icon = 'YES' if found else 'NO'
                color = (5, 150, 105) if found else (156, 163, 175)
                checks.append((field.title(), icon, color))

            for field_name, status, color in checks:
                pdf.set_text_color(*color)
                pdf.set_font('Helvetica', 'B', 10)
                pdf.cell(12, 6, status)
                pdf.set_text_color(75, 85, 99)
                pdf.set_font('Helvetica', '', 10)
                pdf.cell(40, 6, field_name)

            pdf.ln(8)

        # Issues
        for issue in ats_issues:
            issue_type = issue.get('type', 'info')
            message = issue.get('message', '')
            detail = issue.get('detail', '')

            if issue_type == 'critical':
                icon = '[!!]'
                color = (220, 38, 38)
            elif issue_type == 'warning':
                icon = '[!]'
                color = (217, 119, 6)
            else:
                icon = '[i]'
                color = (37, 99, 235)

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(*color)
            pdf.cell(12, 5.5, icon)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 5.5, _safe(message), new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(107, 114, 128)
            pdf.set_x(22)
            pdf.multi_cell(0, 5, _safe(detail))
            pdf.ln(3)

        # Tips
        if ats_tips:
            pdf.ln(4)
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(55, 65, 81)
            pdf.cell(0, 6, 'Pro Tips', new_x='LMARGIN', new_y='NEXT')
            pdf.ln(2)
            for tip in ats_tips:
                pdf.set_font('Helvetica', '', 9)
                pdf.set_text_color(107, 114, 128)
                pdf.multi_cell(0, 5, _safe(f'*  {tip}'))
                pdf.ln(2)

    # ==================================
    # FOOTER BRANDING
    # ==================================
    pdf.ln(10)
    pdf.set_draw_color(229, 231, 235)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 6, 'ResumeRadar', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(0, 5, 'Built by Olushola Oladipupo  |  AWS Solutions Architect', new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 5, 'https://www.linkedin.com/in/olushola-oladipupo/', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(0, 5, 'Your resume is analyzed in real-time and never stored. Your data stays yours.', new_x='LMARGIN', new_y='NEXT')

    # Output as bytes
    return pdf.output()

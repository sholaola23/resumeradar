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

from collections import OrderedDict

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


# ============================================================
# SKILL GROUPING
# ============================================================

# Category mapping: ordered by display priority.
# Each set contains lowercase skill terms that belong to that category.
_SKILL_CATEGORIES = OrderedDict([
    ("Cloud & Infrastructure", {
        "aws", "azure", "gcp", "google cloud", "amazon web services", "cloud computing",
        "ec2", "s3", "lambda", "rds", "vpc", "iam", "cloudformation", "cloudwatch",
        "terraform", "ansible", "puppet", "chef", "infrastructure as code", "iac",
        "docker", "kubernetes", "k8s", "containers", "ecs", "eks", "fargate",
        "openshift", "helm", "container orchestration", "cloudfront", "route 53",
    }),
    ("CI/CD & DevOps", {
        "ci/cd", "cicd", "jenkins", "github actions", "gitlab ci", "circleci",
        "devops", "devsecops", "continuous integration", "continuous delivery",
        "continuous deployment", "argocd", "spinnaker", "codepipeline",
    }),
    ("Programming", {
        "python", "javascript", "typescript", "java", "c#", "c++", "go", "golang",
        "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
        "bash", "shell scripting", "powershell",
    }),
    ("Web & Frontend", {
        "react", "reactjs", "react.js", "angular", "vue", "vuejs", "vue.js",
        "next.js", "nextjs", "node.js", "nodejs", "express", "html", "css",
        "tailwind", "bootstrap", "sass", "webpack", "vite",
    }),
    ("Backend & APIs", {
        "rest", "restful", "graphql", "api", "apis", "microservices",
        "serverless", "flask", "django", "spring boot", "fastapi",
        "http", "https", "http/https",
    }),
    ("Data & Databases", {
        "sql", "nosql", "postgresql", "mysql", "mongodb", "dynamodb", "redis",
        "elasticsearch", "cassandra", "oracle", "database", "data modeling",
        "etl", "data pipeline", "data warehouse", "redshift", "bigquery",
        "snowflake", "apache spark", "kafka", "airflow",
    }),
    ("AI & Data Science", {
        "machine learning", "deep learning", "artificial intelligence", "ai",
        "ml", "nlp", "natural language processing", "computer vision",
        "tensorflow", "pytorch", "scikit-learn", "llm", "large language model",
        "generative ai", "llms", "prompt optimization", "ai agent orchestration",
        "ai-assisted workflows",
    }),
    ("Security & Compliance", {
        "security", "cybersecurity", "encryption", "oauth", "sso", "identity",
        "access management", "zero trust", "penetration testing", "siem",
        "compliance", "gdpr", "hipaa", "soc2", "soc 2", "data security",
    }),
    ("Tools & Platforms", {
        "git", "github", "gitlab", "bitbucket", "version control",
        "jira", "confluence", "figma", "notion",
        "linux", "windows server", "unix", "macos",
        "monitoring", "observability", "logging", "prometheus", "grafana",
        "datadog", "splunk", "new relic", "elk stack", "cloudtrail",
    }),
    ("Methodologies", {
        "agile", "scrum", "kanban", "waterfall", "sdlc", "lean", "sprint",
        "testing", "unit testing", "integration testing", "test automation",
        "selenium", "cypress", "jest", "pytest", "qa", "quality assurance",
        "agile ceremonies and delivery", "backlog refinement", "roadmap execution",
        "product strategy",
    }),
    ("Soft Skills", {
        "communication", "leadership", "teamwork", "collaboration",
        "problem solving", "problem-solving", "critical thinking", "analytical",
        "attention to detail", "time management", "project management",
        "stakeholder management", "mentoring", "coaching", "presentation",
        "public speaking", "negotiation", "conflict resolution",
        "decision making", "decision-making", "adaptability", "flexibility",
        "creativity", "innovation", "strategic thinking", "strategic planning",
        "customer facing", "cross-functional", "cross functional",
        "self-motivated", "self-starter", "results-driven", "results driven",
        "detail-oriented", "detail oriented", "fast-paced", "multitasking",
        "prioritization", "organizational", "interpersonal",
        "written communication", "verbal communication",
        "emotional intelligence", "relationship building",
        "cross-functional leadership", "user engagement",
        "data-driven decisions", "scalability", "integration",
    }),
])


def _group_skills(skills):
    """Group a flat list of skills into categories for structured rendering.

    Returns an OrderedDict of {category_label: [original_case_skills]}.
    Skills that don't match any category go into 'Other'.
    Empty categories are omitted.
    """
    grouped = OrderedDict()
    used = set()

    for cat_label, cat_terms in _SKILL_CATEGORIES.items():
        matched = []
        for skill in skills:
            if skill in used:
                continue
            low = skill.lower().strip()
            if low in cat_terms:
                matched.append(skill)
                used.add(skill)
        if matched:
            grouped[cat_label] = matched

    # Remaining skills → "Other"
    remaining = [s for s in skills if s not in used]
    if remaining:
        grouped["Other"] = remaining

    return grouped


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
    projects = cv_data.get("projects", [])

    # Normalize skills: scan flow returns {matched:[], missing:[], additional:[]}
    # form flow returns a flat list of strings
    skills = _flatten_skills(raw_skills)

    render_fn = {
        "modern": _render_modern,
        "minimal": _render_minimal,
    }.get(template, _render_classic)

    args = (personal, summary, experience, education, skills, certifications, projects)

    # First pass: normal spacing
    pdf = render_fn(*args, compact=False)

    # If content spills to 3+ pages and last page is mostly empty, retry compact
    if pdf.pages_count >= 3:
        last_page_fill = pdf.get_y() / pdf.h
        if last_page_fill < 0.4:
            pdf = render_fn(*args, compact=True)

    return pdf.output()


# ============================================================
# SHARED HELPERS
# ============================================================

def _render_grouped_skills(pdf, skills, line_height=5.5):
    """Render skills grouped by category with bold labels.

    Each category on its own line: **Category:** skill1, skill2, skill3
    """
    grouped = _group_skills(skills)
    for category, cat_skills in grouped.items():
        x_start = pdf.get_x()
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(31, 41, 55)
        label = _safe(f"{category}: ")
        pdf.write(line_height, label)
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(55, 65, 81)
        # multi_cell from current x position for the rest of the line
        skills_text = _safe(", ".join(cat_skills))
        pdf.multi_cell(0, line_height, skills_text, align='L')


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

def _render_classic(personal, summary, experience, education, skills, certifications, projects=None, compact=False):
    pdf = FPDF()
    m = 13 if compact else 15
    pdf.set_auto_page_break(auto=True, margin=m)
    pdf.add_page()
    pdf.set_margins(m, m, m)

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
        _render_grouped_skills(pdf, skills, line_height=5.5)
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

    # -- Projects (only rendered when non-empty) --
    if projects:
        _classic_section_header(pdf, "PROJECTS")
        for i, proj in enumerate(projects):
            name = _safe(proj.get("name", ""))
            url = _safe(proj.get("url", ""))
            tech = _safe(proj.get("technologies", ""))
            desc = _safe(proj.get("description", ""))

            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(31, 41, 55)
            header = name
            if url:
                header += f"  ({url})"
            pdf.cell(0, 6, header, new_x='LMARGIN', new_y='NEXT')

            if tech:
                pdf.set_font('Helvetica', 'I', 10)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 5, tech, new_x='LMARGIN', new_y='NEXT')

            if desc:
                _render_bullet_point(pdf, desc, indent_x=22, text_width=173)

            if i < len(projects) - 1:
                pdf.ln(2)
        pdf.ln(2)

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

    return pdf


def _classic_section_header(pdf, title, compact=False):
    """Section header with full-width underline separator."""
    if pdf.get_y() > 40:
        pdf.ln(5 if compact else 8)
    pdf.set_font('Helvetica', 'B', 14)
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

def _render_modern(personal, summary, experience, education, skills, certifications, projects=None, compact=False):
    pdf = FPDF()
    m = 13 if compact else 15
    pdf.set_auto_page_break(auto=True, margin=18 if compact else 20)
    pdf.add_page()
    pdf.set_margins(m, m, m)

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
            _render_grouped_skills(pdf, skills, line_height=5.5)

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

    # -- Projects (only rendered when non-empty) --
    if projects:
        _modern_section_header(pdf, "PROJECTS")
        for i, proj in enumerate(projects):
            name = _safe(proj.get("name", ""))
            url = _safe(proj.get("url", ""))
            tech = _safe(proj.get("technologies", ""))
            desc = _safe(proj.get("description", ""))

            def render_proj(n=name, u=url, t=tech, d=desc):
                pdf.set_font('Helvetica', 'B', 10)
                pdf.set_text_color(31, 41, 55)
                header = n
                if u:
                    header += f"  ({u})"
                pdf.cell(0, 6, header, new_x='LMARGIN', new_y='NEXT')
                if t:
                    pdf.set_font('Helvetica', '', 10)
                    pdf.set_text_color(107, 114, 128)
                    pdf.cell(0, 5, t, new_x='LMARGIN', new_y='NEXT')
                if d:
                    cur_margin = pdf.l_margin
                    _render_bullet_point(pdf, d, indent_x=cur_margin + 7,
                                         text_width=168, line_height=5.5, font_size=10)

            _modern_accent_block(pdf, render_proj)
            if i < len(projects) - 1:
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

    return pdf


def _modern_section_header(pdf, title, compact=False):
    """Uppercase section header in blue, no underline."""
    if pdf.get_y() > 40:
        pdf.ln(5 if compact else 8)
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

def _render_minimal(personal, summary, experience, education, skills, certifications, projects=None, compact=False):
    pdf = FPDF()
    m = 18 if compact else 20
    pdf.set_auto_page_break(auto=True, margin=22 if compact else 25)
    pdf.add_page()
    pdf.set_margins(m, m, m)

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
        _render_grouped_skills(pdf, skills, line_height=6)
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

    # -- Projects (only rendered when non-empty) --
    if projects:
        _minimal_section_header(pdf, "Projects")
        for i, proj in enumerate(projects):
            name = _safe(proj.get("name", ""))
            url = _safe(proj.get("url", ""))
            tech = _safe(proj.get("technologies", ""))
            desc = _safe(proj.get("description", ""))

            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(31, 41, 55)
            header = name
            if url:
                header += f"  ({url})"
            pdf.cell(0, 6, header, new_x='LMARGIN', new_y='NEXT')

            if tech:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(107, 114, 128)
                pdf.cell(0, 5, tech, new_x='LMARGIN', new_y='NEXT')

            pdf.ln(2)

            if desc:
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(55, 65, 81)
                old_l_margin = pdf.l_margin
                pdf.l_margin = 25
                pdf.set_x(25)
                pdf.multi_cell(155, 6, _safe(desc), align='L')
                pdf.l_margin = old_l_margin
                pdf.ln(1)

            if i < len(projects) - 1:
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

    return pdf


def _minimal_section_header(pdf, title, compact=False):
    """Simple bold header with generous spacing above, no separator."""
    if pdf.get_y() > 40:
        pdf.ln(6 if compact else 10)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 7, _safe(title), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

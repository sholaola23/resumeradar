"""
ResumeRadar -- CV Builder AI Module
Uses Claude Haiku to polish CV sections for ATS optimization.
Follows same pattern as ai_analyzer.py.
"""

import os
import json
import re
from anthropic import Anthropic


# ============================================================
# SECTION HEADING REGEXES
# ============================================================

# General section heading: matches UPPERCASE or Title Case headings,
# 8+ chars, on their own line. Allows trailing colon/dash.
_SECTION_HEADING_RE = re.compile(
    r'^\s*(?:[A-Z][A-Z\s&,/()\-:]{7,}|'                       # ALL CAPS: "PROFESSIONAL EXPERIENCE:"
    r'(?:[A-Z][a-z]+\s*(?:[&,/:\-]\s*)?){2,})\s*[:\-]?\s*$',  # Title Case: "Professional Experience:"
    re.MULTILINE
)

# Separate education vs certification heading regexes (prevents cross-triggering)
_EDU_HEADING_RE = re.compile(
    r'^\s*(?:EDUCATION|ACADEMIC\s+QUALIFICATIONS?|ACADEMIC\s+BACKGROUND|'
    r'EDUCATIONAL\s+BACKGROUND|EDUCATIONAL\s+QUALIFICATIONS?|'
    r'ACADEMIC\s+CREDENTIALS?|ACADEMIC\s+HISTORY)\s*$',
    re.MULTILINE | re.IGNORECASE
)
_CERT_HEADING_RE = re.compile(
    r'^\s*(?:CERTIFICATIONS?|PROFESSIONAL\s+TRAINING|'
    r'TRAINING\s*[&+]\s*QUALIFICATIONS?|PROFESSIONAL\s+QUALIFICATIONS?|'
    r'LICENSES?\s*[&+]?\s*CERTIFICATIONS?|ACCREDITATIONS?|CREDENTIALS?|'
    r'PROFESSIONAL\s+DEVELOPMENT)\s*$',
    re.MULTILINE | re.IGNORECASE
)
# Combined for truncation (both edu and cert sections need to survive)
_EDU_CERT_HEADING_RE = re.compile(
    _EDU_HEADING_RE.pattern + r'|' + _CERT_HEADING_RE.pattern,
    re.MULTILINE | re.IGNORECASE
)


# ============================================================
# SMART TRUNCATION
# ============================================================

def _smart_truncate_resume(text, max_chars=12000):
    """
    Section-aware resume truncation. Always preserves education and
    certification sections, even if they appear late in the document.
    Strict hard cap ensures output never exceeds max_chars.
    """
    if len(text) <= max_chars:
        return text

    matches = list(_EDU_CERT_HEADING_RE.finditer(text))
    marker = "\n\n[... some experience content omitted for length ...]\n\n"
    marker_len = len(marker)

    if matches:
        # Always anchor tail from first edu/cert heading
        section_start = matches[0].start()
        tail = text[section_start:]

        # Hard cap: total output must not exceed max_chars
        max_tail = max_chars - 1500 - marker_len  # reserve 1500 for head minimum
        if len(tail) > max_tail:
            tail = tail[:max_tail]

        head_budget = max_chars - len(tail) - marker_len
        head_budget = max(1500, head_budget)

        result = text[:head_budget] + marker + tail
        return result[:max_chars]  # strict hard cap

    # Fallback: no edu/cert headings found — simple head+tail
    head_len = 7000
    tail_len = max_chars - head_len - marker_len
    if tail_len < 1000:
        tail_len = 1000
        head_len = max_chars - tail_len - marker_len

    result = text[:head_len] + marker + text[-tail_len:]
    return result[:max_chars]  # strict hard cap


# ============================================================
# DETERMINISTIC FALLBACK EXTRACTOR
# ============================================================

def _fallback_extract_education_certs(resume_text, ai_result):
    """
    Deterministic fallback: extract education and certifications from
    raw resume text when AI misses them. Handles partial misses.

    Returns dict with raw_edu_count and raw_cert_count (section-level
    parsed entry counts, not global keyword counts).
    """
    counts = {"raw_edu_count": 0, "raw_cert_count": 0}

    # --- Education ---
    edu_entries = _extract_section_entries(resume_text, _EDU_HEADING_RE)
    counts["raw_edu_count"] = len(edu_entries)

    ai_edu = ai_result.get("education", [])
    if len(edu_entries) > len(ai_edu):
        # Merge missing entries (dedup by normalized institution+degree)
        existing_keys = set()
        for e in ai_edu:
            key = _normalize_for_dedup(
                (e.get("degree", "") + " " + e.get("institution", "")).strip()
            )
            if key:
                existing_keys.add(key)

        added = 0
        for raw_entry in edu_entries:
            raw_key = _normalize_for_dedup(raw_entry)
            if raw_key and raw_key not in existing_keys:
                # Parse into structured entry
                parsed = _parse_edu_entry(raw_entry)
                if parsed:
                    ai_edu.append(parsed)
                    existing_keys.add(raw_key)
                    added += 1

        if added > 0:
            ai_result["education"] = ai_edu
            print(f"CV Builder fallback: added {added} education entries")

    # --- Certifications ---
    cert_entries = _extract_section_entries(resume_text, _CERT_HEADING_RE)
    counts["raw_cert_count"] = len(cert_entries)

    ai_certs = ai_result.get("certifications", [])
    if len(cert_entries) > len(ai_certs):
        existing_keys = set()
        for c in ai_certs:
            key = _normalize_for_dedup(c.get("name", ""))
            if key:
                existing_keys.add(key)

        added = 0
        for raw_entry in cert_entries:
            raw_key = _normalize_for_dedup(raw_entry)
            if raw_key and raw_key not in existing_keys:
                parsed = _parse_cert_entry(raw_entry)
                if parsed:
                    ai_certs.append(parsed)
                    existing_keys.add(raw_key)
                    added += 1

        if added > 0:
            ai_result["certifications"] = ai_certs
            print(f"CV Builder fallback: added {added} certifications")

    return counts


def _extract_section_entries(text, heading_re):
    """
    Find a section by heading regex, extract text from heading to
    next section heading, then split into individual entries.
    """
    match = heading_re.search(text)
    if not match:
        return []

    section_start = match.end()

    # Find next section heading (any type) after this one
    next_heading = _SECTION_HEADING_RE.search(text, section_start + 1)
    if next_heading:
        section_text = text[section_start:next_heading.start()]
    else:
        section_text = text[section_start:]

    section_text = section_text.strip()
    if not section_text:
        return []

    # Split into entries: each entry starts with a line that has
    # a date pattern or degree/cert keyword
    entries = []
    current_entry = []

    # Date pattern: matches things like "Jan 2023", "2012", "May 2013:"
    date_pattern = re.compile(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
        r'January|February|March|April|June|July|August|September|'
        r'October|November|December)\s*\d{4}|\b\d{4}\b',
        re.IGNORECASE
    )

    # Entry-start indicators (degree/cert keywords)
    entry_start_pattern = re.compile(
        r'(?:B\.?S\.?c?|M\.?S\.?c?|B\.?A\.?|M\.?A\.?|Ph\.?D|MBA|'
        r'HND|OND|SSCE|WASSCE|GCE|Diploma|Certificate|'
        r'PMP|PRINCE2|ITIL|AWS|Azure|Google|Cisco|CompTIA|'
        r'Certified|Professional|Associate|Foundation)',
        re.IGNORECASE
    )

    for line in section_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue

        # Does this line look like the start of a new entry?
        is_new_entry = bool(
            date_pattern.search(stripped) or
            entry_start_pattern.match(stripped)
        )

        if is_new_entry and current_entry:
            entries.append(' '.join(current_entry))
            current_entry = [stripped]
        else:
            current_entry.append(stripped)

    if current_entry:
        entries.append(' '.join(current_entry))

    # Filter out very short entries (likely noise)
    return [e for e in entries if len(e) > 5]


def _parse_edu_entry(raw_text):
    """Parse a raw education entry text into structured dict."""
    if not raw_text or len(raw_text) < 5:
        return None

    # Try to extract date
    date_match = re.search(
        r'(\d{4})\s*[-\u2013\u2014]?\s*(\d{4})?|'
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}',
        raw_text, re.IGNORECASE
    )
    grad_date = date_match.group(0) if date_match else ""

    return {
        "degree": raw_text[:120].strip(),
        "institution": "",
        "graduation_date": grad_date,
        "details": ""
    }


def _parse_cert_entry(raw_text):
    """Parse a raw certification entry text into structured dict."""
    if not raw_text or len(raw_text) < 5:
        return None

    date_match = re.search(r'\d{4}', raw_text)
    cert_date = date_match.group(0) if date_match else ""

    return {
        "name": raw_text[:150].strip(),
        "issuer": "",
        "date": cert_date
    }


def _normalize_for_dedup(text):
    """Normalize text for dedup comparison: lowercase, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.lower().strip())


# ============================================================
# QUALITY ASSESSMENT
# ============================================================

def _assess_extraction_quality(resume_text, result, fallback_counts=None):
    """
    Assess extraction quality. Must be called AFTER _fallback_extract_education_certs()
    on the merged result.

    Uses section-level counts from fallback (not global keyword counts) to
    reduce false positives.

    Args:
        resume_text: original full resume text
        result: merged AI + fallback extraction result
        fallback_counts: dict with raw_edu_count and raw_cert_count from fallback extractor
    """
    warnings = []
    fallback_counts = fallback_counts or {}

    # --- Education: require heading + section-level entry count ---
    has_edu_heading = bool(_EDU_HEADING_RE.search(resume_text))
    raw_edu_count = fallback_counts.get("raw_edu_count", 0)
    edu_count = len(result.get("education", []))
    if has_edu_heading and raw_edu_count >= 1 and edu_count == 0:
        warnings.append("education_missing")
    elif has_edu_heading and raw_edu_count > edu_count:
        warnings.append("education_partial")

    # --- Certifications: require heading + section-level entry count ---
    has_cert_heading = bool(_CERT_HEADING_RE.search(resume_text))
    raw_cert_count = fallback_counts.get("raw_cert_count", 0)
    cert_count = len(result.get("certifications", []))
    if has_cert_heading and raw_cert_count >= 1 and cert_count == 0:
        warnings.append("certifications_missing")
    elif has_cert_heading and raw_cert_count > cert_count:
        warnings.append("certifications_partial")

    # --- Experience: advisory only (no payment block) ---
    exp_signals = len(re.findall(
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
        r'January|February|March|April|June|July|August|September|'
        r'October|November|December)?\s*\d{4}\s*[-\u2013\u2014]\s*'
        r'(?:Present|Current|\d{4})',
        resume_text, re.IGNORECASE
    ))
    exp_count = len(result.get("experience", []))
    if exp_signals >= 3 and exp_count <= 1:
        warnings.append("experience_missing")
    elif exp_signals > exp_count + 2:
        warnings.append("experience_partial")

    return warnings


# ============================================================
# POLISH CV SECTIONS (form-based flow)
# ============================================================

def polish_cv_sections(cv_data):
    """
    Use Claude Haiku to polish all CV sections for ATS optimization
    against the target job description.

    Args:
        cv_data: dict with personal, summary, experience, education,
                 skills, certifications, target_job_description

    Returns:
        dict with polished CV sections in the same structure
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key or api_key == "your-anthropic-api-key-here":
        return _get_fallback(cv_data)

    try:
        client = Anthropic(api_key=api_key)

        personal = cv_data.get("personal", {})
        summary = cv_data.get("summary", "")
        experience = cv_data.get("experience", [])
        education = cv_data.get("education", [])
        skills = cv_data.get("skills", [])
        certifications = cv_data.get("certifications", [])
        target_jd = cv_data.get("target_job_description", "")

        from datetime import datetime
        today = datetime.now().strftime('%B %Y')

        prompt = f"""You are an expert ATS resume writer. Today's date is {today}.

Polish and optimize this CV for ATS systems, tailored to the target job description.

TARGET JOB DESCRIPTION:
{target_jd[:3000]}

CURRENT CV DATA:
Name: {personal.get('full_name', '')}
Summary: {summary}
Experience: {json.dumps(experience[:5], indent=2)[:3500]}
Education: {json.dumps(education[:3], indent=2)[:500]}
Skills: {', '.join(skills[:30])}
Certifications: {json.dumps(certifications[:5], indent=2)[:500]}

STRICT RULES — YOU MUST FOLLOW ALL OF THESE:
1. NEVER add skills the person did not list. Only return the skills they provided.
2. NEVER invent metrics, numbers, percentages, or impact figures. If the person wrote "improved performance" do NOT change it to "improved performance by 40%". Only include numbers the person explicitly provided.
3. NEVER add new experience entries or bullets describing work the person did not mention.
4. NEVER fabricate certifications, degrees, or qualifications.
5. Keep education and certifications EXACTLY as provided — only fix obvious typos or formatting.
6. NEVER omit any entries. If the input has 5 jobs, return ALL 5. If it has 3 education entries, return ALL 3.

WHAT YOU SHOULD DO:
1. Polish the summary into a strong 2-3 sentence professional summary. Improve the WORDING only. Incorporate keywords from the job description naturally, but only where they truthfully describe the person's actual experience.
2. For each experience bullet:
   - Improve the wording: start with strong action verbs, tighten language, remove filler
   - Weave in relevant keywords from the job description WHERE they honestly fit
   - Keep each bullet to 1-2 lines
   - PRESERVE all original metrics and numbers exactly as given
   - If a bullet has no numbers, DO NOT add any — just improve the wording
3. Return the SAME skills list the person provided (reorder to prioritize JD-relevant skills first).
4. In "smart_suggestions", provide coaching advice (NOT new content for the CV). Tell the person:
   - Which bullets would benefit from adding measurable impact (e.g., "Your bullet about CI/CD pipelines would be stronger with a metric — how much did deployment time improve?")
   - Where they could quantify results (suggest they think about: team size, time saved, cost reduced, uptime improved, users served, etc.)
   - Any missing JD keywords they could truthfully add IF they have that experience

Respond with ONLY valid JSON in this exact structure:
{{
    "summary": "Polished professional summary (using only their real experience)",
    "experience": [
        {{
            "title": "Job Title (exactly as provided)",
            "company": "Company Name (exactly as provided)",
            "start_date": "Start Date (exactly as provided)",
            "end_date": "End Date (exactly as provided)",
            "bullets": ["Polished bullet 1", "Polished bullet 2"]
        }}
    ],
    "education": [
        {{
            "degree": "Degree (as provided)",
            "institution": "Institution (as provided)",
            "graduation_date": "Date (as provided)",
            "details": "Details (as provided, or empty string)"
        }}
    ],
    "skills": ["Only skills the person listed, reordered by JD relevance"],
    "certifications": [
        {{
            "name": "Cert Name (as provided)",
            "issuer": "Issuer (as provided)",
            "date": "Date (as provided)"
        }}
    ],
    "smart_suggestions": [
        "Coaching tip 1: which bullet to add impact to and what question to ask themselves",
        "Coaching tip 2: a missing JD keyword they could add IF they have that experience",
        "Coaching tip 3: another area where numbers would strengthen their CV"
    ]
}}

CRITICAL: Same number of experience and education entries as input. Do NOT invent new jobs, degrees, skills, or metrics. You are optimizing WORDING, not fabricating content."""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text

        # Parse JSON -- same pattern as ai_analyzer.py
        try:
            clean_text = response_text.strip()

            # Strip markdown code blocks
            if "```json" in clean_text:
                json_start = clean_text.index("```json") + 7
                closing = clean_text.find("```", json_start)
                if closing != -1:
                    clean_text = clean_text[json_start:closing]
                else:
                    clean_text = clean_text[json_start:]
            elif "```" in clean_text:
                json_start = clean_text.index("```") + 3
                closing = clean_text.find("```", json_start)
                if closing != -1:
                    clean_text = clean_text[json_start:closing]
                else:
                    clean_text = clean_text[json_start:]

            clean_text = clean_text.strip()

            # Repair truncated JSON
            if clean_text.startswith("{") and not clean_text.endswith("}"):
                last_quote = clean_text.rfind('"')
                if last_quote > 0:
                    last_complete = max(
                        clean_text.rfind('}'),
                        clean_text.rfind(']'),
                        clean_text.rfind('"', 0, last_quote),
                    )
                    if last_complete > 0:
                        clean_text = clean_text[:last_complete + 1]

                clean_text += "]" * max(0, clean_text.count("[") - clean_text.count("]"))
                clean_text += "}" * max(0, clean_text.count("{") - clean_text.count("}"))

            polished = json.loads(clean_text)

            # Merge polished data back with personal info (AI doesn't touch personal)
            result = {
                "personal": personal,
                "summary": polished.get("summary", summary),
                "experience": polished.get("experience", experience),
                "education": polished.get("education", education),
                "skills": polished.get("skills", skills),
                "certifications": polished.get("certifications", certifications),
                "smart_suggestions": polished.get("smart_suggestions", []),
                # Keep backward compat — frontend checks both fields
                "suggested_additions": polished.get("suggested_additions", []),
                "ai_polished": True,
            }
            return result

        except (json.JSONDecodeError, ValueError) as parse_error:
            print(f"CV Builder JSON parse error: {parse_error}")
            print(f"Raw response (first 300 chars): {response_text[:300]}")
            return _get_fallback(cv_data)

    except Exception as e:
        print(f"CV Builder Claude API error: {str(e)}")
        return _get_fallback(cv_data)


# ============================================================
# EXTRACT AND POLISH (upload / scan-to-CV flow)
# ============================================================

def extract_and_polish(resume_text, job_description, scan_keywords=None):
    """
    One-shot: extract structured CV from raw resume text AND polish for ATS.
    Used in the scan-to-CV flow so the user never fills a form.

    Args:
        resume_text: raw resume text (from uploaded PDF/DOCX)
        job_description: the target job posting text
        scan_keywords: optional dict with matched/missing keywords from the scan

    Returns:
        dict with full structured, polished CV data
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your-anthropic-api-key-here":
        return {"error": "AI service unavailable.", "ai_polished": False}

    try:
        client = Anthropic(api_key=api_key)

        from datetime import datetime
        today = datetime.now().strftime('%B %Y')

        keyword_context = ""
        if scan_keywords:
            matched = scan_keywords.get("matched", [])
            missing = scan_keywords.get("missing", [])
            if matched:
                keyword_context += f"\nKEYWORDS ALREADY IN RESUME: {', '.join(matched[:20])}"
            if missing:
                keyword_context += f"\nKEYWORDS MISSING FROM RESUME (weave these in naturally where truthful): {', '.join(missing[:20])}"

        # Smart truncation: preserves education/cert sections even in long resumes
        truncated_resume = _smart_truncate_resume(resume_text)

        prompt = f"""You are an expert ATS resume writer. Today is {today}.

I will give you a raw resume text and a target job description. Your job is to:
1. EXTRACT all structured information from the resume (name, email, phone, location, linkedin, summary, experience, education, skills, certifications)
2. POLISH the wording of every section for ATS systems, tailored to the target job description
3. Return clean, structured JSON

TARGET JOB DESCRIPTION:
{job_description[:3000]}
{keyword_context}

IMPORTANT — SECTION HEADING RECOGNITION:
Resumes use many different headings. You MUST recognize ALL of these as education:
  EDUCATION, ACADEMIC QUALIFICATIONS, ACADEMIC BACKGROUND, EDUCATIONAL BACKGROUND,
  EDUCATIONAL QUALIFICATIONS, ACADEMIC CREDENTIALS, ACADEMIC HISTORY
And ALL of these as certifications:
  CERTIFICATIONS, PROFESSIONAL TRAINING, TRAINING & QUALIFICATIONS,
  PROFESSIONAL QUALIFICATIONS, LICENSES & CERTIFICATIONS, ACCREDITATIONS,
  CREDENTIALS, PROFESSIONAL DEVELOPMENT

RAW RESUME TEXT:
{truncated_resume}

STRICT RULES — YOU MUST FOLLOW ALL OF THESE:
1. Only extract information that ACTUALLY EXISTS in the resume text. Do NOT add skills, experience, certifications, or qualifications that are not in the original resume.
2. NEVER invent or fabricate metrics, numbers, percentages, or impact figures. If the resume says "improved system performance", do NOT change it to "improved system performance by 35%". Only include numbers that are explicitly in the resume.
3. NEVER add experience bullets describing work not mentioned in the resume.
4. Keep education and certifications EXACTLY as they appear in the resume.
5. For skills: only extract skills the person actually listed or clearly demonstrated in their experience bullets. Do NOT guess at skills they "probably" have.
6. NEVER omit any entries. If the resume lists 5 jobs, return ALL 5. If it lists 3 education entries, return ALL 3. If it lists 4 certifications, return ALL 4. Completeness is critical.

WHAT YOU SHOULD DO:
- Extract personal info (name, email, phone, location, LinkedIn) from the resume header
- Write a polished 2-3 sentence professional summary using ONLY information from their resume. Incorporate JD keywords naturally but only where they truthfully describe actual experience.
- For each job, polish the bullet wording: strong action verbs, tighter language, weave in JD keywords WHERE they honestly fit. PRESERVE all original metrics exactly as written. If a bullet has no numbers, improve the wording only — do NOT add numbers.
- Compile skills into matched (in resume AND in JD), additional (in resume but not in JD). Do NOT include skills that are only in the JD but not in the resume.
- In "smart_suggestions", provide coaching tips (NOT content for the CV):
  - Which bullets would benefit from measurable impact and what questions to ask themselves
  - Advise them to think about: numbers, percentages, team sizes, time saved, cost reduced, users served
  - Any JD keywords they could add IF they genuinely have that experience (phrase as a question, e.g., "Do you have experience with Terraform? If so, add it to your skills.")

Respond with ONLY valid JSON:
{{
    "personal": {{
        "full_name": "Full Name",
        "email": "email or empty string",
        "phone": "phone or empty string",
        "location": "city, state or empty string",
        "linkedin": "linkedin url or empty string"
    }},
    "summary": "Polished summary using ONLY their real experience",
    "experience": [
        {{
            "title": "Job Title (as in resume)",
            "company": "Company Name (as in resume)",
            "start_date": "Start Date (as in resume)",
            "end_date": "End Date or Present (as in resume)",
            "bullets": ["Polished bullet with original metrics preserved", "Another polished bullet"]
        }}
    ],
    "education": [
        {{
            "degree": "Degree (as in resume)",
            "institution": "Institution (as in resume)",
            "graduation_date": "Date (as in resume)",
            "details": "Honors, GPA as in resume, or empty string"
        }}
    ],
    "skills": {{
        "matched": ["skills ACTUALLY in resume that match JD"],
        "missing": [],
        "additional": ["other skills ACTUALLY in resume"]
    }},
    "certifications": [
        {{
            "name": "Cert Name (as in resume)",
            "issuer": "Issuer or empty string",
            "date": "Date or empty string"
        }}
    ],
    "smart_suggestions": [
        "Coaching tip: which bullet to quantify and what to ask themselves",
        "Coaching tip: a JD keyword to consider adding IF they have that experience",
        "Coaching tip: where adding numbers would strengthen their CV"
    ]
}}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text

        # Parse JSON — same repair logic as polish_cv_sections
        try:
            clean_text = response_text.strip()

            if "```json" in clean_text:
                json_start = clean_text.index("```json") + 7
                closing = clean_text.find("```", json_start)
                clean_text = clean_text[json_start:closing] if closing != -1 else clean_text[json_start:]
            elif "```" in clean_text:
                json_start = clean_text.index("```") + 3
                closing = clean_text.find("```", json_start)
                clean_text = clean_text[json_start:closing] if closing != -1 else clean_text[json_start:]

            clean_text = clean_text.strip()

            if clean_text.startswith("{") and not clean_text.endswith("}"):
                last_quote = clean_text.rfind('"')
                if last_quote > 0:
                    last_complete = max(
                        clean_text.rfind('}'),
                        clean_text.rfind(']'),
                        clean_text.rfind('"', 0, last_quote),
                    )
                    if last_complete > 0:
                        clean_text = clean_text[:last_complete + 1]
                clean_text += "]" * max(0, clean_text.count("[") - clean_text.count("]"))
                clean_text += "}" * max(0, clean_text.count("{") - clean_text.count("}"))

            result = json.loads(clean_text)
            result["ai_polished"] = True

            # --- Post-extraction safety net ---
            # 1. Deterministic fallback: merge missing education/certs
            fallback_counts = _fallback_extract_education_certs(resume_text, result)

            # 2. Quality assessment on merged result with section-level counts
            warnings = _assess_extraction_quality(resume_text, result, fallback_counts)
            result["extraction_warnings"] = warnings

            return result

        except (json.JSONDecodeError, ValueError) as parse_error:
            print(f"CV extract+polish JSON parse error: {parse_error}")
            return {"error": "Failed to parse AI response.", "ai_polished": False}

    except Exception as e:
        print(f"CV extract+polish API error: {str(e)}")
        return {"error": "AI processing failed. Please try again.", "ai_polished": False}


def _get_fallback(cv_data):
    """Return original data unpolished when AI is unavailable."""
    return {
        "personal": cv_data.get("personal", {}),
        "summary": cv_data.get("summary", ""),
        "experience": cv_data.get("experience", []),
        "education": cv_data.get("education", []),
        "skills": cv_data.get("skills", []),
        "certifications": cv_data.get("certifications", []),
        "smart_suggestions": [],
        "suggested_additions": [],
        "ai_polished": False,
        "fallback_note": "AI polishing temporarily unavailable. Your original content was used.",
    }

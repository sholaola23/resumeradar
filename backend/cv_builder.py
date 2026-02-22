"""
ResumeRadar -- CV Builder AI Module
Uses Claude Haiku to polish CV sections for ATS optimization.
Follows same pattern as ai_analyzer.py.
"""

import os
import json
from anthropic import Anthropic


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
{target_jd[:2500]}

CURRENT CV DATA:
Name: {personal.get('full_name', '')}
Summary: {summary}
Experience: {json.dumps(experience[:5], indent=2)[:2000]}
Education: {json.dumps(education[:3], indent=2)[:500]}
Skills: {', '.join(skills[:30])}
Certifications: {json.dumps(certifications[:5], indent=2)[:500]}

STRICT RULES — YOU MUST FOLLOW ALL OF THESE:
1. NEVER add skills the person did not list. Only return the skills they provided.
2. NEVER invent metrics, numbers, percentages, or impact figures. If the person wrote "improved performance" do NOT change it to "improved performance by 40%". Only include numbers the person explicitly provided.
3. NEVER add new experience entries or bullets describing work the person did not mention.
4. NEVER fabricate certifications, degrees, or qualifications.
5. Keep education and certifications EXACTLY as provided — only fix obvious typos or formatting.

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
            max_tokens=4000,
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

        prompt = f"""You are an expert ATS resume writer. Today is {today}.

I will give you a raw resume text and a target job description. Your job is to:
1. EXTRACT all structured information from the resume (name, email, phone, location, linkedin, summary, experience, education, skills, certifications)
2. POLISH the wording of every section for ATS systems, tailored to the target job description
3. Return clean, structured JSON

TARGET JOB DESCRIPTION:
{job_description[:3000]}
{keyword_context}

RAW RESUME TEXT:
{resume_text[:5000]}

STRICT RULES — YOU MUST FOLLOW ALL OF THESE:
1. Only extract information that ACTUALLY EXISTS in the resume text. Do NOT add skills, experience, certifications, or qualifications that are not in the original resume.
2. NEVER invent or fabricate metrics, numbers, percentages, or impact figures. If the resume says "improved system performance", do NOT change it to "improved system performance by 35%". Only include numbers that are explicitly in the resume.
3. NEVER add experience bullets describing work not mentioned in the resume.
4. Keep education and certifications EXACTLY as they appear in the resume.
5. For skills: only extract skills the person actually listed or clearly demonstrated in their experience bullets. Do NOT guess at skills they "probably" have.

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
            max_tokens=4000,
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

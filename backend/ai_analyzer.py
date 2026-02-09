"""
AI-Powered Analysis Module
Uses Claude API for intelligent, contextual resume suggestions.
This is the "smart" part of our hybrid approach.
"""

import os
import json
from anthropic import Anthropic


def get_ai_suggestions(resume_text, job_description, keyword_results):
    """
    Use Claude API to generate intelligent, personalized resume suggestions.

    Args:
        resume_text: The extracted resume text
        job_description: The job description text
        keyword_results: Results from the keyword matching engine

    Returns:
        dict with AI-generated suggestions
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key or api_key == "your-anthropic-api-key-here":
        return _get_fallback_suggestions(keyword_results)

    try:
        client = Anthropic(api_key=api_key)

        # Build a focused prompt with the analysis context
        missing_technical = keyword_results.get("missing_keywords", {}).get("technical_skills", [])
        missing_soft = keyword_results.get("missing_keywords", {}).get("soft_skills", [])
        missing_certs = keyword_results.get("missing_keywords", {}).get("certifications", [])
        match_score = keyword_results.get("overall_score", 0)

        from datetime import datetime
        today = datetime.now().strftime('%B %Y')

        prompt = f"""You are an expert career coach and ATS (Applicant Tracking System) optimization specialist.
Today's date is {today}. Any dates from 2025 or earlier are in the PAST, not the future. Do NOT flag past dates as fake or future-dated.

Analyze this resume against the job description and provide specific, actionable suggestions.

RESUME:
{resume_text[:3000]}

JOB DESCRIPTION:
{job_description[:2000]}

KEYWORD ANALYSIS RESULTS:
- Overall Match Score: {match_score}%
- Missing Technical Skills: {', '.join(missing_technical[:15]) if missing_technical else 'None'}
- Missing Soft Skills: {', '.join(missing_soft[:10]) if missing_soft else 'None'}
- Missing Certifications: {', '.join(missing_certs[:5]) if missing_certs else 'None'}

IMPORTANT: Keep your response concise. Each string value should be 1-2 sentences max. Respond with ONLY valid JSON, no other text:
{{
    "summary": "2-3 sentence overall assessment",
    "strengths": ["Strength 1", "Strength 2", "Strength 3"],
    "critical_improvements": [
        {{
            "section": "Section name",
            "issue": "Brief issue",
            "suggestion": "Brief fix",
            "priority": "high"
        }}
    ],
    "keyword_suggestions": [
        {{
            "keyword": "Missing keyword",
            "where_to_add": "Section name",
            "how_to_add": "Brief example"
        }}
    ],
    "rewrite_suggestions": [
        {{
            "section": "Section name",
            "current_issue": "Brief issue",
            "suggested_approach": "Brief suggestion"
        }}
    ],
    "quick_wins": ["Quick win 1", "Quick win 2", "Quick win 3"]
}}

Limit: max 3 strengths, max 3 critical_improvements, max 4 keyword_suggestions, max 2 rewrite_suggestions, max 4 quick_wins. Keep each value SHORT."""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=3000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Parse the response
        response_text = message.content[0].text

        # Try to extract JSON from the response
        try:
            clean_text = response_text.strip()

            # Strip markdown code blocks (```json ... ``` or ``` ... ```)
            if "```json" in clean_text:
                json_start = clean_text.index("```json") + 7
                # Find the closing ``` — if missing (truncated), take everything after opening
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

            # If JSON is truncated (no closing brace), try to repair it
            if clean_text.startswith("{") and not clean_text.endswith("}"):
                # Count braces to find how many we need to close
                open_braces = clean_text.count("{") - clean_text.count("}")
                open_brackets = clean_text.count("[") - clean_text.count("]")

                # Trim to last complete value (before any cut-off string)
                last_quote = clean_text.rfind('"')
                if last_quote > 0:
                    # Check if we're mid-string — find a safe cut point
                    last_complete = max(
                        clean_text.rfind('}'),
                        clean_text.rfind(']'),
                        clean_text.rfind('"', 0, last_quote),
                    )
                    if last_complete > 0:
                        clean_text = clean_text[:last_complete + 1]

                # Close any open brackets/braces
                clean_text += "]" * max(0, clean_text.count("[") - clean_text.count("]"))
                clean_text += "}" * max(0, clean_text.count("{") - clean_text.count("}"))

            suggestions = json.loads(clean_text)
            suggestions["ai_powered"] = True
            return suggestions

        except (json.JSONDecodeError, ValueError) as parse_error:
            print(f"JSON parse error: {parse_error}")
            print(f"Raw response (first 300 chars): {response_text[:300]}")

            # Last resort: try to extract just the summary from raw text
            summary = response_text
            # Strip any markdown/JSON artifacts for display
            for prefix in ['```json', '```', '{', '"summary":', '"summary" :']:
                summary = summary.replace(prefix, '')
            summary = summary.replace('```', '').strip().strip('"').strip()
            # Take first sentence or two as summary
            if len(summary) > 300:
                cut = summary.find('.', 150)
                if cut != -1 and cut < 400:
                    summary = summary[:cut + 1]
                else:
                    summary = summary[:300] + '...'

            return {
                "summary": summary,
                "strengths": [],
                "critical_improvements": [],
                "keyword_suggestions": [],
                "rewrite_suggestions": [],
                "quick_wins": [],
                "ai_powered": True,
                "parse_note": "AI analysis completed but structured parsing had issues."
            }

    except Exception as e:
        error_msg = str(e)
        print(f"Claude API error: {error_msg}")

        # Return fallback suggestions if API fails
        fallback = _get_fallback_suggestions(keyword_results)
        fallback["api_error"] = "AI analysis temporarily unavailable. Showing rule-based suggestions."
        return fallback


def _get_fallback_suggestions(keyword_results):
    """
    Generate rule-based suggestions when AI is unavailable.
    Still useful, just not as personalized.
    """
    suggestions = {
        "summary": "",
        "strengths": [],
        "critical_improvements": [],
        "keyword_suggestions": [],
        "rewrite_suggestions": [],
        "quick_wins": [],
        "ai_powered": False,
    }

    score = keyword_results.get("overall_score", 0)
    missing_tech = keyword_results.get("missing_keywords", {}).get("technical_skills", [])
    missing_soft = keyword_results.get("missing_keywords", {}).get("soft_skills", [])
    missing_certs = keyword_results.get("missing_keywords", {}).get("certifications", [])

    # Generate summary based on score
    if score >= 80:
        suggestions["summary"] = f"Your resume is a strong match at {score}%. With a few targeted additions, you can push it even higher."
    elif score >= 60:
        suggestions["summary"] = f"Your resume is a decent match at {score}%, but there are notable gaps. Focus on adding missing technical keywords and you'll see a significant improvement."
    elif score >= 40:
        suggestions["summary"] = f"Your resume matches at {score}%. There's meaningful work needed to align it with this role. Focus on the missing technical skills and consider rewriting your summary section."
    else:
        suggestions["summary"] = f"Your resume currently matches at {score}%. This suggests either a significant skills gap or your resume isn't using the right terminology. Let's focus on keyword alignment first."

    # Generate keyword suggestions
    for keyword in missing_tech[:5]:
        suggestions["keyword_suggestions"].append({
            "keyword": keyword,
            "where_to_add": "Skills section or relevant experience bullets",
            "how_to_add": f"Add '{keyword}' to your skills section. If you have experience with it, add a bullet point describing a project or task where you used {keyword}."
        })

    # Generate quick wins
    quick_wins = []
    if missing_tech:
        quick_wins.append(f"Add these missing technical skills to your Skills section: {', '.join(missing_tech[:5])}")
    if missing_soft:
        quick_wins.append(f"Incorporate these soft skills into your experience bullets: {', '.join(missing_soft[:3])}")
    if missing_certs:
        quick_wins.append(f"If you hold any of these certifications, add them prominently: {', '.join(missing_certs[:3])}")
    quick_wins.append("Ensure your resume summary/objective mirrors the language of the job description.")
    quick_wins.append("Start each experience bullet point with a strong action verb (Led, Built, Improved, Designed).")

    suggestions["quick_wins"] = quick_wins

    return suggestions

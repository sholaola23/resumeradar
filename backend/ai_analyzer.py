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

        prompt = f"""You are an expert career coach and ATS (Applicant Tracking System) optimization specialist.

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

Please provide your analysis in the following JSON format (and ONLY valid JSON, no other text):
{{
    "summary": "A 2-3 sentence overall assessment of how well the resume matches the job",
    "strengths": [
        "List 2-4 specific strengths of this resume for this role"
    ],
    "critical_improvements": [
        {{
            "section": "Which resume section to change (e.g., Summary, Experience, Skills)",
            "issue": "What's wrong or missing",
            "suggestion": "Specific text or approach to fix it",
            "priority": "high"
        }}
    ],
    "keyword_suggestions": [
        {{
            "keyword": "The missing keyword",
            "where_to_add": "Which section to add it to",
            "how_to_add": "A specific example of how to naturally incorporate it"
        }}
    ],
    "rewrite_suggestions": [
        {{
            "section": "Section name",
            "current_issue": "What's wrong with the current version",
            "suggested_approach": "How to rewrite it (be specific, give examples)"
        }}
    ],
    "quick_wins": [
        "List 3-5 small changes that would have immediate impact"
    ]
}}"""

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Parse the response
        response_text = message.content[0].text

        # Try to extract JSON from the response
        try:
            # Handle case where response might have markdown code blocks
            if "```json" in response_text:
                json_start = response_text.index("```json") + 7
                json_end = response_text.index("```", json_start)
                response_text = response_text[json_start:json_end]
            elif "```" in response_text:
                json_start = response_text.index("```") + 3
                json_end = response_text.index("```", json_start)
                response_text = response_text[json_start:json_end]

            suggestions = json.loads(response_text.strip())
            suggestions["ai_powered"] = True
            return suggestions

        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, return the raw text in a structured format
            return {
                "summary": response_text[:500],
                "strengths": [],
                "critical_improvements": [],
                "keyword_suggestions": [],
                "rewrite_suggestions": [],
                "quick_wins": [],
                "ai_powered": True,
                "parse_note": "AI analysis completed but structured parsing had issues. See summary for details."
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

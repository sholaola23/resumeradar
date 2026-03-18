"""
Keyword Extraction & Matching Engine
The deterministic, rule-based part of our hybrid analysis.
Extracts keywords from job descriptions and matches them against resumes.
"""

import re
from collections import Counter, defaultdict

# ============================================================
# KEYWORD CATEGORIES
# These help us classify what type of keyword is missing,
# so we can give more specific advice.
# ============================================================

TECHNICAL_SKILLS = {
    # Cloud & Infrastructure
    "aws", "azure", "gcp", "google cloud", "amazon web services", "cloud computing",
    "ec2", "s3", "lambda", "rds", "vpc", "iam", "cloudformation", "cloudwatch",
    "terraform", "ansible", "puppet", "chef", "infrastructure as code", "iac",
    # Containers & Orchestration
    "docker", "kubernetes", "k8s", "containers", "ecs", "eks", "fargate",
    "openshift", "helm", "container orchestration",
    # CI/CD & DevOps
    "ci/cd", "cicd", "jenkins", "github actions", "gitlab ci", "circleci",
    "devops", "devsecops", "continuous integration", "continuous delivery",
    "continuous deployment", "argocd", "spinnaker",
    # Programming Languages
    "python", "javascript", "typescript", "java", "c#", "c++", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab",
    "bash", "shell scripting", "powershell",
    # Web & Frontend
    "react", "reactjs", "react.js", "angular", "vue", "vuejs", "vue.js",
    "next.js", "nextjs", "node.js", "nodejs", "express", "html", "css",
    "tailwind", "bootstrap", "sass", "webpack", "vite",
    # Backend & APIs
    "rest", "restful", "graphql", "api", "apis", "microservices",
    "serverless", "flask", "django", "spring boot", "fastapi",
    # Data & Databases
    "sql", "nosql", "postgresql", "mysql", "mongodb", "dynamodb", "redis",
    "elasticsearch", "cassandra", "oracle", "database", "data modeling",
    "etl", "data pipeline", "data warehouse", "redshift", "bigquery",
    "snowflake", "apache spark", "kafka", "airflow",
    # AI & ML
    "machine learning", "deep learning", "artificial intelligence", "ai", "ml",
    "nlp", "natural language processing", "computer vision", "tensorflow",
    "pytorch", "scikit-learn", "llm", "large language model", "generative ai",
    # Security
    "security", "cybersecurity", "encryption", "oauth", "sso", "identity",
    "access management", "zero trust", "penetration testing", "siem",
    "compliance", "gdpr", "hipaa", "soc2", "soc 2",
    # Monitoring & Observability
    "monitoring", "observability", "logging", "prometheus", "grafana",
    "datadog", "splunk", "new relic", "elk stack", "cloudtrail",
    # Networking
    "networking", "dns", "tcp/ip", "http", "https", "load balancing",
    "cdn", "cloudfront", "route 53", "vpn", "firewall",
    # Version Control
    "git", "github", "gitlab", "bitbucket", "version control",
    # Operating Systems
    "linux", "windows server", "unix", "macos",
    # Methodologies
    "agile", "scrum", "kanban", "waterfall", "sdlc", "lean",
    "sprint", "jira", "confluence",
    # Testing
    "testing", "unit testing", "integration testing", "test automation",
    "selenium", "cypress", "jest", "pytest", "qa", "quality assurance",
}

SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "problem-solving", "critical thinking", "analytical", "attention to detail",
    "time management", "project management", "stakeholder management",
    "mentoring", "coaching", "presentation", "public speaking",
    "negotiation", "conflict resolution", "decision making", "decision-making",
    "adaptability", "flexibility", "creativity", "innovation",
    "strategic thinking", "strategic planning", "customer facing",
    "cross-functional", "cross functional", "self-motivated", "self-starter",
    "results-driven", "results driven", "detail-oriented", "detail oriented",
    "fast-paced", "multitasking", "prioritization", "organizational",
    "interpersonal", "written communication", "verbal communication",
    "emotional intelligence", "relationship building",
}

CERTIFICATIONS = {
    # AWS
    "aws certified", "solutions architect", "cloud practitioner",
    "developer associate", "sysops administrator", "devops engineer",
    "data analytics", "database specialty", "security specialty",
    "machine learning specialty", "advanced networking",
    # Azure
    "azure certified", "az-900", "az-104", "az-305", "az-400",
    "azure fundamentals", "azure administrator", "azure solutions architect",
    # GCP
    "google cloud certified", "professional cloud architect",
    "associate cloud engineer", "professional data engineer",
    # Other
    "pmp", "prince2", "itil", "comptia", "cissp", "cism", "cisa",
    "ccna", "ccnp", "certified kubernetes", "cka", "ckad",
    "scrum master", "csm", "safe", "togaf",
}

EDUCATION_KEYWORDS = {
    "bachelor", "master", "mba", "phd", "doctorate", "degree",
    "computer science", "information technology", "engineering",
    "mathematics", "statistics", "data science", "business administration",
    "bsc", "msc", "b.s.", "m.s.", "b.a.", "m.a.",
}

# Education terms that are equivalent for matching purposes.
# If a JD says "bachelor" and a resume says "bsc", that's a match.
EDUCATION_EQUIVALENCES = [
    {"bachelor", "bsc", "b.s.", "b.a.", "ba", "bs", "degree"},
    {"master", "msc", "m.s.", "m.a.", "ma", "ms", "degree"},
    {"phd", "doctorate", "ph.d.", "degree"},
    {"mba", "degree"},
]

# Technical keywords that are also common English words.
# When extracting from JDs (strict mode), these need case-sensitive
# or compound-context matching to avoid false positives like
# "scalable" → "scala" or "rest of the team" → "rest".
_AMBIGUOUS_TECH = {
    "react":    re.compile(r'\bReact(?:\.?js)?\b'),
    "scala":    re.compile(r'\bScala\b'),
    "express":  re.compile(r'\bExpress(?:\.?js)?\b'),
    "rest":     re.compile(r'\bREST(?:ful)?\b|\brest\s*api\b|\brest\s*endpoint'),
    "identity": re.compile(r'\bidentity\s+(?:management|provider|access|federation|platform|governance|service|verification)\b', re.IGNORECASE),
    "go":       re.compile(r'\bGo(?:lang)?\b(?!\s+to\b|\s+ahead\b|\s+through\b|\s+over\b|\s+back\b|\s+on\b|\s+for\b|\s+with\b|\s+beyond\b)|\bgolang\b', re.IGNORECASE),
    "r":        re.compile(r'(?:^|[\s,;(/])\bR\b(?=[\s,;)/]|$)(?!.*&\s*D)'),
    "rust":     re.compile(r'\bRust\b'),
    "ruby":     re.compile(r'\bRuby\b'),
    "swift":    re.compile(r'\bSwift\b'),
    "chef":     re.compile(r'\bChef\b'),
    "puppet":   re.compile(r'\bPuppet\b'),
    "helm":     re.compile(r'\bHelm\b'),
    "flask":    re.compile(r'\bFlask\b'),
    "lean":     re.compile(r'\blean\s+(?:methodology|agile|six|management|startup|approach)\b|\bLean\b', re.IGNORECASE),
    "sprint":   re.compile(r'\bsprint(?:s)?\s+(?:planning|review|retro|goal|backlog|cycle|velocity)\b|\bsprints\b', re.IGNORECASE),
}


def _strip_jd_boilerplate(text):
    """Remove EEO/legal boilerplate sections from job description text."""
    markers = [
        r'equal\s+(?:opportunity|employment)',
        r'we\s+are\s+(?:an?\s+)?(?:equal|committed\s+to\s+(?:diversity|equal))',
        r'(?:does\s+not|will\s+not)\s+discriminate',
        r'affirmative\s+action',
        r'reasonable\s+accommodation',
        r'applicants\s+are\s+considered\s+without\s+regard',
    ]
    for marker in markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]
            break
    return text


ACTION_VERBS = {
    "led", "managed", "developed", "designed", "implemented", "built",
    "created", "launched", "delivered", "improved", "optimized", "reduced",
    "increased", "automated", "migrated", "deployed", "architected",
    "configured", "established", "spearheaded", "orchestrated", "streamlined",
    "transformed", "mentored", "coordinated", "analyzed", "evaluated",
    "resolved", "maintained", "supported", "collaborated", "contributed",
}


def extract_keywords_from_text(text, *, strict=False):
    """
    Extract all identifiable keywords from a piece of text.
    Returns a dict categorized by type.

    Args:
        strict: When True (use for JD text), applies stricter matching:
                - Strips EEO/legal boilerplate before extraction
                - Disables stem matching for technical skills
                - Uses case-sensitive/context patterns for ambiguous keywords
                This prevents false positives like "scalable" → "scala" or
                "rest of the team" → "rest".
    """
    original_text = text  # preserve case for ambiguous keyword checks
    if strict:
        text = _strip_jd_boilerplate(text)
        original_text = text

    text_lower = text.lower()

    found = {
        "technical_skills": set(),
        "soft_skills": set(),
        "certifications": set(),
        "education": set(),
        "action_verbs": set(),
    }

    # Technical skills: in strict mode, use case-sensitive patterns for
    # ambiguous keywords and disable stemming to avoid false positives.
    for skill in TECHNICAL_SKILLS:
        if strict and skill in _AMBIGUOUS_TECH:
            if _AMBIGUOUS_TECH[skill].search(original_text):
                found["technical_skills"].add(skill)
        else:
            if _keyword_in_text(skill, text_lower, use_stemming=not strict):
                found["technical_skills"].add(skill)

    for skill in SOFT_SKILLS:
        if _keyword_in_text(skill, text_lower):
            found["soft_skills"].add(skill)

    for cert in CERTIFICATIONS:
        if _keyword_in_text(cert, text_lower):
            found["certifications"].add(cert)

    for edu in EDUCATION_KEYWORDS:
        if _keyword_in_text(edu, text_lower):
            found["education"].add(edu)

    for verb in ACTION_VERBS:
        if _keyword_in_text(verb, text_lower):
            found["action_verbs"].add(verb)

    return found


def _keyword_in_text(keyword, text, *, use_stemming=True):
    """Check if a keyword exists in text using word boundary matching.
    Also checks common variations (e.g., collaborate/collaboration/collaborated).

    Args:
        use_stemming: When False, skip stem variation matching.  Disabled for
                      technical skills where stems cause false positives
                      (e.g., "scala" stem "scal" matching "scalable").
    """
    # Escape special regex characters in the keyword
    escaped = re.escape(keyword)
    # Use word boundaries for accurate matching
    pattern = r'\b' + escaped + r'\b'
    if re.search(pattern, text, re.IGNORECASE):
        return True

    if use_stemming:
        # Check stem variations for common word forms
        # e.g., "collaboration" should match "collaborate", "collaborated", "collaborating"
        stem = keyword.rstrip('esiond').rstrip('at').rstrip('ing')
        if len(stem) >= 4:
            stem_pattern = r'\b' + re.escape(stem) + r'\w*\b'
            if re.search(stem_pattern, text, re.IGNORECASE):
                return True

    return False


def _expand_education(keywords):
    """Expand education keywords with equivalences.
    E.g., if 'bachelor' is in the set, also add 'bsc', 'b.s.', 'b.a.' so
    that a resume with 'bsc' matches a JD requiring 'bachelor'."""
    expanded = set(keywords)
    for group in EDUCATION_EQUIVALENCES:
        if expanded & group:  # any overlap
            expanded |= group
    return expanded


def calculate_match(resume_keywords, job_keywords):
    """
    Calculate match percentage between resume and job description keywords.
    Uses a weighted scoring system that better reflects real ATS behavior:
    - Matching core/popular skills counts more than niche ones
    - Having a good spread across categories boosts the score
    - The score is calibrated so a typical good-fit candidate lands 60-80%

    Returns a detailed breakdown of matches and gaps.
    """
    results = {
        "overall_score": 0,
        "category_scores": {},
        "matched_keywords": {},
        "missing_keywords": {},
        "extra_keywords": {},
    }

    total_job_keywords = 0
    total_matched = 0

    # Weight categories differently (technical skills matter most for ATS)
    weights = {
        "technical_skills": 0.40,
        "soft_skills": 0.15,
        "certifications": 0.20,
        "education": 0.10,
        "action_verbs": 0.15,
    }

    for category in ["technical_skills", "soft_skills", "certifications", "education", "action_verbs"]:
        job_set = job_keywords.get(category, set())
        resume_set = resume_keywords.get(category, set())

        # Education: expand both sets with equivalences so "bsc" matches "bachelor".
        # Keep originals for display; use expanded sets for scoring.
        if category == "education":
            original_job_edu = set(job_set)
            original_resume_edu = set(resume_set)
            job_set = _expand_education(job_set)
            resume_set = _expand_education(resume_set)

        # Action verbs are special: we check if the RESUME uses strong verbs,
        # not whether the JD mentions them (JDs don't use action verbs).
        if category == "action_verbs":
            verb_count = len(resume_set)
            if verb_count >= 8:
                category_score = 100
            elif verb_count >= 5:
                category_score = 80
            elif verb_count >= 3:
                category_score = 60
            elif verb_count >= 1:
                category_score = 40
            else:
                category_score = 10

            results["category_scores"][category] = {
                "score": round(category_score, 1),
                "matched": verb_count,
                "total": max(verb_count, 8),  # Target: at least 8 action verbs
                "weight": weights[category],
            }
            results["matched_keywords"][category] = sorted(resume_set)
            results["missing_keywords"][category] = []
            results["extra_keywords"][category] = []
            continue

        if not job_set:
            results["category_scores"][category] = {
                "score": 100,
                "matched": 0,
                "total": 0,
                "weight": weights[category],
            }
            continue

        matched = job_set & resume_set
        missing = job_set - resume_set
        extra = resume_set - job_set

        # Use a curved scoring formula for technical skills
        # This prevents the score from being too punishing when job descriptions
        # list 30+ specific technologies (nobody knows them all)
        if category == "technical_skills" and len(job_set) > 8:
            raw_ratio = len(matched) / len(job_set)
            category_score = min(100, (raw_ratio ** 0.7) * 100)
        else:
            category_score = (len(matched) / len(job_set)) * 100 if job_set else 100

        results["category_scores"][category] = {
            "score": round(category_score, 1),
            "matched": len(matched),
            "total": len(job_set),
            "weight": weights[category],
        }

        # For education, display only the original terms and fix score counts
        if category == "education":
            edu_matched_display = sorted(
                original_job_edu - (original_job_edu - _expand_education(original_resume_edu)))
            edu_missing_display = sorted(
                original_job_edu - _expand_education(original_resume_edu))
            results["matched_keywords"][category] = edu_matched_display
            results["missing_keywords"][category] = edu_missing_display
            results["extra_keywords"][category] = sorted(
                original_resume_edu - _expand_education(original_job_edu))
            # Fix score to use original JD term count, not expanded
            orig_total = len(original_job_edu)
            orig_matched = len(edu_matched_display)
            category_score = (orig_matched / orig_total * 100) if orig_total else 100
            results["category_scores"][category] = {
                "score": round(category_score, 1),
                "matched": orig_matched,
                "total": orig_total,
                "weight": weights[category],
            }
        else:
            results["matched_keywords"][category] = sorted(matched)
            results["missing_keywords"][category] = sorted(missing)
            results["extra_keywords"][category] = sorted(extra)

        total_job_keywords += len(job_set)
        total_matched += len(matched)

    # Calculate weighted overall score
    weighted_score = 0
    total_weight = 0

    for category, data in results["category_scores"].items():
        if data["total"] > 0:
            weighted_score += data["score"] * data["weight"]
            total_weight += data["weight"]

    if total_weight > 0:
        results["overall_score"] = round(weighted_score / total_weight, 1)
    else:
        results["overall_score"] = 0

    # Simple match ratio (unweighted) for reference
    results["simple_match_ratio"] = round(
        (total_matched / total_job_keywords * 100) if total_job_keywords > 0 else 0, 1
    )
    results["total_job_keywords"] = total_job_keywords
    results["total_matched"] = total_matched
    results["total_missing"] = total_job_keywords - total_matched

    return results


def analyze_ats_formatting(resume_text):
    """
    Check for common ATS formatting issues in the resume.
    Returns issues, tips, contact info, AND a numerical formatting_score (0-100).
    """
    issues = []
    tips = []
    checklist = []  # individual check results for UI detail expansion

    # --- Check 1: Special characters (15 pts) ---
    has_special_chars = bool(re.search(r'[^\x00-\x7F]', resume_text))
    if has_special_chars:
        issues.append({
            "type": "warning",
            "message": "Special characters or symbols detected",
            "detail": "Some ATS systems struggle with emojis, icons, or non-standard characters. Consider replacing them with plain text."
        })
    checklist.append({"label": "No special characters", "passed": not has_special_chars, "points": 15 if not has_special_chars else 0})

    # --- Check 2: Section headings (25 pts) ---
    common_sections = ["experience", "education", "skills", "summary", "objective", "projects", "certifications"]
    found_sections = [s for s in common_sections if s in resume_text.lower()]
    required_sections = ["experience", "education", "skills"]
    missing_sections = [s for s in required_sections if s not in resume_text.lower()]

    if missing_sections:
        issues.append({
            "type": "warning",
            "message": f"Missing standard section headers: {', '.join(missing_sections).title()}",
            "detail": "ATS systems look for standard section headers to categorize your information. Make sure you have clearly labeled sections."
        })

    sections_found_ratio = (len(required_sections) - len(missing_sections)) / len(required_sections)
    section_points = round(sections_found_ratio * 25)
    checklist.append({"label": "Standard section headings", "passed": len(missing_sections) == 0, "points": section_points, "detail": f"{len(required_sections) - len(missing_sections)}/{len(required_sections)} required sections"})

    # --- Check 3: Word count in range (20 pts) ---
    word_count = len(resume_text.split())
    if word_count < 150:
        issues.append({
            "type": "warning",
            "message": "Resume seems very short",
            "detail": f"Your resume is about {word_count} words. Most effective resumes are 400-800 words. Consider adding more detail about your accomplishments."
        })
        wc_points = 5
    elif word_count > 1200:
        issues.append({
            "type": "info",
            "message": "Resume is quite long",
            "detail": f"Your resume is about {word_count} words. For most roles, 1-2 pages (400-800 words) is ideal. Consider trimming less relevant details."
        })
        wc_points = 10
    elif 400 <= word_count <= 800:
        wc_points = 20
    else:
        wc_points = 15
    checklist.append({"label": "Word count (400-800 ideal)", "passed": 400 <= word_count <= 800, "points": wc_points, "detail": f"{word_count} words"})

    # --- Check 4: Contact info (20 pts) ---
    has_email = bool(re.search(r'[\w.-]+@[\w.-]+\.\w+', resume_text))
    has_phone = bool(re.search(r'[\+]?[\d\s\-\(\)]{10,}', resume_text))
    has_linkedin = bool(re.search(r'linkedin', resume_text, re.IGNORECASE))

    if not has_email:
        issues.append({
            "type": "critical",
            "message": "No email address detected",
            "detail": "Make sure your email address is clearly visible at the top of your resume."
        })

    if not has_phone:
        tips.append("Consider adding a phone number to your contact information.")

    if not has_linkedin:
        tips.append("Adding your LinkedIn profile URL can strengthen your application.")

    contact_count = sum([has_email, has_phone, has_linkedin])
    contact_points = round((contact_count / 3) * 20)
    contact_parts = [x for x in [("Email" if has_email else ""), ("Phone" if has_phone else ""), ("LinkedIn" if has_linkedin else "")] if x]
    checklist.append({"label": "Contact information", "passed": contact_count == 3, "points": contact_points, "detail": ", ".join(contact_parts) if contact_parts else "None found"})

    # --- Check 5: Action verbs (20 pts) ---
    action_verb_count = sum(1 for verb in ACTION_VERBS if _keyword_in_text(verb, resume_text.lower()))
    if action_verb_count < 3:
        issues.append({
            "type": "warning",
            "message": "Few action verbs detected",
            "detail": "Strong resumes use action verbs (led, built, improved, managed) to describe accomplishments. Consider rewriting bullet points to start with impactful verbs."
        })

    if action_verb_count >= 8:
        verb_points = 20
    elif action_verb_count >= 5:
        verb_points = 15
    elif action_verb_count >= 3:
        verb_points = 10
    else:
        verb_points = 5
    checklist.append({"label": "Action verbs used", "passed": action_verb_count >= 5, "points": verb_points, "detail": f"{action_verb_count} found"})

    # Calculate formatting score (0-100)
    formatting_score = sum(item["points"] for item in checklist)
    formatting_score = max(0, min(100, formatting_score))

    # General tips
    tips.append("Use a clean, single-column layout for best ATS compatibility.")
    tips.append("Avoid headers and footers — some ATS systems can't read them.")
    tips.append("Save as PDF unless the application specifically requests DOCX.")

    return {
        "issues": issues,
        "tips": tips,
        "sections_found": found_sections,
        "word_count": word_count,
        "has_contact_info": {
            "email": has_email,
            "phone": has_phone,
            "linkedin": has_linkedin,
        },
        "formatting_score": formatting_score,
        "checklist": checklist,
    }


def check_bullet_quantification(resume_text):
    """
    Check resume bullets for measurable results (numbers, percentages, metrics).
    Returns flagged bullets and a quantification score.
    """
    lines = resume_text.split('\n')
    flagged = []
    quantified = []

    bullet_pattern = re.compile(r'^\s*[-*\u2022\u25e6\u25aa\u25ba]\s+|^\s*\d+[.)]\s+')
    metric_pattern = re.compile(
        r'\d+[\s]*[%$\u00a3\u20ac\u00a5]|'
        r'[$\u00a3\u20ac][\s]*\d|'
        r'\d+\s*(?:percent|million|billion|thousand|users|clients|projects|'
        r'team|members|employees|customers|revenue|sales|hours|days|weeks|'
        r'months|years|x\b)',
        re.IGNORECASE
    )

    # Get first 20 action verbs for startswith check
    action_verb_list = sorted(ACTION_VERBS)[:20]

    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 15:
            continue

        is_bullet = bool(bullet_pattern.match(stripped))
        starts_with_verb = any(stripped.lower().startswith(verb) for verb in action_verb_list)

        if is_bullet or starts_with_verb:
            has_metric = bool(metric_pattern.search(stripped))
            if has_metric:
                quantified.append(stripped)
            else:
                flagged.append(stripped)

    total_bullets = len(quantified) + len(flagged)
    quantified_count = len(quantified)

    if total_bullets == 0:
        score = 50
    else:
        ratio = quantified_count / total_bullets
        if ratio >= 0.6:
            score = 100
        elif ratio >= 0.4:
            score = 80
        elif ratio >= 0.2:
            score = 60
        elif ratio > 0:
            score = 40
        else:
            score = 15

    return {
        "score": score,
        "total_bullets": total_bullets,
        "quantified_count": quantified_count,
        "flagged_bullets": flagged[:8],
        "detail": f"{quantified_count}/{total_bullets} bullets include metrics" if total_bullets > 0 else "No bullet points detected",
    }


def calculate_recruiter_tips_score(resume_text, job_description=""):
    """
    Calculate a Recruiter Tips score (0-100) based on resume quality signals.
    """
    checklist = []

    # --- Measurable results (30 pts) ---
    quant = check_bullet_quantification(resume_text)
    if quant["score"] >= 80:
        mr_points = 30
    elif quant["score"] >= 60:
        mr_points = 20
    elif quant["score"] >= 40:
        mr_points = 15
    else:
        mr_points = 5
    checklist.append({
        "label": "Measurable results",
        "passed": quant["score"] >= 60,
        "points": mr_points,
        "detail": quant["detail"],
    })

    # --- Action verb density (25 pts) ---
    resume_lower = resume_text.lower()
    verb_count = sum(1 for verb in ACTION_VERBS if _keyword_in_text(verb, resume_lower))
    word_count = len(resume_text.split())

    if verb_count >= 10:
        av_points = 25
    elif verb_count >= 7:
        av_points = 20
    elif verb_count >= 4:
        av_points = 15
    else:
        av_points = 5
    checklist.append({
        "label": "Action verb usage",
        "passed": verb_count >= 7,
        "points": av_points,
        "detail": f"{verb_count} action verbs found",
    })

    # --- Resume length (20 pts) ---
    if 400 <= word_count <= 800:
        rl_points = 20
        length_ok = True
    elif 300 <= word_count <= 1000:
        rl_points = 15
        length_ok = True
    elif word_count < 200:
        rl_points = 5
        length_ok = False
    else:
        rl_points = 10
        length_ok = False
    checklist.append({
        "label": "Resume length",
        "passed": length_ok,
        "points": rl_points,
        "detail": f"{word_count} words (400-800 ideal)",
    })

    # --- Job title alignment (25 pts) ---
    jt_points = 15  # default when can't assess
    if job_description:
        jd_first_lines = ' '.join(job_description.split('\n')[:3]).lower()
        stopwords = {'the', 'and', 'for', 'are', 'our', 'you', 'will', 'with', 'this', 'that', 'have', 'from', 'your', 'about', 'who', 'can', 'all', 'has', 'not', 'but', 'what', 'been', 'looking', 'seeking', 'role', 'position', 'join', 'team'}
        title_words = [w for w in re.findall(r'\b[a-z]{3,}\b', jd_first_lines) if w not in stopwords][:10]

        if title_words:
            matches = sum(1 for w in title_words if w in resume_lower)
            ratio = matches / len(title_words)
            if ratio >= 0.5:
                jt_points = 25
            elif ratio >= 0.3:
                jt_points = 18
            elif ratio >= 0.1:
                jt_points = 10
            else:
                jt_points = 3
    checklist.append({
        "label": "Job title alignment",
        "passed": jt_points >= 18,
        "points": jt_points,
        "detail": "Resume aligns with job requirements" if jt_points >= 18 else "Consider tailoring resume to match the job title",
    })

    total_score = sum(item["points"] for item in checklist)
    total_score = max(0, min(100, total_score))

    return {
        "score": total_score,
        "checklist": checklist,
        "quantification": quant,
    }

"""
Keyword Extraction & Matching Engine
The deterministic, rule-based part of our hybrid analysis.
Extracts keywords from job descriptions and matches them against resumes.
"""

import re
from collections import Counter

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

ACTION_VERBS = {
    "led", "managed", "developed", "designed", "implemented", "built",
    "created", "launched", "delivered", "improved", "optimized", "reduced",
    "increased", "automated", "migrated", "deployed", "architected",
    "configured", "established", "spearheaded", "orchestrated", "streamlined",
    "transformed", "mentored", "coordinated", "analyzed", "evaluated",
    "resolved", "maintained", "supported", "collaborated", "contributed",
}


def extract_keywords_from_text(text):
    """
    Extract all identifiable keywords from a piece of text.
    Returns a dict categorized by type.
    """
    text_lower = text.lower()

    found = {
        "technical_skills": set(),
        "soft_skills": set(),
        "certifications": set(),
        "education": set(),
        "action_verbs": set(),
    }

    # Check each category
    for skill in TECHNICAL_SKILLS:
        if _keyword_in_text(skill, text_lower):
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


def _keyword_in_text(keyword, text):
    """Check if a keyword exists in text using word boundary matching.
    Also checks common variations (e.g., collaborate/collaboration/collaborated)."""
    # Escape special regex characters in the keyword
    escaped = re.escape(keyword)
    # Use word boundaries for accurate matching
    pattern = r'\b' + escaped + r'\b'
    if re.search(pattern, text, re.IGNORECASE):
        return True

    # Check stem variations for common word forms
    # e.g., "collaboration" should match "collaborate", "collaborated", "collaborating"
    stem = keyword.rstrip('esiond').rstrip('at').rstrip('ing')
    if len(stem) >= 4:
        stem_pattern = r'\b' + re.escape(stem) + r'\w*\b'
        if re.search(stem_pattern, text, re.IGNORECASE):
            return True

    return False


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
    """
    issues = []
    tips = []

    # Check for common ATS-unfriendly patterns
    if re.search(r'[^\x00-\x7F]', resume_text):
        # Has non-ASCII characters (emojis, special chars)
        issues.append({
            "type": "warning",
            "message": "Special characters or symbols detected",
            "detail": "Some ATS systems struggle with emojis, icons, or non-standard characters. Consider replacing them with plain text."
        })

    # Check for headers/sections
    common_sections = ["experience", "education", "skills", "summary", "objective", "projects", "certifications"]
    found_sections = [s for s in common_sections if s in resume_text.lower()]
    missing_sections = [s for s in ["experience", "education", "skills"] if s not in resume_text.lower()]

    if missing_sections:
        issues.append({
            "type": "warning",
            "message": f"Missing standard section headers: {', '.join(missing_sections).title()}",
            "detail": "ATS systems look for standard section headers to categorize your information. Make sure you have clearly labeled sections."
        })

    # Check resume length
    word_count = len(resume_text.split())
    if word_count < 150:
        issues.append({
            "type": "warning",
            "message": "Resume seems very short",
            "detail": f"Your resume is about {word_count} words. Most effective resumes are 400-800 words. Consider adding more detail about your accomplishments."
        })
    elif word_count > 1200:
        issues.append({
            "type": "info",
            "message": "Resume is quite long",
            "detail": f"Your resume is about {word_count} words. For most roles, 1-2 pages (400-800 words) is ideal. Consider trimming less relevant details."
        })

    # Check for contact info patterns
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

    # Check for action verbs in experience
    action_verb_count = sum(1 for verb in ACTION_VERBS if _keyword_in_text(verb, resume_text.lower()))
    if action_verb_count < 3:
        issues.append({
            "type": "warning",
            "message": "Few action verbs detected",
            "detail": "Strong resumes use action verbs (led, built, improved, managed) to describe accomplishments. Consider rewriting bullet points to start with impactful verbs."
        })

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
        }
    }

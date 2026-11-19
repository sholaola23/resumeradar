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
    "terraform", "pulumi", "ansible", "puppet", "chef", "infrastructure as code", "iac",
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
    "snowflake", "apache spark", "spark", "tableau", "kafka", "airflow",
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

# Fields of study. These only name a qualification when a degree word sits
# next to them ("BSc in Engineering"). On their own they are usually job
# titles, team names or skills: "Engineering Manager", "our data science
# team", "strong statistics".
EDUCATION_FIELDS = {
    "computer science", "information technology", "engineering",
    "mathematics", "statistics", "data science", "business administration",
}

# "master" is the degree only as "master's", "masters", "master of <subject>",
# "master in" or "master degree", never in "Scrum Master(s)", "master data"
# or "mastering".
_MASTER_DEGREE = re.compile(
    r"(?<!scrum\s)\bmaster(?:['’]?s\b|\s+in\b|\s+degree\b|\s+of\s+(?:science|arts|engineering|"
    r"business|philosophy|research|laws|public|education|fine|computer|data|information)\b)",
    re.IGNORECASE)
# "degree" is not "a high degree of autonomy" or "360-degree feedback".
_DEGREE_WORD = re.compile(r"(?<![\w-])degrees?\b(?!\s+of\b)", re.IGNORECASE)
_DOCTORATE = re.compile(r"\bdoctora(?:te|l)s?\b", re.IGNORECASE)

# Words that show a sentence is about a qualification.
_DEGREE_CUE = re.compile(
    r"\b(?:bachelor(?:['’]?s)?|mba|ph\.?d|[bm]sc|[bm]\.?eng|[bm]\.?tech|ba|bs|ma|(?<!\d)(?<!\d\s)ms(?=\s+(?:in|degree)\b)|"
    r"hnd|hnc|llb|bcom|(?:under|post)?graduates?|"
    r"diplomas?|university|college|studied|major(?:ing)?\s+in|qualified\s+in)\b|"
    r"\b[bm]\.(?:s|a|sc|eng|tech)\.",
    re.IGNORECASE)
# "Computer Science, Engineering or a related field" is one requirement: the
# fields are joined only by commas, "or", "and/or" or "/", with an "or" or
# "/" somewhere in the list, or the list ends with "or a related field".
_FIELD_JOIN = re.compile(r"\s*(?:,\s*)?(?:(?:and\s*/\s*)?or\s+|/\s*)?", re.IGNORECASE)
_RELATED_FIELD = re.compile(r"\s*,?\s*or\s+(?:an?\s+|any\s+)?(?:other\s+)?(?:related|similar|equivalent|relevant)\b",
                            re.IGNORECASE)
# On a CV the subject often sits a line or two from the degree or heading.
_CV_EDUCATION_CUE = re.compile(r"\b(?:education|academic|school|institute)\b", re.IGNORECASE)
_CV_EDUCATION_LINES = 3

# Sentence units for job descriptions. Abbreviations such as "B.S." and "e.g."
# do not end a sentence, so "B.S. in Computer Science" stays together.
_JD_SENTENCE_SPLIT = re.compile(
    r'(?<=[.!?])(?<!\.[A-Za-z]\.)(?<!\.[A-Za-z]{2}\.)(?<!\.[A-Za-z]{3}\.)(?<!\.[A-Za-z]{4}\.)\s+|[;\n]+')

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
    "spark":    re.compile(r'\bSpark\b|(?i:\bapache spark\b)'),
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
    if not strict:
        text_lower = _positive_evidence(text_lower)

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
            if _keyword_in_text(skill, text_lower, use_stemming=False):
                found["technical_skills"].add(skill)

    for skill in SOFT_SKILLS:
        if _keyword_in_text(skill, text_lower):
            found["soft_skills"].add(skill)

    for cert in CERTIFICATIONS:
        if _keyword_in_text(cert, text_lower):
            found["certifications"].add(cert)

    for edu in EDUCATION_KEYWORDS:
        if _education_in_text(edu, text_lower, strict=strict):
            found["education"].add(edu)
    if strict:
        found["education_alternatives"] = _field_alternatives(text_lower)

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
    return any(re.search(pattern, text, re.IGNORECASE)
               for pattern in _keyword_patterns(keyword, use_stemming=use_stemming))


def _keyword_patterns(keyword, *, use_stemming=True):
    """Regex patterns that count as evidence of a keyword, strongest first.

    Shared by matching and by locate_job_terms so the highlighted job text
    can never disagree with the keyword lists.
    """
    # Word boundaries that also work for names such as c++ and node.js
    patterns = [r'(?<!\w)' + re.escape(keyword) + r'(?!\w)']
    if use_stemming:
        # Stem variations for common word forms, e.g. "collaboration"
        # matches "collaborate", "collaborated", "collaborating"
        stem = keyword.rstrip('esiond').rstrip('at').rstrip('ing')
        if len(stem) >= 4:
            patterns.append(r'\b' + re.escape(stem) + r'\w*\b')
    return patterns


def _education_in_text(term, text, *, strict=False):
    """Check for an education term without stemming.

    Stemming turned "engineering" into "engineer", so every Engineer job title
    read as an engineering degree. Only the term itself or its plural counts.
    A field of study also needs a degree word nearby: in the same sentence of
    a job description (strict), or within a few lines on a CV.
    """
    pattern = _education_pattern(term)
    if term not in EDUCATION_FIELDS:
        return bool(pattern.search(text))
    if strict:
        return bool(_job_education_spans(term, text))
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if pattern.search(line):
            nearby = '\n'.join(lines[max(0, index - _CV_EDUCATION_LINES):index + _CV_EDUCATION_LINES + 1])
            if _has_degree_cue(nearby) or _CV_EDUCATION_CUE.search(nearby):
                return True
    return False


def _job_education_spans(term, text):
    """Where an education term counts in a job description, as (start, end).

    A field of study counts only in a sentence that also has a degree word.
    Shared by extraction and locate_job_terms, so the job view marks exactly
    the mentions that put the term in the keyword lists.
    """
    pattern = _education_pattern(term)
    if term not in EDUCATION_FIELDS:
        return [match.span() for match in pattern.finditer(text)]
    spans, start = [], 0
    for separator in list(_JD_SENTENCE_SPLIT.finditer(text)) + [None]:
        end = separator.start() if separator else len(text)
        sentence = text[start:end]
        if _has_degree_cue(sentence):
            spans.extend((start + m.start(), start + m.end()) for m in pattern.finditer(sentence))
        if separator:
            start = separator.end()
    return spans


def _field_alternatives(text):
    """Groups of fields a job description offers as a choice, as frozensets."""
    spans = sorted((start, end, field) for field in EDUCATION_FIELDS
                   for start, end in _job_education_spans(field, text))
    groups, run, has_or = [], [], False

    def close():
        fields = {field for _, _, field in run}
        if len(fields) > 1 and (has_or or _RELATED_FIELD.match(text, run[-1][1])):
            groups.append(frozenset(fields))

    for span in spans:
        joiner = text[run[-1][1]:span[0]] if run else ''
        if run and span[0] >= run[-1][1] and _FIELD_JOIN.fullmatch(joiner):
            has_or = has_or or bool(re.search(r'\bor\b|/', joiner))
            run.append(span)
            continue
        if run:
            close()
        run, has_or = [span], False
    if run:
        close()
    return groups


def _education_pattern(term):
    special = {"master": _MASTER_DEGREE, "degree": _DEGREE_WORD, "doctorate": _DOCTORATE}
    if term in special:
        return special[term]
    return re.compile(r'(?<!\w)' + re.escape(term) + r's?(?!\w)', re.IGNORECASE)


def _has_degree_cue(text):
    return bool(_DEGREE_CUE.search(text) or _MASTER_DEGREE.search(text) or _DEGREE_WORD.search(text)
                or _DOCTORATE.search(text))


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
    Uses a custom heuristic weighted scoring system:
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
        "action_verbs": 0.0,
    }

    for category in ["technical_skills", "soft_skills", "certifications", "education", "action_verbs"]:
        job_set = job_keywords.get(category, set())
        resume_set = resume_keywords.get(category, set())

        # Education: expand both sets with equivalences so "bsc" matches "bachelor".
        # Keep originals for display; use expanded sets for scoring.
        if category == "education":
            original_job_edu = set(job_set)
            original_resume_edu = set(resume_set)
            # One field from an "X or Y" list meets the requirement, so the
            # other fields in that list are no longer asked for.
            for group in job_keywords.get("education_alternatives", []):
                if group & original_resume_edu:
                    original_job_edu -= group - original_resume_edu
            job_set = set(original_job_edu)
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

        total_job_keywords += results["category_scores"][category]["total"]
        total_matched += results["category_scores"][category]["matched"]

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

    substantive_count = sum(len(job_keywords.get(category, ())) for category in
                            ("technical_skills", "soft_skills", "certifications", "education"))
    results["score_status"] = "estimated"
    results["score_explanation"] = (
        "Custom weighted keyword-overlap estimate, not an employer ATS score or hiring prediction. "
        "Action verbs are informational and do not contribute to this match estimate."
    )
    if substantive_count < 3:
        results["overall_score"] = None
        results["score_status"] = "insufficient_evidence"
        results["score_explanation"] = (
            "Fewer than three substantive job-description terms were recognized. "
            "The supported vocabulary is too limited to estimate this match reliably."
        )
    return results


def _positive_evidence(text):
    """Remove explicit skill denials without discarding unrelated achievements.

    Limit negation to recognized terms and experience verbs. Phrases such as
    'without downtime' and 'never missed a deadline' are positive evidence.
    This is intentionally a lexical check, not a semantic understanding claim.
    """
    vocabulary = TECHNICAL_SKILLS | SOFT_SKILLS | CERTIFICATIONS | EDUCATION_KEYWORDS
    term = r'(?<!\w)(?:' + '|'.join(re.escape(word) for word in sorted(vocabulary, key=len, reverse=True)) + r')(?!\w)'
    terms = term + r'(?:\s*(?:,\s*(?:or\s+|and\s+)?|and\s+|or\s+|/)\s*' + term + r')*'
    experience = r'(?:experience|expertise|knowledge|proficiency|familiarity|skills?|certification)'
    prefix = (r"\b(?:no|without|lack(?:s|ed|ing)?)\s+(?:" + experience + r"\s+(?:in|with|of)\s+)?"
              r"|\b(?:never|haven['’]t|hasn['’]t|do\s+not|don['’]t|doesn['’]t)\s+(?:used?|worked\s+with|learned|known|know)\s+"
              r"|\bnot\s+(?:familiar|experienced|proficient)\s+(?:in|with)\s+")
    text = re.sub(r'(?:' + prefix + r')' + terms + r'(?:\s+' + experience + r')?', ' ', text, flags=re.I)
    suffix = r"\s*[:—-]?\s*(?:no\s+" + experience + r"|not\s+(?:known|used|learned))\b"
    return re.sub(terms + suffix, ' ', text, flags=re.I)


def analyze_requirements(resume_text, job_description, match_results):
    """Return source-grounded missing-term advice; priorities are textual cues only.

    The original match arrays stay intact. Explicit comma/or tool alternatives
    are suppressed only when positive resume evidence satisfies that local list.
    """
    resume = extract_keywords_from_text(resume_text)
    sentences = _JD_SENTENCE_SPLIT.split(_strip_jd_boilerplate(job_description))
    evidence = []
    section_priority = "unspecified"
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        required = bool(re.search(r'\b(?:required|requirements|must|essential|mandatory)\b', sentence, re.I))
        preferred = bool(re.search(r'\b(?:preferred|desirable|bonus|nice[- ]to[- ]have|optional)\b', sentence, re.I))
        priority = "preferred" if preferred else "required" if required else section_priority
        heading = sentence.strip(' :#-*').lower()
        if re.fullmatch(r'(?:key |minimum |essential |required |preferred )?(?:requirements|qualifications|skills)|nice[- ]to[- ]have|desirable|bonus|optional', heading):
            section_priority = priority if required or preferred else 'required'
        elif heading in ('responsibilities', 'about the role', 'about us', 'benefits', 'what you will do'):
            section_priority = 'unspecified'
        if re.search(r"\b(?:not|never)\s+(?:required|necessary|essential)\b|\bno\s+.{0,40}\brequired\b", sentence, re.I):
            continue
        terms = extract_keywords_from_text(sentence, strict=True)
        alternatives = set()
        # A list such as Jenkins, GitHub Actions or CircleCI is one choice.
        # Limit candidates to contiguous tool names joined only by list syntax.
        positions = []
        for keyword in terms['technical_skills']:
            for match in re.finditer(r'(?<!\w)' + re.escape(keyword) + r'(?!\w)', sentence, re.I):
                positions.append((match.start(), match.end(), keyword))
        positions.sort(key=lambda item: (item[0], -item[1]))
        filtered = []
        for pos in positions:
            if not filtered or pos[0] >= filtered[-1][1]:
                filtered.append(pos)
        group = []
        has_or = False
        for pos in filtered + [(len(sentence) + 1, len(sentence) + 1, '')]:
            connector = sentence[group[-1][1]:pos[0]].strip() if group else ''
            connected = bool(pos[2] and group and re.fullmatch(r',?\s*(?:or)?\s*|/', connector, re.I))
            if not connected and group:
                keys = {item[2] for item in group}
                if has_or and keys & resume['technical_skills']:
                    alternatives |= keys
                group, has_or = [], False
            if connected and re.search(r'\bor\b|/', connector, re.I):
                has_or = True
            group.append(pos)
        evidence.append((sentence, priority, terms, alternatives))

    recommendations = []
    order = {'required': 0, 'unspecified': 1, 'preferred': 2}
    for category, missing in match_results.get('missing_keywords', {}).items():
        if category == 'action_verbs':
            continue
        for keyword in missing:
            sources = [(sentence, priority) for sentence, priority, terms, alternatives in evidence
                       if keyword in terms.get(category, set()) and keyword not in alternatives]
            if not sources:
                continue
            sentence, priority = min(sources, key=lambda source: order[source[1]])
            recommendations.append({
                'keyword': keyword, 'category': category, 'priority': priority,
                'reason': f'Job description: “{sentence}”',
                'suggestion': (f'If you hold this qualification, list {keyword} accurately in your education or certifications section.'
                               if category in ('education', 'certifications') else
                               f'If you have used {keyword}, add a relevant experience bullet describing the project and your contribution. Otherwise, leave it out.'),
            })
    category_order = {'technical_skills': 0, 'certifications': 1, 'education': 2, 'soft_skills': 3}
    return sorted(recommendations, key=lambda item: (order[item['priority']], category_order.get(item['category'], 4), item['keyword']))


def locate_job_terms(job_description, match_results):
    """Split the job description into segments marking each recognised term.

    Returns a list of {"text"} and {"text", "keyword", "category", "status"}
    segments whose text joins back to the job description exactly. A marked
    segment holding a shorter listed term also has "parts": the same text split
    into plain and marked pieces, so the inner term keeps its own status.
    Every listed term gets at least one mark carrying its own status. Status is
    "matched" or "missing", taken from match_results, so this view is the same
    evidence as the keyword lists. Text after the equal-opportunity boilerplate
    marker is returned unmarked because extraction ignores it. Action verbs are
    left out: they are scored from the CV, not the job description.
    """
    status = {}
    for label, key in (("matched", "matched_keywords"), ("missing", "missing_keywords")):
        for category, keywords in match_results.get(key, {}).items():
            if category != "action_verbs":
                for keyword in keywords:
                    status[(category, keyword)] = label

    scanned = _strip_jd_boilerplate(job_description)
    spans = []
    for (category, keyword), label in status.items():
        if category == "education":
            spans.extend((start, end, keyword, category, label)
                         for start, end in _job_education_spans(keyword, scanned))
            continue
        if category == "technical_skills" and keyword in _AMBIGUOUS_TECH:
            patterns = [_AMBIGUOUS_TECH[keyword]]
        else:
            patterns = [re.compile(pattern, re.IGNORECASE) for pattern in
                        _keyword_patterns(keyword, use_stemming=category != "technical_skills")]
        for pattern in patterns:
            found = False
            for match in pattern.finditer(scanned):
                start, end = match.span()
                # Some context patterns consume a leading separator, e.g. " R".
                while start < end and scanned[start] in " \t\r\n,;(/":
                    start += 1
                if start < end:
                    spans.append((start, end, keyword, category, label))
                    found = True
            if found:
                break  # same order as _keyword_in_text: exact form, then stem

    # Longest term wins where two overlap ("google cloud" over "cloud"). A
    # term inside it ("aws" in "aws certified") gets its own mark within that
    # one, so it keeps its own status.
    spans.sort(key=lambda span: (span[0], span[0] - span[1]))
    marks, cursor = [], 0
    for start, end, keyword, category, label in spans:
        if start >= cursor:
            marks.append({"span": (start, end), "keyword": keyword, "category": category,
                          "status": label, "inner": []})
            cursor = end
            continue
        outer = marks[-1]
        inner = outer["inner"]
        if keyword == outer["keyword"] or any(item["keyword"] == keyword for item in inner):
            continue
        if end <= cursor and (not inner or start >= inner[-1]["span"][1]):
            inner.append({"span": (start, end), "keyword": keyword, "category": category, "status": label})
        elif end > cursor:
            # Overlaps only partly ("cloud computing" after "Google Cloud"):
            # mark the part not already marked, so it keeps its own status.
            rest = cursor
            while rest < end and scanned[rest].isspace():
                rest += 1
            marks.append({"span": (rest, end), "keyword": keyword, "category": category,
                          "status": label, "inner": []})
            cursor = end

    def piece(mark):
        start, end = mark["span"]
        return {"text": job_description[start:end], "keyword": mark["keyword"],
                "category": mark["category"], "status": mark["status"]}

    segments, cursor = [], 0
    for mark in marks:
        start, end = mark["span"]
        if start > cursor:
            segments.append({"text": job_description[cursor:start]})
        segment = piece(mark)
        if mark["inner"]:
            parts, at = [], start
            for item in mark["inner"]:
                if item["span"][0] > at:
                    parts.append({"text": job_description[at:item["span"][0]]})
                parts.append(piece(item))
                at = item["span"][1]
            if at < end:
                parts.append({"text": job_description[at:end]})
            segment["parts"] = parts
        segments.append(segment)
        cursor = end
    if cursor < len(job_description):
        segments.append({"text": job_description[cursor:]})
    return segments


def analyze_ats_formatting(resume_text):
    """
    Check for common ATS formatting issues in the resume.
    Returns issues, tips, contact info, AND a numerical formatting_score (0-100).
    """
    issues = []
    tips = []
    checklist = []  # individual check results for UI detail expansion

    # --- Check 1: Special characters (15 pts) ---
    has_special_chars = bool(re.search(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFFFD]', resume_text))
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

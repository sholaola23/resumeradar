"""
ResumeRadar — rich per-role content for the programmatic SEO pages.

Written 27 Aug 2026 to replace the thin meta-swap pages (each page shared
~1,000 words with the homepage and differed by ~35). Every role gets a
genuine ~450-word page: role-specific intro, categorized keywords,
quantification tips, FAQs (also wired into FAQPage JSON-LD), and
related-role links. Update LASTMOD_ROLES in app.py when this file changes.

Framing rule (site-wide since 26 Aug 2026): ranking and AI screening,
never "the ATS auto-rejects you".
"""

ROLE_CONTENT = {
    "software-engineer": {
        "intro": [
            "Software engineering roles attract some of the highest application volumes in tech — several hundred per opening is normal, and screening software ranks every resume against the job description before a recruiter scrolls. What decides your rank is rarely raw talent: it is whether your resume states the stack, practices, and impact the posting asks for, in words the parser can match.",
            "Recruiters searching a candidate database also query by exact terms — \"React\", \"Kubernetes\", \"CI/CD\" — so a resume that says \"modern JavaScript frameworks\" instead of naming them is invisible to those searches. Scan your resume against a real posting below to see exactly which terms you are missing.",
        ],
        "categories": {
            "Languages & frameworks": ["Python", "Java", "JavaScript", "TypeScript", "React", "Node.js"],
            "Infrastructure & delivery": ["AWS", "Docker", "Kubernetes", "CI/CD", "Git", "microservices"],
            "Practices & fundamentals": ["REST APIs", "SQL", "Agile", "unit testing", "code review", "system design"],
        },
        "tips": [
            "Attach numbers to shipping: \"Delivered checkout service handling 40K daily orders\" ranks and reads better than \"worked on backend services\".",
            "Name the stack per role, not just in a skills list — rankers weight terms that appear inside experience bullets more heavily.",
            "If the posting says \"microservices\" and you built them, use that word — \"distributed services\" may not match the search query.",
        ],
        "faqs": [
            {"q": "What keywords do ATS systems look for in software engineer resumes?",
             "a": "The exact languages, frameworks, and practices in each job description — most commonly Python, Java, JavaScript/TypeScript, React, Node.js, AWS, Docker, Kubernetes, CI/CD, SQL, and Agile. Recruiters also run database searches on these exact terms, so name technologies explicitly instead of writing \"various modern frameworks\"."},
            {"q": "Do software engineers need a different resume for every application?",
             "a": "You need the same experience described in each posting's vocabulary. Keep one master resume, then adjust the summary and the most relevant bullets to mirror the target job description's terms — a 10-minute edit that measurably improves your ranking. ResumeRadar shows you exactly which terms to swap in."},
            {"q": "How long should a software engineer resume be?",
             "a": "One page under ~5 years of experience, two pages at most beyond that. Screening software has no length preference, but the human who reads the top-ranked resumes spends under a minute — put your strongest, most JD-relevant work in the top third of page one."},
        ],
        "related": ["frontend-developer", "backend-developer", "devops-engineer"],
    },
    "data-analyst": {
        "intro": [
            "Data analyst postings draw huge applicant pools because the role spans industries — and screening software does the first cut by ranking resumes against the posting's terms. Analysts are often filtered on tool names: a resume that says \"dashboarding and reporting\" without naming Tableau or Power BI will rank below one that names them, even with identical experience.",
            "The strongest analyst resumes read like their own dashboards: every bullet pairs a tool with a measured outcome. Scan yours against a live posting below to see which of the terms recruiters search for are missing.",
        ],
        "categories": {
            "Core tools": ["SQL", "Python", "Tableau", "Power BI", "Excel", "Looker"],
            "Techniques": ["data visualization", "ETL", "statistics", "A/B testing", "data modeling"],
            "Working with the business": ["stakeholder management", "reporting automation", "KPI definition", "requirements gathering"],
        },
        "tips": [
            "Quantify the decision, not just the dashboard: \"Built churn dashboard that redirected £40K of retention spend\" beats \"created dashboards in Tableau\".",
            "Name every tool at the point of use — \"automated weekly reporting in Python, saving 6 hours/week\" hits two searched terms in one bullet.",
            "Mirror the posting's dialect: if it says \"business intelligence\", use that phrase alongside the tool names.",
        ],
        "faqs": [
            {"q": "What keywords matter most on a data analyst resume?",
             "a": "SQL appears in almost every data analyst posting and is the most-searched term. After that: Python or R, a visualization tool (Tableau, Power BI, or Looker), Excel, ETL, statistics, and A/B testing. Match the specific tools each posting names — a Power BI shop searches for Power BI."},
            {"q": "Can I become a data analyst without a degree in data?",
             "a": "Yes — postings increasingly rank on demonstrated skills. A resume with real SQL projects, a portfolio dashboard, and quantified outcomes (\"analyzed 2M rows to identify a 12% pricing gap\") can outrank degree-holders with vague bullets. State the skills explicitly so the screening layer sees them."},
            {"q": "How do I quantify data analyst work on my resume?",
             "a": "Attach a number to the outcome of the analysis, not the analysis itself: rows or datasets handled, hours saved by automation, revenue or cost impact of a recommendation, adoption of a dashboard. \"Saved 6 hours weekly by automating reports in Python\" is the pattern."},
        ],
        "related": ["data-scientist", "business-analyst", "machine-learning-engineer"],
    },
    "project-manager": {
        "intro": [
            "Project management postings are ranked hard on methodology and certification terms — Agile, Scrum, PRINCE2, PMP — because recruiters use them as database search filters. A PM resume that describes \"leading delivery across teams\" without those exact words ranks below a thinner resume that names them.",
            "The second thing screeners and recruiters look for is scale: budgets, team sizes, timelines. \"Managed projects\" is unrankable; \"Delivered a £1.2M migration across 4 teams, 2 weeks early\" is a search hit and a story. Check your resume against a real posting below.",
        ],
        "categories": {
            "Methodologies & certifications": ["Agile", "Scrum", "PMP", "PRINCE2", "Kanban", "SAFe"],
            "Tools": ["Jira", "Confluence", "MS Project", "roadmapping tools"],
            "Delivery skills": ["stakeholder management", "risk management", "budgeting", "sprint planning", "cross-functional leadership"],
        },
        "tips": [
            "Lead bullets with scale: budget, headcount, duration — \"£800K budget, 12 engineers, 9 months\" ranks and reassures.",
            "Name your certifications with their acronyms (PMP, PRINCE2, CSM) — that is exactly how recruiters search.",
            "Show outcomes over activity: \"cut release cycle from 6 weeks to 2\" beats \"ran sprint ceremonies\".",
        ],
        "faqs": [
            {"q": "What keywords should a project manager resume include?",
             "a": "The methodology and certification terms recruiters filter on: Agile, Scrum, PMP, PRINCE2, plus stakeholder management, risk management, budgeting, and the tools (Jira, Confluence). Use the exact terms from each posting — an organization running SAFe searches for SAFe."},
            {"q": "Is PMP or PRINCE2 better for my resume?",
             "a": "Whichever your target market searches for: PMP dominates North American postings, PRINCE2 remains common in UK and public-sector roles, and Agile/Scrum certifications (CSM, PSM) appear across both. Scan your resume against postings you actually want to see which certification terms they use."},
            {"q": "How do I show project management impact without confidential numbers?",
             "a": "Use ranges and relative measures: \"budget in the seven figures\", \"cut delivery time by a third\", \"coordinated 5 workstreams\". Screeners and recruiters need magnitude, not audited figures — any honest number outranks \"responsible for project delivery\"."},
        ],
        "related": ["scrum-master", "product-manager", "business-analyst"],
    },
    "product-manager": {
        "intro": [
            "Product manager openings routinely draw 500+ applicants, and the ranking layer reads for a specific vocabulary: product strategy, roadmap, user research, OKRs, A/B testing. PM work is genuinely cross-functional, which tempts people into generic bullets — \"worked with engineering and design\" — that match nothing a recruiter searches.",
            "Strong PM resumes are metric-dense because the job is metric-driven: activation, retention, conversion, revenue. Every bullet that pairs a shipped thing with a moved number improves both your ranking and your interview conversation. See how your resume scores against a real PM posting below.",
        ],
        "categories": {
            "Product craft": ["product strategy", "roadmap", "user research", "PRD writing", "market research"],
            "Data & experimentation": ["A/B testing", "OKRs", "KPIs", "data-driven decision making", "analytics"],
            "Ways of working": ["Agile", "Scrum", "Jira", "stakeholder management", "go-to-market"],
        },
        "tips": [
            "Anchor every launch to a metric: \"Shipped onboarding redesign that lifted activation 18%\" is the canonical PM bullet.",
            "Use the posting's framework language — OKRs, north-star metric, discovery — where it honestly describes your work.",
            "Name the surface area: \"owned checkout for a 2M-user marketplace\" tells screeners scope instantly.",
        ],
        "faqs": [
            {"q": "What keywords do recruiters search for in product manager resumes?",
             "a": "Product strategy, roadmap, user research, A/B testing, OKRs, KPIs, stakeholder management, Agile, and go-to-market. Senior postings add \"product vision\" and \"P&L\". Mirror the exact phrases in each posting — \"experimentation\" and \"A/B testing\" are searched as different terms."},
            {"q": "How do I get past screening for PM roles without the PM title?",
             "a": "Rankers match on described work, not just titles. If you ran discovery, wrote specs, prioritized a backlog, or owned a metric as an engineer, analyst, or founder — say so in PM vocabulary and quantify the outcome. A \"Product work\" section that names roadmap and user research beats hoping a recruiter infers it."},
            {"q": "Should a product manager resume be one page?",
             "a": "One page up to ~7 years of experience is the safe default; two pages for genuinely senior scope. What matters to the screening layer is term coverage; what matters to the human is that your top three bullets carry your biggest shipped outcomes."},
        ],
        "related": ["project-manager", "business-analyst", "ux-designer"],
    },
    "cloud-engineer": {
        "intro": [
            "Cloud engineering resumes are ranked on named services and tooling more than almost any other role — postings list AWS, Terraform, Kubernetes explicitly, and screening software matches your resume term-for-term against that list. \"Cloud infrastructure experience\" without the platform names ranks near the bottom regardless of how good the work was.",
            "Certifications carry unusual search weight here too: recruiters filter databases on \"AWS Solutions Architect\" and \"Terraform Associate\" as exact strings. Scan your resume against a real cloud posting below to see which services, tools, and certs you are missing.",
        ],
        "categories": {
            "Platforms": ["AWS", "Azure", "GCP", "EC2", "S3", "Lambda", "IAM"],
            "Infrastructure as code & containers": ["Terraform", "CloudFormation", "Kubernetes", "Docker", "CI/CD"],
            "Operations": ["Linux", "networking", "serverless", "monitoring", "cost optimization", "high availability"],
        },
        "tips": [
            "Name services at the point of impact: \"cut monthly AWS spend 22% by rightsizing EC2 and moving batch jobs to Spot\" hits three searched terms.",
            "List certifications exactly as titled (\"AWS Certified Solutions Architect – Associate\") — recruiters search the official names.",
            "Quantify reliability: uptime, incident response time, deployment frequency — \"reduced incident response time 45%\" is the pattern.",
        ],
        "faqs": [
            {"q": "Which keywords matter most on a cloud engineer resume?",
             "a": "The specific platform and services (AWS, Azure, or GCP — plus EC2, S3, Lambda, IAM where true), Terraform or CloudFormation, Kubernetes, Docker, CI/CD, Linux, and networking. Postings name their stack precisely, and the ranking layer matches precisely — echo the services you have actually used."},
            {"q": "Do AWS certifications actually help a resume rank?",
             "a": "Yes — certifications are one of the few resume elements recruiters filter on as exact database searches. \"AWS Certified Solutions Architect\" in your certifications section is matched verbatim. They do not replace hands-on bullets, but they get your resume into searches it would otherwise miss."},
            {"q": "How do I show cloud cost optimization on my resume?",
             "a": "State the mechanism and the number: \"Reduced monthly cloud spend 22% through rightsizing, Savings Plans, and S3 lifecycle policies\". Cost optimization appears in most senior cloud postings, and a quantified bullet is both a keyword match and the strongest possible interview opener."},
        ],
        "related": ["devops-engineer", "solutions-architect", "backend-developer"],
    },
    "devops-engineer": {
        "intro": [
            "DevOps postings are keyword-dense by nature — CI/CD, Kubernetes, Terraform, Ansible, Prometheus — and the screening layer ranks resumes on coverage of that exact toolchain. Because the DevOps toolbox is so fragmented, recruiters search tools individually: naming Jenkins when the shop runs GitHub Actions costs you nothing, but naming neither costs you the search.",
            "The best DevOps bullets read as before/after: deployment frequency up, lead time down, incidents shortened. Scan your resume against a real posting below and see which pipeline, container, and monitoring terms you are missing.",
        ],
        "categories": {
            "Pipeline & automation": ["CI/CD", "Jenkins", "GitHub Actions", "Ansible", "infrastructure as code"],
            "Containers & cloud": ["Docker", "Kubernetes", "Terraform", "AWS", "Linux"],
            "Observability & reliability": ["monitoring", "Prometheus", "Grafana", "incident response", "SRE practices"],
        },
        "tips": [
            "Use DORA-shaped numbers: \"took deployments from weekly to daily\" or \"cut lead time from 3 days to 4 hours\" — screeners match the terms, humans remember the delta.",
            "Say \"infrastructure as code\" and name the tool — the phrase and the tool are searched separately.",
            "Include scripting languages (Python, Bash) — they appear in most DevOps postings and are easy to omit accidentally.",
        ],
        "faqs": [
            {"q": "What keywords do DevOps job postings screen for?",
             "a": "CI/CD, Docker, Kubernetes, Terraform, a pipeline tool (Jenkins or GitHub Actions), Ansible, AWS or another cloud, Linux, Python or Bash, and monitoring tools like Prometheus and Grafana. Coverage of the posting's specific toolchain is what the ranking layer measures."},
            {"q": "DevOps engineer vs SRE — does the title on my resume matter?",
             "a": "Less than the vocabulary. Many companies use the titles interchangeably; recruiters search the skills. If your work included SLOs, error budgets, or on-call incident response, use those SRE terms alongside your DevOps toolchain — you will surface in both searches."},
            {"q": "How do I quantify DevOps work?",
             "a": "Deployment frequency, lead time, change failure rate, time to restore — plus cost and toil: \"automated environment provisioning with Terraform, cutting setup from 2 days to 20 minutes\". Pick the two or three numbers that moved most and put them in your top bullets."},
        ],
        "related": ["cloud-engineer", "software-engineer", "solutions-architect"],
    },
    "data-scientist": {
        "intro": [
            "Data science postings sit at the intersection of research and engineering, and their screening reflects it: rankers look for the modeling vocabulary (machine learning, NLP, deep learning) and the delivery vocabulary (Python, SQL, deployment) together. Resumes that read purely academic — models without production, papers without pipelines — rank below ones that show both.",
            "Recruiters also search by library and technique: TensorFlow, PyTorch, scikit-learn, A/B testing. Naming your actual toolkit beats \"experience with modern ML frameworks\" every time. Scan your resume against a live posting below.",
        ],
        "categories": {
            "Modeling": ["machine learning", "deep learning", "NLP", "TensorFlow", "PyTorch", "scikit-learn"],
            "Data engineering & analysis": ["Python", "SQL", "pandas", "Spark", "statistics", "data visualization"],
            "Applied science": ["A/B testing", "experiment design", "model evaluation", "feature engineering"],
        },
        "tips": [
            "Pair every model with its business number: \"churn model that saved an estimated £300K annually\" outranks any architecture description.",
            "State dataset scale — \"trained on 40M events\" — magnitude is a signal recruiters scan for.",
            "If your models shipped, say \"deployed\" and name how (API, batch pipeline, SageMaker) — production terms separate you from research-only profiles.",
        ],
        "faqs": [
            {"q": "What keywords should a data scientist resume include?",
             "a": "Python, SQL, machine learning, and statistics appear in nearly every posting; TensorFlow or PyTorch, NLP, scikit-learn, Spark, and A/B testing follow closely. Match each posting's emphasis — a product analytics team searches for experimentation terms, an ML platform team for deployment terms."},
            {"q": "Do I need a PhD to rank for data science roles?",
             "a": "Most industry postings rank on demonstrated skills, not credentials — a resume with deployed models, quantified impact, and the right technical vocabulary outranks a publication list with vague bullets. Where postings do require advanced degrees, no keyword strategy substitutes; target accordingly."},
            {"q": "How is a data scientist resume different from a data analyst one?",
             "a": "The modeling layer: analysts emphasize SQL, dashboards, and business reporting; scientists add model building, ML libraries, and experiment design. If your experience spans both, let the target posting decide which vocabulary leads — and scan against it to check the balance."},
        ],
        "related": ["machine-learning-engineer", "data-analyst", "software-engineer"],
    },
    "ux-designer": {
        "intro": [
            "UX roles are screened on process vocabulary as much as tools: user research, wireframing, prototyping, usability testing. A portfolio carries the final decision, but the ranking layer decides whose portfolio gets opened — and it ranks the resume, not the case studies.",
            "Tool names matter as exact matches (Figma above all, currently), and accessibility has moved from nice-to-have to searched term. Scan your resume against a real UX posting below to see which process and tool terms you are missing.",
        ],
        "categories": {
            "Process": ["user research", "wireframing", "prototyping", "usability testing", "design thinking", "user flows"],
            "Tools": ["Figma", "Sketch", "Adobe XD", "design systems"],
            "Quality & structure": ["accessibility", "information architecture", "responsive design", "interaction design"],
        },
        "tips": [
            "Quantify research and outcomes: \"12 usability sessions that cut checkout drop-off 15%\" — the number makes the craft legible to non-designers.",
            "Name Figma (and any design-system work) explicitly — both are heavily searched.",
            "Write \"accessibility\" and the standard (WCAG) if you practice it — it is a growing filter term.",
        ],
        "faqs": [
            {"q": "What keywords do UX designer postings screen for?",
             "a": "User research, wireframing, prototyping, usability testing, Figma, information architecture, accessibility, and design systems. Product-heavy postings add user flows and interaction design. Use the process terms for work you have actually done — interviews will probe them."},
            {"q": "Does my resume matter if I have a strong portfolio?",
             "a": "Yes — the resume is what gets ranked and searched; the portfolio is what gets judged afterward. Treat the resume as the index to the portfolio: same project names, quantified outcomes, and the process vocabulary postings search for, with the portfolio link prominent."},
            {"q": "How do I quantify design work on a resume?",
             "a": "Task success, conversion, drop-off, support tickets, time-on-task: \"redesigned onboarding, raising completion from 61% to 84%\". Research effort counts too — participants interviewed, tests run. One honest number per project changes how the whole resume reads."},
        ],
        "related": ["product-manager", "frontend-developer", "business-analyst"],
    },
    "cybersecurity-analyst": {
        "intro": [
            "Security postings are screened on framework and tooling acronyms — SIEM, SOC, NIST, ISO 27001 — because compliance-driven hiring makes recruiters search those exact strings. A resume that describes \"monitoring and responding to threats\" without naming the SIEM, the frameworks, or the certifications ranks below one that does, even at equal skill.",
            "Certifications (Security+, CISSP, CEH) carry direct search weight here, and incident metrics carry the story: alerts triaged, dwell time cut, audits passed. Scan your resume against a real security posting below to see which terms you are missing.",
        ],
        "categories": {
            "Detection & response": ["SIEM", "SOC", "incident response", "threat intelligence", "IDS/IPS"],
            "Assessment & hardening": ["penetration testing", "vulnerability assessment", "firewall", "encryption", "risk assessment"],
            "Frameworks & compliance": ["NIST", "ISO 27001", "compliance", "audit readiness", "security awareness"],
        },
        "tips": [
            "Name your SIEM and stack: \"tuned Splunk detections, cutting false positives 40%\" hits searched terms and shows judgment.",
            "List certifications by exact name (CompTIA Security+, CISSP) — they are database filter fields.",
            "Quantify response: mean time to detect/respond, incidents handled per month, audit findings closed.",
        ],
        "faqs": [
            {"q": "What keywords do cybersecurity job postings screen for?",
             "a": "SIEM, SOC, incident response, vulnerability assessment, penetration testing, and the compliance frameworks the organization answers to (NIST, ISO 27001, SOC 2, PCI DSS). Certifications are searched as exact strings — list them precisely as titled."},
            {"q": "Can I rank for security roles coming from IT support or networking?",
             "a": "Yes — security postings match described work, and support/networking roles contain real security work: access management, patching, firewall changes, phishing response. Describe that work in security vocabulary (IAM, vulnerability remediation, incident response) and add a recognized certification to surface in searches."},
            {"q": "How do I show security impact without breaching confidentiality?",
             "a": "Use counts and deltas, not details: \"triaged 200+ alerts weekly\", \"cut mean time to respond from 4 hours to 45 minutes\", \"closed 30 audit findings ahead of ISO 27001 certification\". Magnitude signals competence; specifics stay internal."},
        ],
        "related": ["cloud-engineer", "devops-engineer", "solutions-architect"],
    },
    "business-analyst": {
        "intro": [
            "Business analyst is one of the most variable titles in hiring — process BA, data BA, technical BA — and the screening layer resolves the ambiguity by ranking on each posting's specific vocabulary: requirements gathering, process mapping, user stories, UAT, SQL. Matching the flavor of BA the posting describes matters more than seniority.",
            "The searched terms split between elicitation skills and tools: recruiters query \"requirements gathering\" and \"stakeholder management\" as phrases, and Jira, SQL, and Power BI as tools. Scan your resume against a live BA posting below to check both halves.",
        ],
        "categories": {
            "Analysis craft": ["requirements gathering", "process mapping", "user stories", "UAT", "gap analysis"],
            "Tools & data": ["SQL", "Jira", "Confluence", "Power BI", "Excel", "data analysis"],
            "Ways of working": ["stakeholder management", "Agile", "business intelligence", "workshop facilitation"],
        },
        "tips": [
            "Anchor bullets to the change delivered: \"documented 40 requirements that shaped a £500K system replacement\" beats \"gathered requirements\".",
            "Write \"user stories\" and \"UAT\" explicitly where true — both are common search phrases.",
            "If you query data yourself, say SQL by name; self-serve analysis is a major BA differentiator.",
        ],
        "faqs": [
            {"q": "What keywords should a business analyst resume include?",
             "a": "Requirements gathering, stakeholder management, user stories, UAT, process mapping, Agile, Jira, and — increasingly — SQL and Power BI. Match the posting's flavor: a data-leaning BA posting weights SQL and BI tools; a process-leaning one weights elicitation and mapping terms."},
            {"q": "Business analyst vs data analyst — which title fits my resume?",
             "a": "Lead with the work the target posting describes. If your days are requirements, workshops, and user stories, the BA vocabulary should dominate; if they are SQL, dashboards, and statistical analysis, you may rank higher against data analyst postings. Scan against both and compare scores."},
            {"q": "How do I quantify business analyst work?",
             "a": "Requirements documented, processes mapped, hours or cost the improved process saved, defects caught in UAT, project value delivered: \"mapped a 12-step onboarding process and cut handling time 30%\" is the pattern — the analysis tied to its outcome."},
        ],
        "related": ["project-manager", "data-analyst", "product-manager"],
    },
    "solutions-architect": {
        "intro": [
            "Architect postings are ranked on breadth signals: multiple platforms, system design vocabulary, and the non-functional words — scalability, high availability, security. Screening software reads for the architecture register; resumes still written in pure implementation language (\"built\", \"coded\") without design language (\"designed\", \"architected\") rank below the title's expectations.",
            "Cloud certifications at the professional level are heavily searched for this role, and so are the words \"trade-offs\", \"migration\", and \"stakeholder\". Scan your resume against a real architect posting below to see which design-level terms are missing.",
        ],
        "categories": {
            "Platforms & patterns": ["AWS", "Azure", "GCP", "microservices", "serverless", "API design"],
            "Design vocabulary": ["system design", "cloud architecture", "scalability", "high availability", "security architecture"],
            "Delivery & tooling": ["Terraform", "Kubernetes", "networking", "migration", "cost optimization"],
        },
        "tips": [
            "Write at design altitude: \"architected a multi-region failover design serving 5M users at 99.95% uptime\" — the register itself is a ranking signal.",
            "Name professional-level certifications in full — \"AWS Certified Solutions Architect – Professional\" is a searched string.",
            "Show the trade-off: \"chose event-driven over polling, cutting compute cost 35%\" demonstrates the actual job.",
        ],
        "faqs": [
            {"q": "What keywords do solutions architect postings screen for?",
             "a": "The platforms (AWS, Azure, GCP), system design, microservices, scalability, high availability, security, API design, and migration. Architecture postings also weight soft-skill phrases — stakeholder management, technical leadership — more than most engineering roles."},
            {"q": "How do I move my resume from engineer to architect?",
             "a": "Reframe your most design-heavy work in architecture vocabulary: decisions made, options weighed, systems that outlived you. Keep the engineering evidence but lead with \"designed\" and \"architected\" where honest — the ranking layer and the hiring manager both read for that register."},
            {"q": "Do certifications matter for architect roles?",
             "a": "More than for most roles: \"AWS Certified Solutions Architect\" (Associate or Professional) is one of the most-searched certification strings in tech hiring. It will not outweigh design experience, but it reliably gets your resume into recruiter searches."},
        ],
        "related": ["cloud-engineer", "devops-engineer", "software-engineer"],
    },
    "frontend-developer": {
        "intro": [
            "Frontend hiring is framework-driven, and so is its screening: React dominates posting counts, with TypeScript now named in most serious listings. The ranking layer matches framework names exactly — writing \"modern component-based frameworks\" instead of React and TypeScript is the single most common way strong frontend resumes underrank.",
            "Beyond frameworks, postings increasingly search performance and accessibility vocabulary: Core Web Vitals, WCAG, responsive design. Scan your resume against a real frontend posting below to see your term coverage.",
        ],
        "categories": {
            "Core stack": ["React", "TypeScript", "JavaScript", "HTML", "CSS", "Next.js"],
            "Quality & performance": ["accessibility", "responsive design", "testing", "Core Web Vitals", "webpack"],
            "Working practices": ["Git", "REST APIs", "component libraries", "code review", "Agile"],
        },
        "tips": [
            "Quantify the user-facing result: \"cut Largest Contentful Paint from 4.2s to 1.8s\" or \"raised Lighthouse score to 96\" — performance numbers are frontend's most credible metrics.",
            "Name the framework in each role's bullets, not only the skills list — in-context mentions rank higher.",
            "Say \"accessibility\" and \"WCAG\" if you practice them — both are rising filter terms.",
        ],
        "faqs": [
            {"q": "What keywords do frontend developer postings screen for?",
             "a": "React and TypeScript lead by a wide margin, then JavaScript, HTML, CSS, a meta-framework (Next.js), testing, responsive design, and accessibility. Vue and Angular shops search their own framework — mirror whichever the posting names."},
            {"q": "Should I list every framework I have touched?",
             "a": "List what you can interview on. The ranking layer rewards coverage, but the humans downstream probe it — a focused stack with quantified work outperforms a 20-item skills cloud that dilutes your strongest matches."},
            {"q": "How do I quantify frontend work?",
             "a": "Performance (load time, Web Vitals, Lighthouse), conversion on the surfaces you built, accessibility compliance, and adoption of shared components: \"built a component library adopted by 4 teams\" is as strong as any speed number."},
        ],
        "related": ["software-engineer", "backend-developer", "ux-designer"],
    },
    "backend-developer": {
        "intro": [
            "Backend postings are ranked on language plus data plus scale: a named language (Python, Java, Go, Node.js), the databases around it, and evidence you have run services under real load. Screeners match those terms directly, and recruiters search databases and message queues by product name — PostgreSQL, MongoDB, Redis, Kafka.",
            "The scale words are what separate ranked resumes: requests per second, records, latency. \"Built APIs\" says nothing a ranker or reader can weigh; \"designed REST APIs serving 12K requests/minute at p95 under 120ms\" says everything. Scan yours against a live posting below.",
        ],
        "categories": {
            "Languages & runtimes": ["Python", "Java", "Node.js", "Go"],
            "Data & messaging": ["SQL", "PostgreSQL", "MongoDB", "Redis", "message queues"],
            "Services & operations": ["REST APIs", "microservices", "Docker", "AWS", "CI/CD", "testing"],
        },
        "tips": [
            "Attach load numbers: requests/second, dataset size, p95 latency — scale vocabulary is backend's strongest ranking and interview signal.",
            "Name databases and queues by product — \"relational databases\" misses the PostgreSQL search.",
            "Show reliability work: \"cut API error rate from 2.1% to 0.3%\" reads as seniority.",
        ],
        "faqs": [
            {"q": "What keywords do backend developer postings screen for?",
             "a": "A primary language (Python, Java, Node.js, or Go), SQL plus a named database (PostgreSQL, MongoDB), REST APIs, microservices, Docker, a cloud platform, and CI/CD. Senior postings add message queues (Kafka, RabbitMQ) and caching (Redis)."},
            {"q": "Does it hurt to know several languages but be expert in one?",
             "a": "No — lead with your expert language in your summary and strongest bullets, and list the others honestly. Rankers reward the coverage; interviews reward the depth. What underranks you is naming none prominently and writing \"polyglot engineer\" instead."},
            {"q": "How do I show scale if my company was small?",
             "a": "Scale is relative — use the real numbers you have: \"grew the API from 10 to 400 daily active integrations\", \"processed 3M records nightly on a two-person team\". Small-company resumes win on breadth: own the fact that you built, deployed, and operated the service end to end."},
        ],
        "related": ["software-engineer", "devops-engineer", "cloud-engineer"],
    },
    "scrum-master": {
        "intro": [
            "Scrum Master screening is certification-forward: CSM, PSM, and SAFe are searched as exact strings, and the methodology vocabulary — sprint planning, retrospectives, velocity, Kanban — forms the ranking baseline. Because the role's output is a team's output, resumes that only list ceremonies run rank below ones that show what the team's delivery did under their facilitation.",
            "The strongest Scrum Master bullets are team-delta bullets: predictability up, cycle time down, blockers cleared faster. Scan your resume against a real posting below to see which methodology and tooling terms you are missing.",
        ],
        "categories": {
            "Framework & ceremonies": ["Scrum", "sprint planning", "retrospectives", "Kanban", "SAFe", "user stories"],
            "Metrics & tooling": ["velocity", "burndown", "Jira", "Confluence", "cycle time"],
            "Coaching craft": ["coaching", "facilitation", "servant leadership", "cross-functional teams", "impediment removal"],
        },
        "tips": [
            "Show the team's delta: \"raised sprint predictability from 60% to 90% commitment hit-rate over two quarters\" — facilitation proven by outcomes.",
            "List certifications by acronym and full name (CSM — Certified ScrumMaster); both forms are searched.",
            "Name the scale: teams coached, team sizes, and whether you worked within SAFe or scaled setups.",
        ],
        "faqs": [
            {"q": "What keywords do Scrum Master postings screen for?",
             "a": "Scrum, Agile, sprint planning, retrospectives, coaching, facilitation, Jira, velocity, and Kanban — plus certifications (CSM, PSM, SAFe) as exact search strings. Enterprise postings weight SAFe heavily; startups rarely mention it."},
            {"q": "Scrum Master vs Agile Coach on a resume — which should I use?",
             "a": "Use the title your target postings use, and let the vocabulary cover both: coaching, facilitation, and team metrics appear in each. If you have coached multiple teams or leaders rather than embedded with one team, the coach vocabulary (enterprise agility, coaching leaders) may rank you higher for those roles."},
            {"q": "How do I quantify Scrum Master impact?",
             "a": "Through the team's numbers: velocity stability, sprint commitment hit-rate, cycle time, defect escape rate, time-to-resolve blockers. \"Cut average blocker resolution from 3 days to same-day by restructuring dependencies with a partner team\" is the model bullet."},
        ],
        "related": ["project-manager", "product-manager", "business-analyst"],
    },
    "machine-learning-engineer": {
        "intro": [
            "ML engineering postings are screened on the production vocabulary that separates the role from research: MLOps, model deployment, feature engineering, plus the frameworks (PyTorch, TensorFlow) and the serving infrastructure (Kubernetes, SageMaker). Rankers read for both halves — models and the systems that run them.",
            "LLM terms have joined the searched set fast: fine-tuning, RAG, inference optimization appear in a growing share of postings. Scan your resume against a real ML posting below to check your coverage across modeling, infrastructure, and the new LLM vocabulary.",
        ],
        "categories": {
            "Modeling": ["Python", "PyTorch", "TensorFlow", "deep learning", "NLP", "computer vision", "scikit-learn"],
            "Production ML": ["MLOps", "model deployment", "feature engineering", "AWS SageMaker", "Kubernetes", "Docker"],
            "Emerging": ["LLM", "fine-tuning", "RAG", "inference optimization", "model monitoring"],
        },
        "tips": [
            "Pair model and serving numbers: \"deployed a ranking model serving 30M daily predictions at p99 under 50ms\" covers both searched halves in one bullet.",
            "Say \"MLOps\" where true — pipelines, CI/CD for models, monitoring — it is the role's highest-weight differentiator term.",
            "Quantify model impact in product terms: CTR lift, fraud caught, cost per inference reduced.",
        ],
        "faqs": [
            {"q": "What keywords do ML engineer postings screen for?",
             "a": "Python, PyTorch or TensorFlow, MLOps, model deployment, feature engineering, Docker, Kubernetes, and a cloud ML platform (SageMaker, Vertex AI). LLM-era terms — fine-tuning, RAG, inference optimization — now appear in a large share of postings and are worth naming where honest."},
            {"q": "ML engineer vs data scientist — how should my resume differ?",
             "a": "ML engineering resumes lead with production: deployment, serving latency, pipelines, monitoring. Data science resumes lead with analysis and modeling insight. If you do both, mirror the target posting — the same experience ranks differently depending on which vocabulary carries your top bullets."},
            {"q": "How do I show LLM experience credibly?",
             "a": "Name the technique and the measured result: \"cut support handling time 40% with a RAG pipeline over 12K internal documents\" or \"reduced inference cost 60% by quantizing and batching\". Specific mechanisms plus numbers separate real LLM work from keyword-chasing."},
        ],
        "related": ["data-scientist", "software-engineer", "devops-engineer"],
    },
}


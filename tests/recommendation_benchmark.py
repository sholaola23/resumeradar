"""Small, hand-labelled release benchmark; synthetic cases are not real applicants.

Run: .venv/bin/python tests/recommendation_benchmark.py
Optional: --private-cv-content /path/to/cv_content.py
The private file is parsed as literals, never executed or copied into the report.
"""
import argparse
import ast
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import keyword_engine as engine

# Expectations are manually labelled from the text, not derived from engine output.
# Each missing term must be grounded in the JD and correctly prioritized.
CASES = [
    ('cloud-gap', 'Built Python services on AWS using Docker.',
     'Requirements\nAWS Python Docker Kubernetes\nNice to Have\nTerraform',
     {'kubernetes': 'required', 'terraform': 'preferred'}, {'aws', 'python', 'docker'}),
    ('ci-alternatives', 'Built CI/CD pipelines with GitHub Actions and Python.',
     'Requirements\nPython Docker Kubernetes\nJenkins, GitHub Actions or CircleCI',
     {'docker': 'required', 'kubernetes': 'required'}, {'jenkins', 'circleci'}),
    ('career-change', 'Customer support analyst using Excel and SQL for reporting.',
     'Requirements\nSQL Python Tableau\nNice to Have\nDocker',
     {'python': 'required', 'tableau': 'required', 'docker': 'preferred'}, {'sql'}),
    ('negated-skill', 'Built Python and Docker services. No Kubernetes experience.',
     'Requirements\nPython Docker Kubernetes',
     {'kubernetes': 'required'}, {'python', 'docker'}),
    ('negative-outcome', 'Deployed Kubernetes without downtime. Built Python APIs with no outages. Docker.',
     'Requirements\nPython Docker Kubernetes', {}, {'python', 'docker', 'kubernetes'}),
    ('backend-punctuation', 'Built C++ and Node.js services with PostgreSQL.',
     'Requirements\nC++ Node.js PostgreSQL Redis', {'redis': 'required'}, {'c++', 'node.js', 'postgresql'}),
    ('optional-only', 'Built Python services using Docker and Kubernetes.',
     'Requirements\nPython Docker Kubernetes\nNice to Have\nPulumi Ansible',
     {'pulumi': 'preferred', 'ansible': 'preferred'}, {'python', 'docker'}),
    ('explicit-exclusion', 'Python Docker Kubernetes platform engineer.',
     'Requirements\nPython Docker Kubernetes\nJenkins is not required.', {}, {'jenkins'}),
    ('data-gap', 'Built SQL reports and Python pipelines with AWS.',
     'Requirements\nSQL Python AWS Spark\nNice to Have\nKafka',
     {'spark': 'required', 'kafka': 'preferred'}, {'sql', 'python', 'aws'}),
    ('no-stem-invention', 'Built scalable Python services and reacted quickly using Docker.',
     'Requirements\nPython Docker Scala React',
     {'scala': 'required', 'react': 'required'}, {'python', 'docker'}),
    ('nontechnical-florist', 'Arranged bouquets and cared for seasonal flowers.',
     'Arrange bouquets and care for seasonal blooms in our shop.', {}, set()),
    ('international-name', 'José Ọlúṣọlá\nExperience\nBuilt Python and AWS services.\nEducation\nSkills\nDocker',
     'Requirements\nPython AWS Docker Kubernetes', {'kubernetes': 'required'}, {'python', 'aws', 'docker'}),
]


def evaluate(case):
    name, resume, jd, expected, forbidden = case
    result = engine.calculate_match(engine.extract_keywords_from_text(resume),
                                    engine.extract_keywords_from_text(jd, strict=True))
    recommendations = engine.analyze_requirements(resume, jd, result)
    actual = {item['keyword']: item['priority'] for item in recommendations}
    failures = []
    for term, priority in expected.items():
        if actual.get(term) != priority:
            failures.append(f'{term}: expected {priority}, got {actual.get(term)}')
    for term in forbidden & actual.keys():
        failures.append(f'unsupported recommendation: {term}')
    for item in recommendations:
        source = item['reason'].removeprefix('Job description: “').removesuffix('”')
        if source not in jd or item['keyword'] not in source.lower():
            failures.append(f'ungrounded source: {item["keyword"]}')
    if name == 'nontechnical-florist' and result['overall_score'] is not None:
        failures.append('unsupported domain must not receive a numeric estimate')
    return {'case': name, 'passed': not failures, 'failures': failures,
            'expected_priorities': len(expected), 'recommendations': len(actual)}


def private_cases(path):
    module = ast.parse(Path(path).read_text())
    cv = next(ast.literal_eval(node.value) for node in module.body
              if isinstance(node, ast.Assign) and any(
                  isinstance(t, ast.Name) and t.id == 'CV' for t in node.targets))
    # Only experience/capability sections are used. Contact fields are excluded.
    resume = json.dumps({key: cv.get(key, []) for key in
                         ('profile', 'capabilities', 'experience', 'selected_credentials')})
    # Deliberately synthetic job specifications, matched against one real CV.
    return [
        ('private-cloud-role', resume,
         'Requirements\nAWS Python SQL Kubernetes\nNice to Have\nTerraform',
         {'terraform': 'preferred'}, {'aws', 'python', 'sql', 'kubernetes'}),
        ('private-data-role', resume,
         'Requirements\nSQL Python Azure Spark\nNice to Have\nKafka',
         {'spark': 'required', 'kafka': 'preferred'}, {'sql', 'python', 'azure'}),
    ]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-cv-content')
    parser.add_argument('--live-staging', action='store_true',
                        help='Spot-check three synthetic cases through staging AI; never sends the private CV.')
    args = parser.parse_args()
    cases = CASES + (private_cases(args.private_cv_content) if args.private_cv_content else [])
    results = [evaluate(case) for case in cases]
    print(json.dumps({'synthetic_cases': len(CASES), 'private_real_cv_count': int(bool(args.private_cv_content)),
                      'passed': sum(row['passed'] for row in results), 'total': len(results),
                      'results': results}, indent=2))
    if args.live_staging:
        import requests
        for case in (CASES[1], CASES[3], CASES[10]):
            name, resume, jd, _, _ = case
            resume = ('SYNTHETIC TEST CANDIDATE\nProfessional summary\n' + resume +
                      '\nExperience\nDocumented daily work and supported colleagues in a small team.\n' +
                      'Education\nSecondary school completed.\n')
            jd += '\nResponsibilities\nWork with the team, document your work and support day-to-day operations.'
            response = requests.post('https://resumeradar-staging.onrender.com/api/scan',
                                     data={'resume_text': resume, 'job_description': jd}, timeout=90)
            response.raise_for_status()
            data = response.json()
            print(json.dumps({'live_case': name, 'score': data.get('match_score'),
                              'ai_suggestions': data.get('ai_suggestions')}, indent=2), flush=True)
    sys.exit(any(not row['passed'] for row in results))

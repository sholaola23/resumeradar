import unittest
from backend import keyword_engine as engine


class KeywordQualityTests(unittest.TestCase):
    def match(self, resume, jd):
        return engine.calculate_match(engine.extract_keywords_from_text(resume), engine.extract_keywords_from_text(jd, strict=True))

    def test_negated_skill_is_not_evidence(self):
        self.assertNotIn('kubernetes', engine.extract_keywords_from_text('No Kubernetes experience. Python and Docker.')['technical_skills'])

    def test_skill_before_explicit_denial_is_not_evidence(self):
        self.assertNotIn('kubernetes', engine.extract_keywords_from_text('Kubernetes: no experience.')['technical_skills'])

    def test_negated_outcomes_preserve_technical_evidence(self):
        for text in ('Deployed Kubernetes without downtime.', 'Built Python APIs with no outages.', 'Never missed a Docker deployment deadline.'):
            with self.subTest(text=text):
                self.assertTrue(engine.extract_keywords_from_text(text)['technical_skills'])

    def test_mixed_positive_and_negative_evidence(self):
        skills = engine.extract_keywords_from_text('Built Python services, no Kubernetes experience.')['technical_skills']
        self.assertIn('python', skills)
        self.assertNotIn('kubernetes', skills)

    def test_denied_skill_list(self):
        skills = engine.extract_keywords_from_text('No experience with Python, Docker or Kubernetes.')['technical_skills']
        self.assertFalse({'python', 'docker', 'kubernetes'} & skills)

    def test_not_only_is_positive_evidence(self):
        self.assertIn('kubernetes', engine.extract_keywords_from_text('Not only Kubernetes but also Docker.')['technical_skills'])

    def test_punctuation_technical_names_are_recognized(self):
        self.assertIn('c++', engine.extract_keywords_from_text('Developed C++ applications.')['technical_skills'])

    def test_dotted_tool_names_survive_evidence_filter(self):
        self.assertIn('node.js', engine.extract_keywords_from_text('Built Node.js applications.')['technical_skills'])

    def test_positive_separate_evidence_counts(self):
        self.assertIn('kubernetes', engine.extract_keywords_from_text('No Kubernetes experience in 2020. Built Kubernetes clusters in 2024.')['technical_skills'])

    def test_technical_stemming_does_not_invent_skills(self):
        skills = engine.extract_keywords_from_text('Built scalable systems and reacted quickly.')['technical_skills']
        self.assertFalse({'scala', 'react'} & skills)

    def test_unicode_names_and_punctuation_do_not_lose_points(self):
        a = engine.analyze_ats_formatting('Jose Experience Education Skills')
        b = engine.analyze_ats_formatting('José Ọlúṣọlá Experience • Education — Skills')
        self.assertEqual(a['formatting_score'], b['formatting_score'])
        self.assertLess(engine.analyze_ats_formatting('Jose 🚀 Experience Education Skills')['formatting_score'], a['formatting_score'])

    def test_unknown_domain_has_no_score(self):
        result = self.match('Built managed designed improved developed launched delivered created.', 'Floral arranging and bouquet assembly.')
        self.assertIsNone(result['overall_score'])
        self.assertEqual(result['score_status'], 'insufficient_evidence')
        self.assertTrue(result['score_explanation'])

    def test_two_terms_are_insufficient(self):
        self.assertIsNone(self.match('Python Docker', 'Python Docker')['overall_score'])

    def test_verbs_do_not_change_match_estimate(self):
        jd = 'Python Docker Kubernetes'
        self.assertEqual(self.match('Python', jd)['overall_score'], self.match('Python built managed designed improved launched developed delivered created', jd)['overall_score'])

    def test_headings_without_colons_and_responsibilities_reset(self):
        jd = 'Requirements\nKubernetes Docker Python\nNice to Have\nPulumi Terraform\nResponsibilities\nJenkins'
        items = engine.analyze_requirements('Python', jd, self.match('Python', jd))
        priorities = {item['keyword']: item['priority'] for item in items}
        self.assertEqual(priorities['kubernetes'], 'required')
        self.assertEqual(priorities['pulumi'], 'preferred')
        self.assertEqual(priorities['jenkins'], 'unspecified')

    def test_explicitly_not_required_is_not_a_recommendation(self):
        jd = 'Python Docker Kubernetes required. Jenkins is not required.'
        items = engine.analyze_requirements('Python', jd, self.match('Python', jd))
        self.assertNotIn('jenkins', {item['keyword'] for item in items})

    def test_demo_prioritizes_required_technical_terms(self):
        import re
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] / 'static/js/app.js').read_text()
        resume = re.search(r'const DEMO_RESUME\s*=\s*`(.*?)`', script, re.S).group(1)
        jd = re.search(r'const DEMO_JOB\s*=\s*`(.*?)`', script, re.S).group(1)
        items = engine.analyze_requirements(resume, jd, self.match(resume, jd))
        self.assertEqual(len(items[:3]), 3)
        self.assertTrue(all(item['priority'] == 'required' and item['category'] == 'technical_skills' for item in items[:3]))

    def test_requirements_priority_and_alternatives(self):
        resume = 'Python GitHub Actions Docker'
        jd = 'Required: Python, Kubernetes and Docker. Experience with Jenkins, GitHub Actions or CircleCI. Pulumi preferred.'
        helper = getattr(engine, 'analyze_requirements', None)
        self.assertTrue(callable(helper), 'Requirement analysis helper must exist')
        items = helper(resume, jd, self.match(resume, jd))
        by_keyword = {item['keyword']: item for item in items}
        self.assertEqual(by_keyword['kubernetes']['priority'], 'required')
        self.assertEqual(by_keyword['pulumi']['priority'], 'preferred')
        self.assertFalse({'jenkins', 'circleci'} & by_keyword.keys())
        self.assertIn('Required:', by_keyword['kubernetes']['reason'])


if __name__ == '__main__':
    unittest.main()

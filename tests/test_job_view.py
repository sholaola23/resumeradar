"""The "View in job description" panel must agree with the keyword lists."""
import os
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as product
from backend import keyword_engine as engine

CV = ('Experience: Built Python services on AWS with Docker and GitHub. Collaborated with product teams. '
      'Education: BSc Computer Science. Skills: Python, AWS, Docker, SQL.')

# Messy, real-world job text: headings, bullets, look-alike words, symbols,
# nested tool names, placeholders, repeats and a legal footer.
JOBS = {
    'tidy': 'Requirements: Python, AWS and Docker. You will build services and work with Kubernetes every day.',
    'nested_names': 'Must have GitHub Actions or GitLab CI, Google Cloud, machine learning and AWS Solutions Architect certification.',
    'look_alikes': 'A scalable platform. The rest of the team will go to great lengths to react quickly and express ideas. '
                   'Our R&D group uses Scala, REST APIs, Go, React and Express.js. Strong R skills needed.',
    'symbols': 'Key skills:\n\t• C++ / C# (5+ yrs)\n\t• Node.js & CI/CD\n\t• B.S. or M.S. degree — N/A for contractors\n',
    'unicode': 'Rôle 🚀 İstanbul office — Python developer, “Kubernetes” engineer, ＰＹＴＨＯＮ fan, communication skills ✅ leadership.',
    'word_forms': 'You collaborate with stakeholders, communicate clearly and lead teams. Bachelor\'s degree preferred. PMP is a bonus.',
    'repeats': 'Python Python python PYTHON. Docker, docker. Kubernetes; kubernetes. Terraform and terraform again for ten words.',
    'legal_footer': 'We need Python and Terraform for our platform team today. We are an equal opportunity employer '
                    'and value Kubernetes, leadership and communication.',
    'no_terms': 'We seek a florist to arrange bouquets and care for blooms in our shop every day.',
    'huge': ('Requirements: Python, Kubernetes, Terraform and strong communication. ' * 3000),
}


def view(job, cv=CV):
    match = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                   engine.extract_keywords_from_text(job, strict=True))
    return match, engine.locate_job_terms(job, match)


def marked(segments):
    return [segment for segment in segments if 'status' in segment]


class JobViewTests(unittest.TestCase):
    def test_segments_rebuild_the_job_description_exactly(self):
        for name, job in JOBS.items():
            with self.subTest(job=name):
                self.assertEqual(''.join(segment['text'] for segment in view(job)[1]), job)

    def test_every_listed_term_can_be_found_in_the_view(self):
        for name, job in JOBS.items():
            with self.subTest(job=name):
                match, segments = view(job)
                findable = {keyword for segment in marked(segments)
                            for keyword in [segment['keyword']] + segment['also']}
                for key in ('matched_keywords', 'missing_keywords'):
                    for category, keywords in match[key].items():
                        if category != 'action_verbs':
                            self.assertFalse(set(keywords) - findable, (key, category))

    def test_marks_carry_the_same_status_as_the_lists(self):
        for name, job in JOBS.items():
            with self.subTest(job=name):
                match, segments = view(job)
                for segment in marked(segments):
                    key = segment['status'] + '_keywords'
                    self.assertIn(segment['status'], ('matched', 'missing'))
                    self.assertIn(segment['keyword'], match[key][segment['category']])
                    self.assertTrue(segment['text'].strip())

    def test_matched_and_missing_terms_are_told_apart(self):
        status = {segment['keyword']: segment['status'] for segment in marked(view(JOBS['tidy'])[1])}
        self.assertEqual(status, {'python': 'matched', 'aws': 'matched', 'docker': 'matched', 'kubernetes': 'missing'})

    def test_every_mention_is_marked(self):
        texts = [segment['text'] for segment in marked(view(JOBS['repeats'])[1]) if segment['keyword'] == 'python']
        self.assertEqual(texts, ['Python', 'Python', 'python', 'PYTHON'])

    def test_look_alike_words_are_not_marked(self):
        texts = [segment['text'] for segment in marked(view(JOBS['look_alikes'])[1])]
        for word in ('scalable', 'rest', 'go', 'react', 'express'):
            self.assertNotIn(word, texts)
        for word in ('Scala', 'REST', 'Go', 'React', 'Express.js'):
            self.assertIn(word, texts)
        self.assertEqual(texts.count('R'), 1)  # the skill, not the R in R&D

    def test_longer_term_wins_and_keeps_the_shorter_one_findable(self):
        segments = {segment['text']: segment for segment in marked(view(JOBS['nested_names'])[1])}
        self.assertIn('github', segments['GitHub Actions']['also'])
        self.assertEqual(segments['GitHub Actions']['status'], 'missing')
        self.assertNotIn('GitHub', segments)
        self.assertIn('Google Cloud', segments)

    def test_word_forms_are_marked_where_the_job_uses_them(self):
        found = {segment['keyword']: segment['text'] for segment in marked(view(JOBS['word_forms'])[1])}
        self.assertEqual(found.get('collaboration'), 'collaborate')
        self.assertEqual(found.get('bachelor'), 'Bachelor')

    def test_legal_footer_is_left_unmarked(self):
        segments = view(JOBS['legal_footer'])[1]
        self.assertEqual({segment['keyword'] for segment in marked(segments)}, {'python', 'terraform'})
        self.assertIn('Kubernetes, leadership and communication', segments[-1]['text'])

    def test_job_with_no_recognised_terms_has_no_marks(self):
        self.assertEqual(view(JOBS['no_terms'])[1], [{'text': JOBS['no_terms']}])

    def test_action_verbs_from_the_cv_are_never_marked(self):
        job = 'You will have built and managed Python services, led teams and delivered projects on time.'
        match, segments = view(job, 'Led, built, managed and delivered Python services.')
        self.assertTrue(match['matched_keywords']['action_verbs'])
        self.assertFalse([segment for segment in marked(segments) if segment['category'] == 'action_verbs'])

    def test_scan_api_returns_the_view_for_the_submitted_job_only(self):
        with patch.dict(os.environ, {}, clear=True):
            data = product.app.test_client().post('/api/scan', data={
                'resume_text': CV + ' I maintain reliable services and work closely with developers on customer applications.',
                'job_description': '  ' + JOBS['tidy'] + '\n',
            }).get_json()
        segments = data['job_description_view']
        self.assertEqual(''.join(segment['text'] for segment in segments), JOBS['tidy'])
        self.assertEqual({segment['keyword'] for segment in marked(segments) if segment['status'] == 'missing'},
                         set(data['missing_keywords']['technical_skills']))
        self.assertNotIn(CV[:40], ''.join(segment['text'] for segment in segments))


if __name__ == '__main__':
    unittest.main()

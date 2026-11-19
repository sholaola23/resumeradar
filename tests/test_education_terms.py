"""Education terms must come from qualifications, not job titles.

Regression for the job-title word "Engineer" being read as the education
keyword "engineering" and listed as missing (found in review of PR #9).
"""
import unittest

from backend import keyword_engine as engine


def jd_education(text):
    return engine.extract_keywords_from_text(text, strict=True)['education']


def cv_education(text):
    return engine.extract_keywords_from_text(text)['education']


class JobTitlesAreNotQualifications(unittest.TestCase):
    def test_engineer_title_is_not_engineering(self):
        for jd in ('Senior Cloud Engineer\nWe need AWS and Terraform.',
                   'We are hiring a DevOps Engineer to join us.',
                   'Engineers on this team own their services.'):
            with self.subTest(jd=jd):
                self.assertNotIn('engineering', jd_education(jd))

    def test_engineering_as_team_or_title_is_not_a_qualification(self):
        for jd in ('Engineering Manager\nLead our engineering team.',
                   '5+ years of experience in cloud engineering or DevOps.',
                   'Mentor junior engineers and contribute to engineering standards.'):
            with self.subTest(jd=jd):
                self.assertNotIn('engineering', jd_education(jd))

    def test_other_fields_as_titles_or_skills_are_not_qualifications(self):
        self.assertFalse(jd_education('Data Science Manager\nLead the data science team.'))
        self.assertFalse(jd_education('Strong statistics and mathematics skills.'))
        self.assertFalse(jd_education('Information Technology Support Analyst'))

    def test_scrum_master_is_not_a_masters_degree(self):
        for text in ('Scrum Master\nRun sprint ceremonies.', 'Own master data quality.',
                     'Mastering Kubernetes is a plus.'):
            with self.subTest(text=text):
                self.assertNotIn('master', jd_education(text))
                self.assertNotIn('master', cv_education(text))

    def test_demo_job_lists_no_education(self):
        # The home page sample job asks for no degree.
        jd = ('Senior Cloud Engineer\n\nAbout the Role\nWe are looking for a Senior Cloud Engineer.\n'
              'Requirements\n- 5+ years of experience in cloud engineering or DevOps\n'
              '- Mentor junior engineers and contribute to engineering standards')
        self.assertEqual(jd_education(jd), set())

    def test_title_far_from_a_degree_line_in_one_paragraph(self):
        jd = ('Engineering Manager. ' + 'You will lead delivery across several product squads. ' * 4 +
              "A bachelor's degree is preferred.")
        edu = jd_education(jd)
        self.assertNotIn('engineering', edu)
        self.assertIn('bachelor', edu)


    def test_look_alike_words_are_not_degree_cues(self):
        for jd in ('Engineering hub based in Bengaluru.',
                   'Diplomatic with engineering stakeholders.',
                   'Scrum Master supporting our engineering teams.',
                   'You will have a high degree of autonomy across engineering.',
                   '360-degree feedback culture in engineering.',
                   'Qualifications: 5+ years in cloud engineering.'):
            with self.subTest(jd=jd):
                self.assertNotIn('engineering', jd_education(jd))

    def test_scrum_master_phrasings(self):
        for jd in ('Work as a Scrum Master in an agile team.', 'We are hiring Scrum Masters.'):
            with self.subTest(jd=jd):
                self.assertNotIn('master', jd_education(jd))

    def test_degree_of_is_not_a_degree(self):
        self.assertNotIn('degree', jd_education('A high degree of ownership. 360-degree reviews.'))


class RealQualificationsStillCount(unittest.TestCase):
    def test_degree_lines_name_their_fields(self):
        cases = {
            "Bachelor's degree in Computer Science or Engineering.": {'bachelor', 'degree', 'computer science', 'engineering'},
            'BEng or BSc in Engineering required.': {'bsc', 'engineering'},
            'Degree in Mathematics, Statistics or a related field.': {'degree', 'mathematics', 'statistics'},
            "Master's in Data Science preferred.": {'master', 'data science'},
            'Educated to degree level in Information Technology.': {'degree', 'information technology'},
            'MBA or Business Administration qualification.': {'mba', 'business administration'},
        }
        for jd, expected in cases.items():
            with self.subTest(jd=jd):
                self.assertTrue(expected <= jd_education(jd), jd_education(jd))

    def test_abbreviated_degrees_keep_their_subject(self):
        self.assertTrue({'b.s.', 'computer science'} <= jd_education('B.S. in Computer Science required.'))
        self.assertIn('engineering', jd_education('Degree in a STEM subject, e.g. Engineering.'))
        self.assertIn('doctorate', jd_education('Doctoral degree in Statistics.'))

    def test_every_missing_field_gets_advice(self):
        # The score and the advice read the job description the same way.
        jd = ("Backend Engineer\nBachelor's degree required; Engineering, Mathematics or Physics preferred.\n"
              'B.S. in Computer Science, e.g. Statistics. Engineering Manager reports.')
        cv = 'Software Engineer\nPython.'
        result = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                        engine.extract_keywords_from_text(jd, strict=True))
        advice = {item['keyword'] for item in engine.analyze_requirements(cv, jd, result)
                  if item['category'] == 'education'}
        self.assertEqual(set(result['missing_keywords']['education']), advice)

    def test_master_degree_forms(self):
        for text in ("Master's degree", 'Masters in Statistics', 'Master of Science', 'master degree'):
            with self.subTest(text=text):
                self.assertIn('master', jd_education(text))
                self.assertIn('master', cv_education(text))

    def test_plural_degree_counts(self):
        self.assertIn('degree', jd_education('Relevant degrees considered.'))


class CvSide(unittest.TestCase):
    def test_engineer_job_title_is_not_an_engineering_degree(self):
        self.assertNotIn('engineering', cv_education('Software Engineer | Acme | 2020 - Present'))

    def test_cv_degree_fields_count_without_a_degree_word_on_the_line(self):
        # CVs often put the subject on its own line under EDUCATION.
        edu = cv_education('EDUCATION\nImperial College London\nMechanical Engineering, 2015 - 2019')
        self.assertIn('engineering', edu)

    def test_engineering_job_title_on_cv_is_not_a_degree(self):
        self.assertNotIn('engineering', cv_education('Engineering Manager at Acme\nLed a team of 8.'))

    def test_missing_engineering_degree_is_reported_honestly(self):
        jd = "Backend Engineer\nPython, AWS.\nBachelor's degree in Engineering."
        cv = 'Software Engineer\nPython, AWS.\nSelf-taught.'
        result = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                        engine.extract_keywords_from_text(jd, strict=True))
        self.assertIn('engineering', result['missing_keywords']['education'])
        self.assertNotIn('engineering', result['matched_keywords']['education'])


if __name__ == '__main__':
    unittest.main()

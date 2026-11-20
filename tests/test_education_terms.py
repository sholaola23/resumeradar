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


class SubjectAlternatives(unittest.TestCase):
    def score(self, cv, jd):
        return engine.calculate_match(engine.extract_keywords_from_text(cv),
                                      engine.extract_keywords_from_text(jd, strict=True))

    def test_one_subject_from_an_or_list_is_enough(self):
        cv = 'EDUCATION\nBSc Computer Science, University of Leeds'
        for jd in ("Bachelor's degree in Computer Science or Engineering.",
                   'BS in Computer Science, Engineering, or a related field.',
                   'Degree in Computer Science/Information Technology.'):
            with self.subTest(jd=jd):
                result = self.score(cv, jd)
                self.assertIn('computer science', result['matched_keywords']['education'])
                self.assertEqual(result['missing_keywords']['education'], [])

    def test_or_a_related_subject_is_one_requirement(self):
        jd = 'Requirements: a degree in computer science or a related engineering subject.'
        groups = engine.extract_keywords_from_text(jd, strict=True)['education_alternatives']
        self.assertEqual(groups, [frozenset({'computer science', 'engineering'})])
        result = self.score('EDUCATION\nBSc (Hons), University of Leeds', jd)
        edu = result['category_scores']['education']
        # degree and one subject are asked for; the CV has the degree only.
        self.assertEqual((edu['matched'], edu['total']), (1, 2))
        self.assertEqual(result['total_missing'], result['total_job_keywords'] - result['total_matched'])

    def test_degree_levels_offered_as_a_choice(self):
        cv = 'Education\nMS Machine Learning, Stanford University'
        for jd in ('MS or PhD in Machine Learning.', "Master's or PhD in Machine Learning.",
                   'BS/MS in Machine Learning.'):
            with self.subTest(jd=jd):
                self.assertEqual(self.score(cv, jd)['missing_keywords']['education'], [])
        for cv, jd in ((cv, 'MS or PhD in Machine Learning. Python, SQL, AWS.'),
                       ('Education\nMSc Statistics, University of Leeds', "Master's or PhD in Statistics.")):
            with self.subTest(jd=jd):
                result = self.score(cv, jd)
                edu = result['category_scores']['education']
                self.assertLessEqual(edu['matched'], edu['total'])
                self.assertLessEqual(edu['score'], 100)
                self.assertLessEqual(result['overall_score'], 100)
        groups = engine.extract_keywords_from_text('MS or PhD in Machine Learning.', strict=True)['education_alternatives']
        self.assertIn(frozenset({'master', 'phd'}), groups)

    def test_or_list_with_no_subject_lists_every_option(self):
        result = self.score('EDUCATION\nBA History, University of York',
                            "Bachelor's degree in Computer Science or Engineering.")
        self.assertTrue({'computer science', 'engineering'} <= set(result['missing_keywords']['education']))

    def test_and_list_needs_both(self):
        result = self.score('EDUCATION\nBSc Mathematics, University of Leeds',
                            'Degree in Mathematics and Statistics.')
        self.assertIn('statistics', result['missing_keywords']['education'])

    def test_separate_requirements_are_not_alternatives(self):
        jd = "BSc in Computer Science required.\nMaster's in Statistics preferred."
        groups = engine.extract_keywords_from_text(jd, strict=True)['education_alternatives']
        self.assertEqual(groups, [])


class MoreDegreeWords(unittest.TestCase):
    def test_short_degree_names_are_cues(self):
        for jd in ('BS in Computer Science.', 'BA in Mathematics.', 'B.Tech in Engineering.',
                   'BTech or MTech in Engineering.', 'HND in Engineering.', 'MS in Statistics.',
                   'M.Tech. in Engineering.', 'BEng (Hons) Engineering.'):
            with self.subTest(jd=jd):
                self.assertTrue(jd_education(jd) & engine.EDUCATION_FIELDS, jd_education(jd))

    def test_state_codes_are_not_degrees(self):
        self.assertNotIn('engineering', jd_education('Engineering office in Boston, MA with hybrid working.'))

    def test_or_after_a_short_name_needs_another_degree(self):
        self.assertNotIn('master', jd_education('Located in Boston, MA or remote.'))
        self.assertNotIn('bachelor', jd_education('Work closely with the BA or PM.'))
        self.assertNotIn('master', jd_education('Ms or Mr Smith.'))
        self.assertNotIn('master', cv_education('Boston, MA\nStatistics consultant'))
        self.assertNotIn('master', jd_education('Office in Boston, MA\nDegree in Statistics preferred.'))
        self.assertIn('bachelor', jd_education('BA or BSc in Economics.'))
        self.assertIn('master', jd_education('BS or MS degree in Statistics.'))

    def test_milliseconds_are_not_a_degree(self):
        self.assertNotIn('engineering', jd_education('Latency under 50 ms in our engineering stack.'))


class ScoreBounds(unittest.TestCase):
    JOBS = ("MS or PhD in Machine Learning.", "Master's or PhD in Statistics.", 'BS/MS in Computer Science.',
            "Bachelor's or Master's degree in Engineering or Mathematics.",
            'BS in Computer Science, Engineering, or a related field.', 'MBA or MSc in Business Administration.',
            'Degree in Mathematics and Statistics.', 'Senior Cloud Engineer. Python, AWS.',
            'BS in Computer Science or Engineering required.\nMS in Computer Science or Engineering preferred.',
            'BS in Computer Science or Engineering required.\nMS in Computer Science or Engineering preferred.\n'
            'PhD in Computer Science or Engineering a plus. Python, SQL, AWS.',
            'BS in Computer Science or Mathematics.\nMS in Mathematics or Statistics preferred.')
    CVS = ('Education\nMS Machine Learning, Stanford', 'Education\nMSc Statistics, University of Leeds',
           'EDUCATION\nBSc Computer Science\nMSc Data Science\nPhD Statistics, University of Oxford',
           'EDUCATION\nBEng Mechanical Engineering, Imperial College', 'Software Engineer. Python, AWS.',
           'EDUCATION\nMBA, London Business School', 'EDUCATION\nBA History, University of York',
           'EDUCATION\nBSc History, University of Leeds\nPython, SQL, AWS')

    def test_repeated_choice_is_one_group(self):
        jd = 'BS in Computer Science or Engineering required.\nMS in Computer Science or Engineering preferred.'
        groups = engine.extract_keywords_from_text(jd, strict=True)['education_alternatives']
        self.assertEqual(groups, [frozenset({'computer science', 'engineering'})])

    def test_matched_never_exceeds_total(self):
        for jd in self.JOBS:
            for cv in self.CVS:
                with self.subTest(jd=jd, cv=cv):
                    result = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                                    engine.extract_keywords_from_text(jd, strict=True))
                    for category, data in result['category_scores'].items():
                        if category != 'action_verbs':
                            self.assertLessEqual(data['matched'], data['total'], category)
                    # None means too few terms to score, which is fine here.
                    self.assertLessEqual(result['overall_score'] or 0, 100)


class JobView(unittest.TestCase):
    def test_job_view_marks_only_qualification_mentions(self):
        jd = ("Engineering Manager\nLead our engineering team. Python, AWS.\n"
              "Bachelor's degree in Engineering or a related field.")
        cv = 'Software Engineer\nPython, AWS.'
        result = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                        engine.extract_keywords_from_text(jd, strict=True))
        self.assertIn('engineering', result['missing_keywords']['education'])
        marks = [seg for seg in engine.locate_job_terms(jd, result) if seg.get('keyword') == 'engineering']
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]['text'], 'Engineering')
        self.assertGreater(jd.index(marks[0]['text'], jd.index('degree')), 0)

    def test_job_view_does_not_mark_scrum_master(self):
        jd = "Scrum Master\nRun Scrum with Jira. Master's degree preferred."
        result = engine.calculate_match(engine.extract_keywords_from_text('Scrum. Jira.'),
                                        engine.extract_keywords_from_text(jd, strict=True))
        marks = [seg['text'] for seg in engine.locate_job_terms(jd, result) if seg.get('keyword') == 'master']
        self.assertEqual(marks, ["Master's"])


class CvSide(unittest.TestCase):
    def test_engineer_job_title_is_not_an_engineering_degree(self):
        self.assertNotIn('engineering', cv_education('Software Engineer | Acme | 2020 - Present'))

    def test_cv_degree_fields_count_without_a_degree_word_on_the_line(self):
        # CVs often put the subject on its own line under EDUCATION.
        edu = cv_education('EDUCATION\nImperial College London\nMechanical Engineering, 2015 - 2019')
        self.assertIn('engineering', edu)

    def test_short_degree_name_before_subject_on_cv(self):
        cv = ('EDUCATION\nMS Statistics, Georgia Tech\n- Thesis on forecasting\n- Teaching assistant\n'
              '- Dean\'s list\n\nBS Computer Science, Georgia Tech')
        self.assertIn('computer science', cv_education(cv))
        for line in ('BS Computer Science', 'BS, Computer Science', 'MA Mathematics'):
            with self.subTest(line=line):
                self.assertTrue(engine._has_degree_cue(line.lower()))

    def test_qa_cv_with_bs_below_ms_entry_meets_bs_requirement(self):
        cv = ('EDUCATION\nMS Statistics, Georgia Tech\n- Thesis on forecasting\n- Teaching assistant\n'
              "- Dean's list\nBS Computer Science, Georgia Tech, 2018\nPython, SQL, AWS")
        result = engine.calculate_match(engine.extract_keywords_from_text(cv), engine.extract_keywords_from_text(
            'BS in Computer Science required. Python, SQL, AWS.', strict=True))
        self.assertEqual(result['missing_keywords']['education'], [])
        self.assertTrue({'bachelor', 'computer science'} <= cv_education('BS, Computer Science - Georgia Tech'))

    def test_other_degree_names_meet_their_level(self):
        jd = "Bachelor's in Computer Science, Engineering, or related field."
        for cv in ('EDUCATION\nBEng Mechanical Engineering, Imperial College',
                   'EDUCATION\nB.Tech Computer Science, IIT Delhi'):
            with self.subTest(cv=cv):
                result = engine.calculate_match(engine.extract_keywords_from_text(cv),
                                                engine.extract_keywords_from_text(jd, strict=True))
                self.assertNotIn('bachelor', result['missing_keywords']['education'])
        for text in ('LLB, University of Leeds', 'BCom Accounting, University of Lagos'):
            with self.subTest(text=text):
                self.assertIn('bachelor', cv_education(text))
        for text in ('MEng Civil Engineering', 'M.Tech in Engineering', 'MA in Statistics'):
            with self.subTest(text=text):
                self.assertIn('master', cv_education(text))

    def test_ma_or_ms_is_a_master_requirement(self):
        self.assertIn('master', jd_education('MA or MS in Statistics.'))

    def test_short_degree_in_any_subject_under_education(self):
        self.assertIn('master', cv_education('Education\nMS Machine Learning, Stanford'))
        self.assertIn('master', cv_education('EDUCATION\nMS Finance, NYU'))
        self.assertIn('bachelor', cv_education('Education\nBA, History, University of York'))
        self.assertNotIn('master', cv_education('Skills\nMS Office, Excel'))
        self.assertNotIn('master', cv_education('Skills\nMS Office, Excel, Python\nUniversity liaison role'))
        self.assertNotIn('master', cv_education('Education\nMS Office certification'))

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

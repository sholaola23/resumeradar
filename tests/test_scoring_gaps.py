"""Tests for scoring paths that had no direct assertions.

These pin today's behaviour of calculate_match weighting, the ATS formatting
score, bullet quantification and the recruiter tips score. They do not touch
education matching, which has its own tests.
"""
import unittest

from backend import keyword_engine as engine

FILLER = "lorem"
VERBS = sorted(engine.ACTION_VERBS)


def words(n):
    return " ".join([FILLER] * n)


def keywords(**cats):
    base = {c: set() for c in ("technical_skills", "soft_skills", "certifications", "education", "action_verbs")}
    base.update({k: set(v) for k, v in cats.items()})
    return base


class CalculateMatchWeightingTests(unittest.TestCase):
    def test_small_technical_list_is_a_straight_ratio(self):
        job = keywords(technical_skills={"python", "docker", "kubernetes", "terraform"})
        cv = keywords(technical_skills={"python", "docker"})
        result = engine.calculate_match(cv, job)
        self.assertEqual(result["category_scores"]["technical_skills"]["score"], 50.0)
        self.assertEqual(result["overall_score"], 50.0)

    def test_long_technical_list_uses_the_curve(self):
        job_terms = {f"skill{i}" for i in range(10)}
        job = keywords(technical_skills=job_terms)
        cv = keywords(technical_skills=set(sorted(job_terms)[:5]))
        result = engine.calculate_match(cv, job)
        # (5/10) ** 0.7 * 100 = 61.56
        self.assertEqual(result["category_scores"]["technical_skills"]["score"], 61.6)

    def test_curve_only_applies_above_eight_terms(self):
        job_terms = {f"skill{i}" for i in range(8)}
        result = engine.calculate_match(keywords(technical_skills=set(sorted(job_terms)[:4])),
                                        keywords(technical_skills=job_terms))
        self.assertEqual(result["category_scores"]["technical_skills"]["score"], 50.0)

    def test_overall_is_weighted_by_categories_the_job_mentions(self):
        job = keywords(technical_skills={"python", "docker", "aws", "sql"}, soft_skills={"leadership", "communication"})
        cv = keywords(technical_skills={"python", "docker", "aws", "sql"})
        result = engine.calculate_match(cv, job)
        # (100 * 0.40 + 0 * 0.15) / 0.55; empty categories are left out.
        self.assertEqual(result["overall_score"], 72.7)
        self.assertEqual(result["category_scores"]["certifications"], {"score": 100, "matched": 0, "total": 0, "weight": 0.20})

    def test_matched_missing_and_extra_lists(self):
        job = keywords(technical_skills={"python", "docker", "go"})
        cv = keywords(technical_skills={"python", "rust"})
        result = engine.calculate_match(cv, job)
        self.assertEqual(result["matched_keywords"]["technical_skills"], ["python"])
        self.assertEqual(result["missing_keywords"]["technical_skills"], ["docker", "go"])
        self.assertEqual(result["extra_keywords"]["technical_skills"], ["rust"])
        self.assertEqual(result["total_job_keywords"], 3)
        self.assertEqual(result["total_matched"], 1)
        self.assertEqual(result["total_missing"], 2)
        self.assertEqual(result["simple_match_ratio"], 33.3)

    def test_action_verb_tiers(self):
        job = keywords(technical_skills={"python", "docker", "go"})
        for count, expected in ((0, 10), (1, 40), (2, 40), (3, 60), (4, 60), (5, 80), (7, 80), (8, 100), (12, 100)):
            with self.subTest(count=count):
                cv = keywords(action_verbs=set(VERBS[:count]))
                data = engine.calculate_match(cv, job)["category_scores"]["action_verbs"]
                self.assertEqual(data["score"], expected)
                self.assertEqual(data["matched"], count)
                self.assertEqual(data["total"], max(count, 8))

    def test_action_verbs_do_not_change_the_overall_score(self):
        job = keywords(technical_skills={"python", "docker", "go"})
        none = engine.calculate_match(keywords(technical_skills={"python"}), job)
        many = engine.calculate_match(keywords(technical_skills={"python"}, action_verbs=set(VERBS[:10])), job)
        self.assertEqual(none["overall_score"], many["overall_score"])
        self.assertEqual(none["simple_match_ratio"], many["simple_match_ratio"])

    def test_fewer_than_three_job_terms_gives_no_score(self):
        job = keywords(technical_skills={"python", "docker"}, action_verbs=set(VERBS[:5]))
        result = engine.calculate_match(keywords(technical_skills={"python", "docker"}), job)
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["score_status"], "insufficient_evidence")

    def test_three_job_terms_gives_an_estimate(self):
        job = keywords(technical_skills={"python", "docker"}, soft_skills={"leadership"})
        result = engine.calculate_match(keywords(technical_skills={"python", "docker"}), job)
        self.assertEqual(result["score_status"], "estimated")
        self.assertIn("not an employer ATS score", result["score_explanation"])

    def test_missing_categories_are_treated_as_empty(self):
        result = engine.calculate_match({"technical_skills": {"python"}},
                                        {"technical_skills": {"python", "go", "sql"}})
        self.assertEqual(result["category_scores"]["technical_skills"]["score"], 33.3)
        self.assertEqual(result["overall_score"], 33.3)


def ats_cv(*, sections=("Experience", "Education", "Skills"), email=True, phone=True,
           linkedin=True, verbs=8, extra_words=0, emoji=False):
    parts = ["Jo Bloggs"]
    if email:
        parts.append("jo@mail.test")
    if phone:
        parts.append("+44 7700 900123")
    if linkedin:
        parts.append("linkedin.com/in/jobloggs")
    parts.extend(sections)
    parts.extend(VERBS[:verbs])
    if emoji:
        parts.append("\U0001F680")
    text = "\n".join(parts)
    if extra_words:
        text += "\n" + words(extra_words)
    return text


def points(result, label):
    return next(item["points"] for item in result["checklist"] if item["label"] == label)


class AtsFormattingTests(unittest.TestCase):
    def test_complete_cv_scores_full_marks(self):
        result = engine.analyze_ats_formatting(ats_cv(extra_words=500))
        self.assertEqual(result["formatting_score"], 100)
        self.assertEqual(result["issues"], [])
        self.assertTrue(all(item["passed"] for item in result["checklist"]))
        self.assertEqual(result["has_contact_info"], {"email": True, "phone": True, "linkedin": True})

    def test_bare_text_scores_the_floor(self):
        result = engine.analyze_ats_formatting(words(50))
        # 15 no special chars + 0 sections + 5 short + 0 contact + 5 verbs
        self.assertEqual(result["formatting_score"], 25)
        messages = [issue["message"] for issue in result["issues"]]
        self.assertIn("Your CV seems very short", messages)
        self.assertIn("No email address detected", messages)
        self.assertIn("Few action verbs detected", messages)
        self.assertTrue(any(m.startswith("Missing standard section headers") for m in messages))
        critical = [i for i in result["issues"] if i["type"] == "critical"]
        self.assertEqual([i["message"] for i in critical], ["No email address detected"])

    def test_emoji_loses_special_character_points(self):
        result = engine.analyze_ats_formatting(ats_cv(extra_words=500, emoji=True))
        self.assertEqual(points(result, "No special characters"), 0)
        self.assertEqual(result["formatting_score"], 85)

    def test_section_points_are_proportional(self):
        for sections, expected in ((("Experience", "Education", "Skills"), 25),
                                   (("Experience", "Skills"), 17),
                                   (("Experience",), 8),
                                   ((), 0)):
            with self.subTest(sections=sections):
                result = engine.analyze_ats_formatting(ats_cv(sections=sections, extra_words=500))
                self.assertEqual(points(result, "Standard section headings"), expected)

    def test_optional_sections_are_reported(self):
        result = engine.analyze_ats_formatting(ats_cv(sections=("Summary", "Experience", "Education", "Skills", "Projects")))
        self.assertEqual(result["sections_found"], ["experience", "education", "skills", "summary", "projects"])

    def test_word_count_bands(self):
        for extra, expected in ((100, 5), (300, 15), (500, 20), (900, 15), (1300, 10)):
            with self.subTest(extra=extra):
                result = engine.analyze_ats_formatting(ats_cv(extra_words=extra))
                self.assertEqual(points(result, "Word count (400-800 ideal)"), expected)

    def test_word_count_band_edges(self):
        for count, expected in ((149, 5), (150, 15), (399, 15), (400, 20), (800, 20),
                                (801, 15), (1200, 15), (1201, 10)):
            with self.subTest(count=count):
                result = engine.analyze_ats_formatting(words(count))
                self.assertEqual(result["word_count"], count)
                self.assertEqual(points(result, "Word count (400-800 ideal)"), expected)

    def test_long_cv_is_info_not_warning(self):
        result = engine.analyze_ats_formatting(ats_cv(extra_words=1300))
        long_issue = next(i for i in result["issues"] if i["message"] == "Your CV is quite long")
        self.assertEqual(long_issue["type"], "info")

    def test_contact_points(self):
        cases = (({}, 20), ({"linkedin": False}, 13), ({"linkedin": False, "phone": False}, 7),
                 ({"linkedin": False, "phone": False, "email": False}, 0))
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                result = engine.analyze_ats_formatting(ats_cv(extra_words=500, **overrides))
                self.assertEqual(points(result, "Contact information"), expected)

    def test_missing_phone_and_linkedin_become_tips(self):
        result = engine.analyze_ats_formatting(ats_cv(phone=False, linkedin=False))
        self.assertIn("Consider adding a phone number to your contact information.", result["tips"])
        self.assertIn("Adding your LinkedIn profile URL can strengthen your application.", result["tips"])

    def test_action_verb_bands(self):
        for count, expected in ((0, 5), (2, 5), (3, 10), (4, 10), (5, 15), (7, 15), (8, 20)):
            with self.subTest(count=count):
                result = engine.analyze_ats_formatting(ats_cv(verbs=count, extra_words=500))
                self.assertEqual(points(result, "Action verbs used"), expected)


class BulletQuantificationTests(unittest.TestCase):
    QUANT = "- Cut hosting costs by 20% in a year"
    PLAIN = "- Looked after the build pipeline daily"

    def bullets(self, quantified, plain):
        return "\n".join([self.QUANT] * quantified + [self.PLAIN] * plain)

    def test_no_bullets_scores_fifty(self):
        result = engine.check_bullet_quantification("Jo Bloggs\nlorem ipsum dolor sit amet")
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["total_bullets"], 0)
        self.assertEqual(result["detail"], "No bullet points detected")

    def test_ratio_bands(self):
        for quantified, plain, expected in ((3, 2, 100), (1, 1, 80), (2, 3, 80), (1, 4, 60), (1, 9, 40), (0, 5, 15)):
            with self.subTest(quantified=quantified, plain=plain):
                result = engine.check_bullet_quantification(self.bullets(quantified, plain))
                self.assertEqual(result["score"], expected)
                self.assertEqual(result["quantified_count"], quantified)
                self.assertEqual(result["detail"], f"{quantified}/{quantified + plain} bullets include metrics")

    def test_metric_forms(self):
        for line in ("- Grew revenue to £5k in the first quarter",
                     "- Saved $ 40 on every single order",
                     "- Served 300 users across three regions",
                     "- Raised conversion by 12 percent overall",
                     "- Made the build pipeline 3x faster than before"):
            with self.subTest(line=line):
                self.assertEqual(engine.check_bullet_quantification(line)["quantified_count"], 1)

    def test_bullet_markers(self):
        for marker in ("-", "*", "•", "1.", "2)"):
            with self.subTest(marker=marker):
                line = f"{marker} Looked after the build pipeline daily"
                self.assertEqual(engine.check_bullet_quantification(line)["total_bullets"], 1)

    def test_line_starting_with_an_action_verb_counts(self):
        result = engine.check_bullet_quantification("Automated the release process for the team")
        self.assertEqual(result["total_bullets"], 1)
        self.assertEqual(result["flagged_bullets"], ["Automated the release process for the team"])

    def test_plain_prose_and_short_lines_are_ignored(self):
        result = engine.check_bullet_quantification("Looked after the build pipeline daily\n- Did 5%\n\n")
        self.assertEqual(result["total_bullets"], 0)

    def test_flagged_list_is_capped_at_eight(self):
        result = engine.check_bullet_quantification(self.bullets(0, 12))
        self.assertEqual(result["total_bullets"], 12)
        self.assertEqual(len(result["flagged_bullets"]), 8)


class RecruiterTipsScoreTests(unittest.TestCase):
    def test_measurable_results_points_follow_quantification(self):
        quant, plain = BulletQuantificationTests.QUANT, BulletQuantificationTests.PLAIN
        for text, expected in (("\n".join([quant] * 3 + [plain] * 2), 30),
                               ("\n".join([quant, plain]), 30),
                               ("\n".join([quant] + [plain] * 4), 20),
                               ("Jo Bloggs", 15),
                               ("\n".join([plain] * 3), 5)):
            with self.subTest(expected=expected):
                result = engine.calculate_recruiter_tips_score(text)
                self.assertEqual(points(result, "Measurable results"), expected)

    def test_action_verb_points(self):
        for count, expected in ((3, 5), (4, 15), (6, 15), (7, 20), (9, 20), (10, 25)):
            with self.subTest(count=count):
                result = engine.calculate_recruiter_tips_score(" ".join(VERBS[:count]))
                self.assertEqual(points(result, "Action verb usage"), expected)

    def test_length_points(self):
        for count, expected in ((150, 5), (199, 5), (200, 10), (299, 10), (300, 15), (399, 15), (400, 20),
                               (800, 20), (801, 15), (1000, 15), (1001, 10)):
            with self.subTest(count=count):
                result = engine.calculate_recruiter_tips_score(words(count))
                self.assertEqual(points(result, "CV length"), expected)

    def test_title_alignment_defaults_without_a_job(self):
        result = engine.calculate_recruiter_tips_score("Python developer")
        self.assertEqual(points(result, "Job title alignment"), 15)

    def test_title_alignment_with_only_stopwords(self):
        result = engine.calculate_recruiter_tips_score("Python developer", "Join our team")
        self.assertEqual(points(result, "Job title alignment"), 15)

    def test_title_alignment_bands(self):
        jd = "Senior Python Developer\nLondon office\nHybrid working"
        # Title words: senior, python, developer, london, office, hybrid, working
        for cv, expected in (("senior python developer london", 25),
                             ("python developer office", 18),
                             ("python", 10),
                             ("gardener", 3)):
            with self.subTest(cv=cv):
                result = engine.calculate_recruiter_tips_score(cv, jd)
                self.assertEqual(points(result, "Job title alignment"), expected)

    def test_title_alignment_band_edges(self):
        jd = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        title = jd.split()
        for matched, expected in ((5, 25), (4, 18), (3, 18), (2, 10), (1, 10), (0, 3)):
            with self.subTest(matched=matched):
                result = engine.calculate_recruiter_tips_score(" ".join(title[:matched]) or "zzz", jd)
                self.assertEqual(points(result, "Job title alignment"), expected)

    def test_title_alignment_reads_only_the_first_three_lines(self):
        jd = "Senior Python Developer\n\n\nGardener wanted"
        result = engine.calculate_recruiter_tips_score("gardener", jd)
        self.assertEqual(points(result, "Job title alignment"), 3)

    def test_total_is_the_sum_of_points(self):
        result = engine.calculate_recruiter_tips_score(words(600), "Senior Python Developer")
        self.assertEqual(result["score"], sum(item["points"] for item in result["checklist"]))
        # 15 (no bullets) + 5 (no verbs) + 20 (length) + 3 (no title words)
        self.assertEqual(result["score"], 43)
        self.assertEqual(result["quantification"]["score"], 50)


if __name__ == "__main__":
    unittest.main()

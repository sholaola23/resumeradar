"""Offline product regressions; never load local service credentials."""
import os
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {}, clear=True), patch('dotenv.load_dotenv'):
    import app as product
from backend.ai_analyzer import _get_fallback_suggestions
from backend.report_generator import generate_pdf_report
from backend import cv_builder

class ProductTests(unittest.TestCase):
    def test_ai_context_excludes_satisfied_tool_alternatives(self):
        from backend import ai_analyzer
        context = getattr(ai_analyzer, '_recommendation_context', None)
        self.assertIsNotNone(context)
        missing, excluded = context({
            'missing_keywords': {'technical_skills': ['docker', 'jenkins']},
            'priority_recommendations': [{'keyword': 'docker', 'category': 'technical_skills'}],
        })
        self.assertEqual(missing['technical_skills'], ['docker'])
        self.assertEqual(excluded, ['jenkins'])
    def test_short_skills_heading_ends_education_section(self):
        resume = """EDUCATION
BSc Computer Science | University of Manchester | 2020

SKILLS
AWS, Terraform, Docker

CERTIFICATIONS
AWS Solutions Architect Associate
"""
        entries = cv_builder._extract_section_entries(
            resume, cv_builder._EDU_HEADING_RE
        )
        self.assertEqual(
            entries,
            ['BSc Computer Science | University of Manchester | 2020'],
        )

    def test_suggestion_terms_use_job_description_spelling(self):
        canonicalize = getattr(cv_builder, '_canonicalize_suggestion_terms', None)
        self.assertIsNotNone(canonicalize)
        suggestions = canonicalize(
            ['Have you used DynamoCDB, CloudFront, or Route 53?'],
            'Experience with DynamoDB, CloudFront, and Route 53 is required.',
        )
        self.assertEqual(
            suggestions,
            ['Have you used DynamoDB, CloudFront, or Route 53?'],
        )

    def test_configured_staging_origin_can_record_client_events(self):
        with patch.object(
            product, '_public_base_url',
            'https://resumeradar-staging.onrender.com',
        ):
            self.assertTrue(product._origin_allowed(
                'https://resumeradar-staging.onrender.com'
            ))
            self.assertTrue(product._origin_allowed(
                'https://resumeradar-staging.onrender.com/build?from=scan'
            ))

    def test_unknown_domain_returns_no_score_through_api_and_pdf(self):
        with patch.dict(os.environ, {}, clear=True):
            response = product.app.test_client().post('/api/scan', data={
                'resume_text': 'Experience: Led managed built created designed deployed automated implemented bouquets for customers. Education: school. Skills: floristry. I arrange seasonal bouquets and help customers choose flowers for special occasions.',
                'job_description': 'We seek a florist to arrange bouquets and care for blooms in our shop every day.',
            })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNone(data['match_score'])
        self.assertEqual(data['score_status'], 'insufficient_evidence')
        self.assertNotIn('0%', data['ai_suggestions']['summary'])
        self.assertTrue(bytes(generate_pdf_report(data)).startswith(b'%PDF'))

    def test_fallback_advice_uses_priorities_and_truthful_language(self):
        result = _get_fallback_suggestions({'overall_score': None, 'priority_recommendations':[
            {'keyword':'python','category':'technical_skills','priority':'required','reason':'Required','suggestion':'If you have used Python, describe a project.'}
        ]})
        self.assertNotIn('0%', result['summary'])
        self.assertIn('If you have used Python', ' '.join(result['quick_wins']))

    def test_journey_from_scan_reaches_server_completion(self):
        from uuid import uuid4
        journey = str(uuid4())
        with patch.dict(os.environ, {}, clear=True), patch.object(product.funnel_metrics, 'record') as record:
            response = product.app.test_client().post('/api/scan', data={
                'resume_text':'Experience: Built Python and AWS applications using Docker for customers. Education: degree. Skills: Python AWS Docker. I maintain reliable services and work closely with developers on customer applications.',
                'job_description':'Requirements: Python AWS Docker. You will build applications and deploy services for our customers.',
                'journey_id':journey,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['score_version'], '2')
        record.assert_any_call('scan_completed', journey)

if __name__ == '__main__': unittest.main()

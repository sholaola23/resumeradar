"""
ATS Job Scanner — Main Application
A tool that helps job seekers optimize their resumes for ATS systems.
Built by Olushola Oladipupo
"""

import os
import json
import uuid
import secrets
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from flask_limiter import Limiter
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from backend.resume_parser import parse_resume
from backend.keyword_engine import extract_keywords_from_text, calculate_match, analyze_ats_formatting
from backend.ai_analyzer import get_ai_suggestions
from backend.report_generator import generate_pdf_report

# Load environment variables (override=True ensures .env values take priority)
load_dotenv(override=True)

# Initialize Flask app
app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static'
)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
CORS(app)

# Rate limiting — protect API credits and prevent abuse
# Use X-Forwarded-For header behind Render's proxy to get real client IP
def get_real_ip():
    """Get the real client IP, handling Render's reverse proxy."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

limiter = Limiter(
    app=app,
    key_func=get_real_ip,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://",
)

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ============================================================
# SCAN COUNTER (env var base + in-memory session counter)
# ============================================================
# SCAN_COUNT_BASE: Set in Render env vars to the total count at last deploy.
#   Before each deploy, check /api/scan-count and update this value.
#   Between deploys, _session_scans tracks new scans in memory.
_SCAN_COUNT_BASE = int(os.getenv('SCAN_COUNT_BASE', '150'))
_session_scans = 0
_counter_lock = threading.Lock()


def _read_scan_count():
    """Return total scan count: base (from env var) + scans since this deploy."""
    return _SCAN_COUNT_BASE + _session_scans


def _increment_scan_count():
    """Increment the session counter. Thread-safe."""
    global _session_scans
    with _counter_lock:
        _session_scans += 1
        return _SCAN_COUNT_BASE + _session_scans


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
@limiter.exempt
def index():
    """Serve the main application page."""
    return render_template('index.html')


@app.route('/api/scan', methods=['POST'])
@limiter.limit("15 per hour")
def scan_resume():
    """
    Main API endpoint: analyze resume against job description.

    Accepts:
        - resume_file: uploaded PDF or DOCX file
        - resume_text: pasted resume text
        - job_description: the job description text (required)

    Returns:
        JSON with match score, missing keywords, suggestions, and ATS tips.
    """
    try:
        # 1. Get the job description
        job_description = request.form.get('job_description', '').strip()
        if not job_description:
            return jsonify({"error": "Please provide a job description."}), 400

        if len(job_description.split()) < 10:
            return jsonify({"error": "The job description seems too short. Please paste the full job description."}), 400

        # 2. Get the resume (file upload or pasted text)
        resume_text = request.form.get('resume_text', '').strip()
        resume_file = request.files.get('resume_file')

        file_path = None
        file_type = None

        if resume_file and resume_file.filename:
            # Handle file upload
            if not allowed_file(resume_file.filename):
                return jsonify({"error": "Please upload a PDF or DOCX file."}), 400

            # Save with unique filename to prevent collisions
            filename = secure_filename(resume_file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            resume_file.save(file_path)
            file_type = filename.rsplit('.', 1)[1].lower()

        elif not resume_text:
            return jsonify({"error": "Please upload a resume file or paste your resume text."}), 400

        # 3. Parse the resume
        parse_result = parse_resume(
            file_path=file_path,
            pasted_text=resume_text if not file_path else None,
            file_type=file_type
        )

        # Clean up uploaded file immediately after parsing
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        if parse_result["error"]:
            return jsonify({"error": parse_result["error"]}), 400

        extracted_resume_text = parse_result["text"]

        # 4. Extract keywords from both resume and job description
        resume_keywords = extract_keywords_from_text(extracted_resume_text)
        job_keywords = extract_keywords_from_text(job_description)

        # 5. Calculate match
        match_results = calculate_match(resume_keywords, job_keywords)

        # 6. Analyze ATS formatting
        ats_check = analyze_ats_formatting(extracted_resume_text)

        # 7. Get AI-powered suggestions
        ai_suggestions = get_ai_suggestions(
            extracted_resume_text,
            job_description,
            match_results
        )

        # 8. Increment scan counter
        _increment_scan_count()

        # 9. Compile final response
        response = {
            "success": True,
            "match_score": match_results["overall_score"],
            "simple_match_ratio": match_results["simple_match_ratio"],
            "total_job_keywords": match_results["total_job_keywords"],
            "total_matched": match_results["total_matched"],
            "total_missing": match_results["total_missing"],
            "category_scores": match_results["category_scores"],
            "matched_keywords": match_results["matched_keywords"],
            "missing_keywords": match_results["missing_keywords"],
            "ats_formatting": ats_check,
            "ai_suggestions": ai_suggestions,
            "resume_word_count": parse_result["word_count"],
        }

        return jsonify(response)

    except Exception as e:
        # Clean up file on error
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)

        print(f"Scan error: {str(e)}")
        return jsonify({"error": "Something went wrong during the analysis. Please try again."}), 500


@app.route('/api/download-report', methods=['POST'])
@limiter.limit("20 per hour")
def download_report():
    """
    Generate and return a PDF report from scan data.

    Accepts:
        JSON body with the scan results data.

    Returns:
        PDF file download.
    """
    try:
        scan_data = request.get_json()
        if not scan_data:
            return jsonify({"error": "No scan data provided."}), 400

        pdf_bytes = bytes(generate_pdf_report(scan_data))

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': 'attachment; filename=ResumeRadar_Report.pdf',
                'Content-Type': 'application/pdf',
                'Content-Length': str(len(pdf_bytes))
            }
        )

    except Exception as e:
        print(f"PDF generation error: {str(e)}")
        return jsonify({"error": "Failed to generate PDF report."}), 500


@app.route('/api/email-report', methods=['POST'])
@limiter.limit("10 per hour")
def email_report():
    """
    Send the ATS scan report via email using Resend.

    Accepts:
        JSON body with 'email' and 'scan_data'.

    Returns:
        JSON success/error response.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        email = data.get('email', '').strip()
        scan_data = data.get('scan_data')

        if not email or '@' not in email:
            return jsonify({"error": "Please provide a valid email address."}), 400

        if not scan_data:
            return jsonify({"error": "No scan data provided."}), 400

        # Check for Resend API key
        resend_key = os.getenv('RESEND_API_KEY')
        if not resend_key or resend_key == 'your-resend-api-key-here':
            return jsonify({"error": "Email service is not configured yet. Please download or copy your report instead."}), 503

        import resend
        resend.api_key = resend_key

        # Generate the PDF attachment
        pdf_bytes = bytes(generate_pdf_report(scan_data))

        score = scan_data.get('match_score', 0)
        ai = scan_data.get('ai_suggestions', {}) or {}
        summary = ai.get('summary', 'Your ATS scan report is ready.')

        # Sanitize summary — strip any JSON/markdown artifacts that may have leaked through
        if summary and ('```' in summary or '"summary"' in summary or summary.strip().startswith('{')):
            for artifact in ['```json', '```', '{', '}', '"summary":', '"summary" :']:
                summary = summary.replace(artifact, '')
            summary = summary.strip().strip('"').strip()
            if not summary:
                summary = 'Your ATS scan report is ready.'

        # Build the HTML email body
        html_body = f"""
        <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1f2937;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); padding: 32px 24px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">ResumeRadar</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0; font-size: 14px;">Beat the scan. Land the interview.</p>
            </div>

            <div style="background: white; padding: 32px 24px; border: 1px solid #e5e7eb; border-top: none;">
                <h2 style="margin: 0 0 8px; font-size: 20px; color: #1f2937;">Your ATS Match Score</h2>

                <div style="text-align: center; margin: 24px 0;">
                    <span style="font-size: 56px; font-weight: 800; color: {'#059669' if score >= 75 else '#d97706' if score >= 50 else '#dc2626'};">{score}%</span>
                </div>

                <p style="font-size: 15px; line-height: 1.6; color: #4b5563;">{summary}</p>

                <div style="display: flex; justify-content: space-around; margin: 24px 0; text-align: center;">
                    <div>
                        <div style="font-size: 24px; font-weight: 800; color: #059669;">{scan_data.get('total_matched', 0)}</div>
                        <div style="font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px;">Matched</div>
                    </div>
                    <div>
                        <div style="font-size: 24px; font-weight: 800; color: #dc2626;">{scan_data.get('total_missing', 0)}</div>
                        <div style="font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px;">Missing</div>
                    </div>
                    <div>
                        <div style="font-size: 24px; font-weight: 800; color: #1f2937;">{scan_data.get('total_job_keywords', 0)}</div>
                        <div style="font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px;">Total</div>
                    </div>
                </div>

                <div style="background: #f3f4f6; padding: 16px; border-radius: 8px; margin-top: 24px;">
                    <p style="margin: 0; font-size: 13px; color: #6b7280;">
                        Your full detailed report is attached as a PDF, including keyword breakdowns,
                        AI suggestions, and ATS formatting checks.
                    </p>
                </div>
            </div>

            <div style="background: #1f2937; padding: 24px; border-radius: 0 0 12px 12px; text-align: center;">
                <p style="color: #9ca3af; margin: 0 0 4px; font-size: 13px;">Built by <a href="https://www.linkedin.com/in/olushola-oladipupo/" style="color: #93c5fd; text-decoration: none;">Olushola Oladipupo</a></p>
                <p style="color: #6b7280; margin: 0; font-size: 11px;">Your resume is analyzed in real-time and never stored.</p>
            </div>
        </div>
        """

        # Send the email with PDF attachment
        import base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        params = {
            "from": "ResumeRadar <reports@sholastechnotes.com>",
            "to": [email],
            "subject": f"Your ResumeRadar Report — ATS Match Score: {score}%",
            "html": html_body,
            "attachments": [
                {
                    "filename": "ResumeRadar_Report.pdf",
                    "content": pdf_base64,
                }
            ],
        }

        result = resend.Emails.send(params)

        return jsonify({
            "success": True,
            "message": f"Report sent to {email}!"
        })

    except Exception as e:
        print(f"Email sending error: {str(e)}")
        return jsonify({"error": f"Failed to send email. Please try downloading the report instead."}), 500


@app.route('/api/subscribe', methods=['POST'])
@limiter.limit("10 per hour")
def subscribe_newsletter():
    """
    Subscribe a user to the Beehiiv newsletter.

    Accepts:
        JSON body with 'email'.

    Returns:
        JSON success/error response.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        email = data.get('email', '').strip()
        first_name = data.get('first_name', '').strip()

        if not email or '@' not in email:
            return jsonify({"error": "Please provide a valid email address."}), 400

        if not first_name:
            return jsonify({"error": "Please provide your first name."}), 400

        beehiiv_key = os.getenv('BEEHIIV_API_KEY')
        pub_id = os.getenv('BEEHIIV_PUBLICATION_ID')

        if not beehiiv_key or not pub_id:
            return jsonify({"error": "Newsletter service is not configured."}), 503

        import requests as http_requests

        # Build the subscription payload with first name as custom field
        subscription_data = {
            'email': email,
            'reactivate_existing': True,
            'send_welcome_email': True,
            'utm_source': 'resumeradar',
            'custom_fields': [
                {
                    'name': 'first_name',
                    'value': first_name,
                }
            ],
        }

        response = http_requests.post(
            f'https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions',
            headers={
                'Authorization': f'Bearer {beehiiv_key}',
                'Content-Type': 'application/json',
            },
            json=subscription_data,
            timeout=10,
        )

        if response.status_code in [200, 201]:
            return jsonify({
                "success": True,
                "message": "You're subscribed! Check your inbox."
            })
        else:
            error_msg = response.json().get('message', 'Subscription failed')
            print(f"Beehiiv API error: {response.status_code} - {error_msg}")
            return jsonify({"error": "Could not subscribe. Please try again."}), 500

    except Exception as e:
        print(f"Newsletter subscription error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route('/api/health', methods=['GET'])
@limiter.exempt
def health_check():
    """Health check endpoint."""
    has_api_key = bool(os.getenv('ANTHROPIC_API_KEY')) and os.getenv('ANTHROPIC_API_KEY') != 'your-anthropic-api-key-here'
    return jsonify({
        "status": "healthy",
        "ai_enabled": has_api_key,
    })


@app.route('/api/scan-count', methods=['GET'])
@limiter.exempt
def get_scan_count():
    """Return the total number of resumes scanned."""
    count = _read_scan_count()
    return jsonify({"count": count})


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def add_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    # Only add HSTS in production
    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please wait a few minutes and try again."}), 429


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 5MB."}), 413


@app.errorhandler(404)
def not_found(e):
    """Serve branded 404 page for browser requests, JSON for API requests."""
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not found."}), 404
    return render_template('404.html'), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed."}), 405


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error. Please try again."}), 500


# ============================================================
# RUN
# ============================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'
    print(f"\n📡 ResumeRadar running at http://localhost:{port}")
    print(f"   AI Suggestions: {'✅ Enabled' if os.getenv('ANTHROPIC_API_KEY') else '❌ No API key found'}")
    print(f"   Debug mode: {'On' if debug else 'Off'}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)

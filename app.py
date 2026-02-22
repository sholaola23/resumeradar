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
import html as html_module
import re as re_module
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from flask_limiter import Limiter
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from backend.resume_parser import parse_resume
from backend.keyword_engine import extract_keywords_from_text, calculate_match, analyze_ats_formatting
from backend.ai_analyzer import get_ai_suggestions
from backend.report_generator import generate_pdf_report
from backend.cv_builder import polish_cv_sections, extract_and_polish
from backend.cv_pdf_generator import generate_cv_pdf
from backend.stripe_utils import create_checkout_session, verify_checkout_payment, verify_webhook_signature

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
# SCAN COUNTER (Redis-backed, persistent across deploys)
# ============================================================
# Set REDIS_URL in Render env vars (from Upstash free tier).
# Falls back to in-memory counting if Redis is unavailable.
_redis_client = None
_REDIS_KEY = 'resumeradar:scan_count'

try:
    _redis_url = os.getenv('REDIS_URL')
    if _redis_url:
        import redis
        _redis_client = redis.from_url(_redis_url, decode_responses=True)
        _redis_client.ping()  # Verify connection
        # Seed the counter if it doesn't exist yet
        if _redis_client.get(_REDIS_KEY) is None:
            _redis_client.set(_REDIS_KEY, int(os.getenv('SCAN_COUNT_BASE', '150')))
        print("📊 Scan counter: Redis connected (persistent)")
    else:
        print("📊 Scan counter: in-memory fallback (no REDIS_URL)")
except Exception as e:
    print(f"📊 Scan counter: in-memory fallback (Redis error: {e})")
    _redis_client = None

# In-memory fallback
_fallback_count = int(os.getenv('SCAN_COUNT_BASE', '150'))
_counter_lock = threading.Lock()


def _read_scan_count():
    """Read the current scan count."""
    if _redis_client:
        try:
            return int(_redis_client.get(_REDIS_KEY) or 0)
        except Exception:
            return _fallback_count
    return _fallback_count


def _increment_scan_count():
    """Increment and return the new scan count, plus track hourly velocity."""
    global _fallback_count
    if _redis_client:
        try:
            count = _redis_client.incr(_REDIS_KEY)
            # Track hourly scan velocity for social proof
            hour_key = f'resumeradar:scans_hour:{datetime.now(timezone.utc).strftime("%Y%m%d%H")}'
            _redis_client.incr(hour_key)
            _redis_client.expire(hour_key, 7200)  # expire after 2 hours
            return count
        except Exception:
            pass
    # Fallback: in-memory
    with _counter_lock:
        _fallback_count += 1
        return _fallback_count


def _read_scan_velocity():
    """Read the number of scans in the current hour."""
    if _redis_client:
        try:
            hour_key = f'resumeradar:scans_hour:{datetime.now(timezone.utc).strftime("%Y%m%d%H")}'
            return int(_redis_client.get(hour_key) or 0)
        except Exception:
            return 0
    return 0


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
@limiter.exempt
def index():
    """Serve the main application page with dynamic OG image based on score tier."""
    score_tier = request.args.get('score_tier', '')
    og_images = {
        'low': 'og-score-low.png',
        'mid': 'og-score-mid.png',
        'high': 'og-score-high.png',
    }
    og_image = og_images.get(score_tier, 'og-image.png')
    return render_template('index.html', og_image=og_image)


@app.route('/favicon.ico')
@limiter.exempt
def favicon():
    """Serve favicon from static folder (browsers request this from root)."""
    return send_from_directory(app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
@limiter.exempt
def apple_touch_icon():
    """Serve apple-touch-icon (iPhones request this from root)."""
    return send_from_directory(os.path.join(app.static_folder, 'images'), 'apple-touch-icon.png', mimetype='image/png')


@app.route('/robots.txt')
@limiter.exempt
def robots_txt():
    """Serve robots.txt for search engine crawlers."""
    return send_from_directory(app.static_folder, 'robots.txt', mimetype='text/plain')


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
            "resume_text": extracted_resume_text,
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
        utm_source = data.get('utm_source', 'resumeradar').strip()

        if not email or '@' not in email:
            return jsonify({"error": "Please provide a valid email address."}), 400

        if not first_name:
            return jsonify({"error": "Please provide your first name."}), 400

        beehiiv_key = os.getenv('BEEHIIV_API_KEY')
        pub_id = os.getenv('BEEHIIV_PUBLICATION_ID')

        if not beehiiv_key or not pub_id:
            return jsonify({"error": "Newsletter service is not configured."}), 503

        import requests as http_requests

        # Build the subscription payload
        subscription_data = {
            'email': email,
            'reactivate_existing': True,
            'send_welcome_email': True,
            'utm_source': utm_source,
        }

        # Add first name as custom field if provided
        if first_name:
            subscription_data['custom_fields'] = [
                {
                    'name': 'first_name',
                    'value': first_name,
                }
            ]

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
    """Return the total number of resumes scanned and hourly velocity."""
    count = _read_scan_count()
    velocity = _read_scan_velocity()
    return jsonify({"count": count, "velocity": velocity})


# ============================================================
# CV BUILDER ROUTES
# ============================================================

@app.route('/build')
@limiter.exempt
def build_page():
    """Serve the CV Builder page."""
    return render_template('build.html')


@app.route('/api/build/generate', methods=['POST'])
@limiter.limit("5 per hour")
def build_generate():
    """
    Accept CV form data, polish with AI, store in Redis, return preview + token.

    Accepts:
        JSON body with personal, summary, experience, education, skills,
        certifications, target_job_description.

    Returns:
        JSON with polished CV data and a token for later PDF download.
    """
    try:
        cv_data = request.get_json()
        if not cv_data:
            return jsonify({"error": "No CV data provided."}), 400

        if not cv_data.get("target_job_description", "").strip():
            return jsonify({"error": "Please provide a target job description."}), 400

        personal = cv_data.get("personal", {})
        if not personal.get("full_name", "").strip():
            return jsonify({"error": "Please provide your full name."}), 400

        # Polish with AI
        polished = polish_cv_sections(cv_data)

        # Generate a token and store in Redis
        token = uuid.uuid4().hex
        cv_redis_key = f"resumeradar:cv:{token}"

        if _redis_client:
            try:
                import json as _json
                _redis_client.setex(cv_redis_key, 7200, _json.dumps(polished))  # 2hr TTL
            except Exception as redis_err:
                print(f"Redis store error: {redis_err}")
                # Fallback: return data to frontend to store in sessionStorage
                return jsonify({
                    "success": True,
                    "token": token,
                    "polished": polished,
                    "storage": "client",
                })
        else:
            # No Redis: return data to frontend
            return jsonify({
                "success": True,
                "token": token,
                "polished": polished,
                "storage": "client",
            })

        return jsonify({
            "success": True,
            "token": token,
            "polished": polished,
            "storage": "server",
        })

    except Exception as e:
        print(f"CV Builder generate error: {str(e)}")
        return jsonify({"error": "Something went wrong generating your CV. Please try again."}), 500


@app.route('/api/build/generate-from-scan', methods=['POST'])
@limiter.limit("5 per hour")
def build_generate_from_scan():
    """
    One-shot scan-to-CV: extract structured data from raw resume text
    and polish for ATS — no form needed.

    Accepts:
        JSON body with resume_text, job_description, and optional scan_keywords

    Returns:
        JSON with polished CV data and a token for payment/download.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        resume_text = data.get("resume_text", "").strip()
        job_description = data.get("job_description", "").strip()
        scan_keywords = data.get("scan_keywords")

        if not resume_text:
            return jsonify({"error": "Resume text is missing."}), 400
        if not job_description:
            return jsonify({"error": "Job description is missing."}), 400

        # One AI call: extract structure + polish for ATS
        polished = extract_and_polish(resume_text, job_description, scan_keywords)

        if polished.get("error"):
            return jsonify({"error": polished["error"]}), 500

        # Generate token and store
        token = uuid.uuid4().hex
        cv_redis_key = f"resumeradar:cv:{token}"

        if _redis_client:
            try:
                import json as _json
                _redis_client.setex(cv_redis_key, 7200, _json.dumps(polished))
            except Exception as redis_err:
                print(f"Redis store error: {redis_err}")
                return jsonify({
                    "success": True,
                    "token": token,
                    "polished": polished,
                    "storage": "client",
                })
        else:
            return jsonify({
                "success": True,
                "token": token,
                "polished": polished,
                "storage": "client",
            })

        return jsonify({
            "success": True,
            "token": token,
            "polished": polished,
            "storage": "server",
        })

    except Exception as e:
        print(f"CV Builder scan-generate error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route('/api/build/create-checkout', methods=['POST'])
@limiter.limit("10 per hour")
def build_create_checkout():
    """
    Create a Stripe Checkout session for CV download payment.

    Accepts:
        JSON with token and template.

    Returns:
        JSON with checkout_url to redirect to.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        token = data.get("token", "").strip()
        template = data.get("template", "classic").strip()

        if not token:
            return jsonify({"error": "Missing CV token."}), 400

        # Verify the token exists in Redis
        if _redis_client:
            try:
                cv_redis_key = f"resumeradar:cv:{token}"
                if not _redis_client.exists(cv_redis_key):
                    return jsonify({"error": "CV session expired. Please regenerate your CV."}), 400
            except Exception:
                pass  # Proceed anyway if Redis check fails

        # Validate optional delivery email
        delivery_email = data.get("delivery_email", "").strip()
        if delivery_email:
            try:
                from email_validator import validate_email, EmailNotValidError
                valid = validate_email(delivery_email, check_deliverability=False)
                delivery_email = valid.normalized
            except EmailNotValidError:
                return jsonify({"error": "Please enter a valid email address."}), 400
            except ImportError:
                # email-validator not installed — basic sanity check as fallback
                print("WARNING: email-validator not installed. Using basic email check.")
                if "@" not in delivery_email or "." not in delivery_email.split("@")[-1]:
                    return jsonify({"error": "Please enter a valid email address."}), 400

        # Build success/cancel URLs
        base_url = request.host_url.rstrip('/')
        success_url = f"{base_url}/build?payment=success&token={token}&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/build?payment=cancelled"

        result = create_checkout_session(token, template, success_url, cancel_url, delivery_email)

        if result.get("error"):
            return jsonify({"error": result["error"]}), 500

        return jsonify({
            "success": True,
            "checkout_url": result["checkout_url"],
            "session_id": result["session_id"],
        })

    except Exception as e:
        print(f"CV Builder checkout error: {str(e)}")
        return jsonify({"error": "Could not create payment session."}), 500


@app.route('/api/build/download/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def build_download(token):
    """
    Verify payment, generate PDF with chosen template, return download.

    GET (server storage / Redis):
        Query params: session_id, template
    POST (client storage fallback):
        JSON body: { session_id, template, cv_data }
    """
    try:
        # Parse params from GET query string or POST body
        if request.method == 'POST':
            body = request.get_json() or {}
            session_id = body.get("session_id", "").strip()
            template = body.get("template", "classic").strip()
            client_cv_data = body.get("cv_data")
        else:
            session_id = request.args.get("session_id", "").strip()
            template = request.args.get("template", "classic").strip()
            client_cv_data = None

        if not session_id:
            return jsonify({"error": "Missing payment session."}), 400

        # Verify payment
        payment = verify_checkout_payment(session_id, token)
        if not payment.get("verified"):
            return jsonify({"error": payment.get("reason", "Payment verification failed.")}), 403

        # Use template from payment metadata if available
        template = payment.get("template", template)

        # Get CV data: try Redis first, fall back to client-provided data
        cv_data = None
        if _redis_client:
            try:
                cv_redis_key = f"resumeradar:cv:{token}"
                stored = _redis_client.get(cv_redis_key)
                if stored:
                    cv_data = json.loads(stored)

                    # Check download limit (max 3)
                    dl_key = f"resumeradar:cv_downloads:{token}"
                    dl_count = int(_redis_client.get(dl_key) or 0)
                    if dl_count >= 3:
                        return jsonify({"error": "Download limit reached (3 downloads max)."}), 403
                    _redis_client.incr(dl_key)
                    _redis_client.expire(dl_key, 7200)
            except Exception as redis_err:
                print(f"Redis retrieve error: {redis_err}")

        # Fallback: use CV data from client (sessionStorage)
        if not cv_data and client_cv_data:
            cv_data = client_cv_data

        if not cv_data:
            return jsonify({"error": "CV data not found. It may have expired. Please regenerate."}), 404

        # Generate PDF
        pdf_bytes = bytes(generate_cv_pdf(cv_data, template))

        raw_name = cv_data.get("personal", {}).get("full_name", "Resume")
        safe_name = re_module.sub(r'[^\w.-]', '_', raw_name)
        filename = f"{safe_name}_CV.pdf"

        # Check if email delivery was requested (from Stripe metadata)
        delivery_email = payment.get("delivery_email", "")

        response = Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename={filename}',
                'Content-Type': 'application/pdf',
                'Content-Length': str(len(pdf_bytes))
            }
        )
        response.headers['X-Email-Requested'] = 'true' if delivery_email else 'false'
        return response

    except Exception as e:
        print(f"CV Builder download error: {str(e)}")
        return jsonify({"error": "Failed to generate PDF."}), 500


def _send_cv_email(email, token, template, event_id):
    """
    Send CV PDF via email. Uses SETNX on Stripe event.id for strict idempotency.
    Best-effort: if this fails, Stripe retries the webhook and we try again.
    Synchronous: ~3-4s total (SETNX + Redis GET + fpdf2 + Resend API).
    """
    try:
        if not _redis_client:
            return

        # Strict idempotency: SETNX on event.id, 72h TTL matches Stripe retry window
        dedup_key = f"resumeradar:cv_emailed:{event_id}"
        was_set = _redis_client.set(dedup_key, "1", nx=True, ex=259200)
        if not was_set:
            return  # Already sent or being sent by this event

        # Read CV data (TTL extended to 72h by webhook caller)
        cv_data_raw = _redis_client.get(f"resumeradar:cv:{token}")
        if not cv_data_raw:
            _redis_client.delete(dedup_key)  # Release so retry can try again
            return

        cv_data = json.loads(cv_data_raw)
        resend_key = os.getenv('RESEND_API_KEY')
        if not resend_key or resend_key == 'your-resend-api-key-here':
            _redis_client.delete(dedup_key)
            return

        import resend
        import base64
        resend.api_key = resend_key

        pdf_bytes = bytes(generate_cv_pdf(cv_data, template))
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        # Sanitize user-derived values
        raw_name = cv_data.get('personal', {}).get('full_name', 'there')
        first_name = html_module.escape(
            raw_name.split()[0] if raw_name and raw_name != 'there' else 'there'
        )
        safe_name = re_module.sub(r'[^\w.-]', '_', raw_name) if raw_name != 'there' else 'ResumeRadar'
        filename = f"{safe_name}_CV.pdf"

        html_body = f"""<div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1f2937;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); padding: 32px 24px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">ResumeRadar</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0; font-size: 14px;">Your ATS-optimized CV is ready.</p>
            </div>
            <div style="background: white; padding: 32px 24px; border: 1px solid #e5e7eb; border-top: none;">
                <h2 style="margin: 0 0 12px; font-size: 20px;">Hi {first_name},</h2>
                <p style="font-size: 15px; line-height: 1.6; color: #4b5563;">Your polished CV is attached. It has been tailored for ATS systems.</p>
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">Next steps:</p>
                    <ul style="margin: 8px 0 0; padding-left: 20px; color: #374151; font-size: 14px; line-height: 1.8;">
                        <li>Submit your CV to the target job posting</li>
                        <li>Scan another resume at resumeradar.sholastechnotes.com</li>
                        <li>Tailor a new CV for each different role</li>
                    </ul>
                </div>
            </div>
            <div style="background: #1f2937; padding: 24px; border-radius: 0 0 12px 12px; text-align: center;">
                <p style="color: #9ca3af; margin: 0; font-size: 11px;">Your resume was processed in real-time and not stored.</p>
            </div>
        </div>"""

        resend.Emails.send({
            "from": "ResumeRadar <reports@sholastechnotes.com>",
            "to": [email],
            "subject": f"Your ResumeRadar CV is ready, {first_name}",
            "html": html_body,
            "attachments": [{"filename": filename, "content": pdf_base64}],
        })

    except Exception as e:
        print(f"CV email error (best-effort): {e}")
        # Release dedup flag on failure so Stripe retries can succeed
        try:
            if _redis_client:
                _redis_client.delete(f"resumeradar:cv_emailed:{event_id}")
        except Exception:
            pass


@app.route('/api/build/webhook', methods=['POST'])
@limiter.exempt
def build_webhook():
    """
    Stripe webhook handler. Marks CV token as paid in Redis.
    """
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature', '')

        event = verify_webhook_signature(payload, sig_header)
        if not event:
            return jsonify({"error": "Invalid signature."}), 400

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            cv_token = session.get('metadata', {}).get('cv_token', '')
            template = session.get('metadata', {}).get('template', 'classic')
            delivery_email = session.get('metadata', {}).get('delivery_email', '')

            if cv_token and _redis_client:
                try:
                    paid_key = f"resumeradar:cv_paid:{cv_token}"
                    _redis_client.setex(paid_key, 7200, "1")
                    # Extend CV data TTL to survive Stripe retry window (72h)
                    _redis_client.expire(f"resumeradar:cv:{cv_token}", 259200)
                except Exception:
                    pass

            # Send email if requested (best-effort, synchronous ~3-4s)
            if delivery_email and cv_token:
                _send_cv_email(delivery_email, cv_token, template, event['id'])

        return jsonify({"received": True}), 200

    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return jsonify({"error": "Webhook processing failed."}), 500


@app.route('/api/build/check-payment/<token>', methods=['GET'])
@limiter.limit("30 per hour")
def build_check_payment(token):
    """
    Check if payment has been confirmed for a CV token (frontend polls this).
    """
    try:
        if _redis_client:
            paid_key = f"resumeradar:cv_paid:{token}"
            is_paid = _redis_client.get(paid_key)
            return jsonify({"paid": bool(is_paid)})
        return jsonify({"paid": False})
    except Exception:
        return jsonify({"paid": False})


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
    # Prevent browser caching of CV builder API responses (PII protection)
    if request.path.startswith('/api/build/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
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

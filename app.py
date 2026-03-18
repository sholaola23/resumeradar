"""
ATS Job Scanner — Main Application
A tool that helps job seekers optimize their resumes for ATS systems.
Built by Olushola Oladipupo
"""

import os
import json
import uuid
import hmac as hmac_module
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
import html as html_module
import re as re_module
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from flask_limiter import Limiter
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from backend.resume_parser import parse_resume
from backend.keyword_engine import extract_keywords_from_text, calculate_match, analyze_ats_formatting, calculate_recruiter_tips_score
from backend.ai_analyzer import get_ai_suggestions, generate_cover_letter, enhance_bullet_point, generate_resume_summary
from backend.report_generator import generate_pdf_report
from backend.cv_builder import polish_cv_sections, extract_and_polish
from backend.cv_pdf_generator import generate_cv_pdf
from backend.cv_docx_generator import generate_cv_docx
import stripe
from backend.stripe_utils import (
    create_checkout_session, verify_checkout_payment, verify_webhook_signature,
    create_bundle_checkout_session, verify_bundle_payment,
)
from backend.paystack_utils import (
    create_paystack_transaction,
    verify_paystack_payment,
    verify_paystack_webhook,
    format_naira_price,
    create_paystack_bundle_transaction,
)
from backend import audit_log
from backend import ai_cache
from backend import ai_budget
from backend import ai_metrics
from backend import ai_ratelimit
from backend import bundle_credits
from backend import funnel_metrics

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
    """Get the real client IP behind Render's single reverse proxy.

    Render's proxy sets X-Forwarded-For to: <client_ip>[, <cdn_ip>, ...].
    With one trusted proxy (Render), the second-to-last entry is the real
    client IP. If there's only one entry, that IS the client IP (set by
    Render). We never trust the first entry in a multi-hop chain because
    a client can prepend spoofed values.

    Falls back to remote_addr if X-Forwarded-For is missing or invalid.
    """
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        parts = [p.strip() for p in forwarded.split(',') if p.strip()]
        if parts:
            # Single trusted proxy (Render): client IP is second-to-last.
            # If only 1 entry, Render set it directly — that's the client.
            idx = max(0, len(parts) - 1) if len(parts) <= 1 else len(parts) - 2
            ip = parts[idx]
            # Basic validation: must look like an IP (IPv4 or IPv6), not garbage
            if re_module.match(r'^[\d.:a-fA-F]+$', ip):
                return ip
    return request.remote_addr or '127.0.0.1'

_redis_limiter_uri = os.getenv('REDIS_URL', 'memory://')
limiter = Limiter(
    app=app,
    key_func=get_real_ip,
    default_limits=["5000 per day", "1000 per hour"],
    storage_uri=_redis_limiter_uri,
)

# Exempt static assets from rate limiting — they'd burn through global limits during spikes
@limiter.request_filter
def _exempt_static():
    return request.path.startswith('/static/')

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Beehiiv async subscription pool — bounded to prevent thread explosion under spike load.
# Each Gunicorn worker gets its own pool (3 workers × 3 threads = 9 Beehiiv threads total).
# Semaphore caps pending queue at 50 per worker to prevent unbounded growth.
_beehiiv_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='beehiiv')
_beehiiv_semaphore = threading.Semaphore(50)

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

# Initialize audit log module with Redis client
audit_log.init(_redis_client)

# Initialize AI cost economics modules (2E)
ai_cache.init(_redis_client)
ai_budget.init(_redis_client)
ai_metrics.init(_redis_client)
ai_ratelimit.init(_redis_client)
bundle_credits.init(_redis_client)
funnel_metrics.init(_redis_client)

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


# Public base URL for payment callbacks — env var preferred over request.host_url
# which can be unreliable behind proxies/CDNs
_public_base_url = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')


def _get_base_url():
    """Return trusted base URL for payment callbacks. Env var preferred over request.host_url."""
    return _public_base_url or request.host_url.rstrip('/')


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


@app.route('/sitemap.xml')
@limiter.exempt
def sitemap_xml():
    """Serve sitemap.xml for search engines and AI crawlers."""
    base = 'https://resumeradar.sholastechnotes.com'
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    pages = [
        {'loc': f'{base}/', 'priority': '1.0', 'changefreq': 'weekly'},
        {'loc': f'{base}/build', 'priority': '0.8', 'changefreq': 'monthly'},
    ]
    xml_entries = '\n'.join(
        f'  <url>\n'
        f'    <loc>{p["loc"]}</loc>\n'
        f'    <lastmod>{today}</lastmod>\n'
        f'    <changefreq>{p["changefreq"]}</changefreq>\n'
        f'    <priority>{p["priority"]}</priority>\n'
        f'  </url>'
        for p in pages
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{xml_entries}\n'
        '</urlset>'
    )
    return Response(xml, mimetype='application/xml')


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
        job_keywords = extract_keywords_from_text(job_description, strict=True)

        # 5. Calculate match
        match_results = calculate_match(resume_keywords, job_keywords)

        # 6. Analyze ATS formatting
        ats_check = analyze_ats_formatting(extracted_resume_text)

        # 6b. Calculate recruiter tips score
        recruiter_tips = calculate_recruiter_tips_score(extracted_resume_text, job_description)

        # 7. Get AI-powered suggestions
        ai_suggestions = get_ai_suggestions(
            extracted_resume_text,
            job_description,
            match_results
        )

        # 8. Increment scan counter + funnel analytics
        _increment_scan_count()
        funnel_metrics.record("scan_completed")

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
            "recruiter_tips": recruiter_tips,
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


@app.route('/api/generate/cover-letter', methods=['POST'])
@limiter.limit("10 per minute")
def generate_cover_letter_endpoint():
    """
    Generate a tailored cover letter from resume + job description.
    Burst limiter: 10/min (decorator). Daily limit: 3/day/IP (in-handler, H7).
    Bundle users bypass daily limit but are still subject to burst limiter.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        resume_text = (data.get('resume_text') or '').strip()
        job_description = (data.get('job_description') or '').strip()

        if not resume_text or len(resume_text) < 50:
            return jsonify({"error": "Please provide your resume text (at least 50 characters)."}), 400

        if not job_description or len(job_description.split()) < 10:
            return jsonify({"error": "Please provide a full job description."}), 400

        # In-handler daily rate limit with bundle override (H6, H7)
        bundle_token = (data.get('bundle_token') or '').strip()
        bundle_bypass = False
        if bundle_token:
            # Check bundle credit — if valid, bypass IP rate limit
            bundle_result = bundle_credits.use_credit(bundle_token, "cover_letter")
            if bundle_result.get("ok"):
                bundle_bypass = True
                # AUDIT: bundle credit used for cover letter
                try:
                    audit_log.log_event(
                        "bundle_credit_used",
                        token=bundle_token,
                        type="cover_letter",
                        remaining=bundle_result.get("remaining"),
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="cover-letter",
                    )
                except Exception:
                    pass
            # If bundle exhausted/expired, fall through to free tier (H6 rule 4)

        if not bundle_bypass:
            ip = get_real_ip()
            if not ai_ratelimit.check_and_increment("cover_letter", ip):
                ai_metrics.record_rate_reject(ai_metrics.TOOL_COVER_LETTER)
                return jsonify({"error": "Daily limit reached (3 per day). Try again tomorrow."}), 429

        result = generate_cover_letter(resume_text, job_description)

        if "error" in result:
            status = 503 if result["error"] == ai_budget.BUDGET_EXCEEDED_MESSAGE else 500
            return jsonify(result), status

        return jsonify(result)

    except Exception as e:
        print(f"Cover letter endpoint error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route('/api/tools/enhance-bullet', methods=['POST'])
@limiter.limit("10 per minute")
def enhance_bullet_endpoint():
    """
    Enhance a resume bullet point with AI.
    Burst limiter: 10/min (decorator). Daily limit: 10/day/IP (in-handler, H7).
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        bullet_text = (data.get('bullet_text') or '').strip()
        job_context = (data.get('job_context') or '').strip() or None

        if not bullet_text or len(bullet_text) < 10:
            return jsonify({"error": "Please provide a bullet point (at least 10 characters)."}), 400

        if len(bullet_text) > 500:
            return jsonify({"error": "Bullet point is too long (max 500 characters)."}), 400

        # In-handler daily rate limit (H7)
        ip = get_real_ip()
        if not ai_ratelimit.check_and_increment("enhance_bullet", ip):
            ai_metrics.record_rate_reject(ai_metrics.TOOL_ENHANCE_BULLET)
            return jsonify({"error": "Daily limit reached (10 per day). Try again tomorrow."}), 429

        result = enhance_bullet_point(bullet_text, job_context)

        if "error" in result:
            status = 503 if result["error"] == ai_budget.BUDGET_EXCEEDED_MESSAGE else 500
            return jsonify(result), status

        return jsonify(result)

    except Exception as e:
        print(f"Bullet enhance endpoint error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route('/api/tools/generate-summary', methods=['POST'])
@limiter.limit("10 per minute")
def generate_summary_endpoint():
    """
    Generate a professional resume summary.
    Burst limiter: 10/min (decorator). Daily limit: 5/day/IP (in-handler, H7).
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        resume_text = (data.get('resume_text') or '').strip()
        job_description = (data.get('job_description') or '').strip()

        if not resume_text or len(resume_text) < 50:
            return jsonify({"error": "Please provide resume text (at least 50 characters)."}), 400

        if not job_description or len(job_description.split()) < 10:
            return jsonify({"error": "Please provide a job description."}), 400

        # In-handler daily rate limit (H7)
        ip = get_real_ip()
        if not ai_ratelimit.check_and_increment("generate_summary", ip):
            ai_metrics.record_rate_reject(ai_metrics.TOOL_GENERATE_SUMMARY)
            return jsonify({"error": "Daily limit reached (5 per day). Try again tomorrow."}), 429

        result = generate_resume_summary(resume_text, job_description)

        if "error" in result:
            status = 503 if result["error"] == ai_budget.BUDGET_EXCEEDED_MESSAGE else 500
            return jsonify(result), status

        return jsonify(result)

    except Exception as e:
        print(f"Summary generation endpoint error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


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

        # Fire-and-forget: submit Beehiiv call to bounded thread pool.
        # Semaphore prevents unbounded queue growth under spike traffic.
        def _beehiiv_task():
            try:
                import requests as http_requests
                subscription_data = {
                    'email': email,
                    'reactivate_existing': True,
                    'send_welcome_email': True,
                    'utm_source': utm_source,
                }
                if first_name:
                    subscription_data['custom_fields'] = [
                        {'name': 'first_name', 'value': first_name}
                    ]
                resp = http_requests.post(
                    f'https://api.beehiiv.com/v2/publications/{pub_id}/subscriptions',
                    headers={
                        'Authorization': f'Bearer {beehiiv_key}',
                        'Content-Type': 'application/json',
                    },
                    json=subscription_data,
                    timeout=10,
                )
                if resp.status_code not in [200, 201]:
                    print(f"Beehiiv API error: {resp.status_code} - {resp.text[:200]}")
            except Exception as exc:
                print(f"Beehiiv background error: {exc}")
            finally:
                _beehiiv_semaphore.release()

        if _beehiiv_semaphore.acquire(blocking=False):
            try:
                _beehiiv_executor.submit(_beehiiv_task)
            except Exception:
                _beehiiv_semaphore.release()

        funnel_metrics.record("subscribe_completed")
        return jsonify({
            "success": True,
            "message": "You're subscribed! Check your inbox."
        })

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
    # Pass Paystack config to template so JS can check server capability
    paystack_enabled = bool(os.getenv('PAYSTACK_SECRET_KEY'))
    paystack_price = format_naira_price() if paystack_enabled else ''
    return render_template(
        'build.html',
        paystack_enabled=paystack_enabled,
        paystack_price=paystack_price,
    )


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


@app.route('/api/build/generate-from-upload', methods=['POST'])
@limiter.limit("5 per hour")
def build_generate_from_upload():
    """
    Accept a resume file upload + job description, parse the file,
    extract structured data, and polish for ATS.

    Accepts:
        multipart/form-data with resume_file (PDF/DOCX) and job_description (text)

    Returns:
        JSON with polished CV data and a token for payment/download.
    """
    file_path = None
    try:
        job_description = request.form.get('job_description', '').strip()
        if not job_description:
            return jsonify({"error": "Please provide a target job description."}), 400

        if len(job_description.split()) < 10:
            return jsonify({"error": "The job description seems too short. Please paste the full job posting."}), 400

        resume_file = request.files.get('resume_file')
        if not resume_file or not resume_file.filename:
            return jsonify({"error": "Please upload a resume file (PDF or DOCX)."}), 400

        if not allowed_file(resume_file.filename):
            return jsonify({"error": "Please upload a PDF or DOCX file."}), 400

        # Save file temporarily
        filename = secure_filename(resume_file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

        # Ensure uploads directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        resume_file.save(file_path)
        file_type = filename.rsplit('.', 1)[1].lower()

        # Parse the resume file — try/finally guarantees cleanup
        try:
            parse_result = parse_resume(file_path=file_path, file_type=file_type)
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                file_path = None  # Prevent double-delete in outer except

        if parse_result.get("error"):
            return jsonify({"error": parse_result["error"]}), 400

        resume_text = parse_result.get("text", "")
        if not resume_text or len(resume_text.strip()) < 50:
            return jsonify({"error": "Could not extract enough text from your resume. Please try a different file or use the manual form."}), 400

        # One AI call: extract structure + polish for ATS (same as scan flow)
        polished = extract_and_polish(resume_text, job_description)

        if polished.get("error"):
            return jsonify({"error": polished["error"]}), 500

        # Generate token and store (same pattern as generate-from-scan)
        token = uuid.uuid4().hex
        cv_redis_key = f"resumeradar:cv:{token}"

        if _redis_client:
            try:
                _redis_client.setex(cv_redis_key, 7200, json.dumps(polished))
                return jsonify({
                    "success": True,
                    "token": token,
                    "polished": polished,
                    "storage": "server",
                })
            except Exception as redis_err:
                print(f"Redis store error (upload): {redis_err}")

        # Fallback: client-side storage
        return jsonify({
            "success": True,
            "token": token,
            "polished": polished,
            "storage": "client",
        })

    except Exception as e:
        # Clean up file on unexpected error
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        print(f"CV Builder upload-generate error: {str(e)}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route('/api/build/create-checkout', methods=['POST'])
@limiter.limit("30 per hour")
def build_create_checkout():
    """
    Create a payment session (Stripe or Paystack) for CV download.

    Accepts:
        JSON with token, template, delivery_email, and provider ('stripe'|'paystack').

    Returns:
        JSON with checkout_url to redirect to.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided."}), 400

        token = data.get("token", "").strip()
        template = data.get("template", "classic").strip()
        provider = data.get("provider", "stripe").strip().lower()
        format_choice = data.get("format", "both").strip().lower()
        if format_choice not in ("pdf", "docx", "both"):
            format_choice = "both"

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

        base_url = _get_base_url()
        funnel_metrics.record("checkout_started")

        # ---- PAYSTACK PATH (Nigeria — explicit opt-in) ----
        if provider == "paystack" and os.getenv("PAYSTACK_SECRET_KEY"):
            # Paystack requires real email — no placeholder
            if not delivery_email:
                return jsonify({"error": "Email address is required for Naira payments."}), 400

            callback_url = f"{base_url}/build?payment=success&token={token}&provider=paystack"
            result = create_paystack_transaction(token, template, callback_url, delivery_email, format_choice)

            if result.get("error"):
                return jsonify({"error": result["error"]}), 500

            # Store auxiliary data in Redis — 72h TTL matching cv data
            if _redis_client:
                try:
                    _redis_client.setex(f"resumeradar:cv_template:{token}", 259200, template)
                    _redis_client.setex(f"resumeradar:cv_email:{token}", 259200, delivery_email)
                    _redis_client.setex(f"resumeradar:cv_format:{token}", 259200, format_choice)
                except Exception:
                    pass

            return jsonify({
                "success": True,
                "checkout_url": result["authorization_url"],
                "reference": result["reference"],
                "provider": "paystack",
            })

        # ---- STRIPE PATH (default — existing flow) ----
        # Generate one-time cancel nonce for Nigeria free-download flow
        cancel_nonce = secrets.token_urlsafe(16)

        success_url = f"{base_url}/build?payment=success&token={token}&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/build?payment=cancelled&cancel_nonce={cancel_nonce}"

        result = create_checkout_session(token, template, success_url, cancel_url, delivery_email, format_choice)

        if result.get("error"):
            return jsonify({"error": result["error"]}), 500

        # Store nonce → (token, session_id) AFTER session creation
        if _redis_client:
            try:
                nonce_key = f"resumeradar:cancel_nonce:{cancel_nonce}"
                nonce_data = json.dumps({"token": token, "session_id": result["session_id"]})
                _redis_client.setex(nonce_key, 7200, nonce_data)  # 2h TTL
            except Exception:
                pass

        return jsonify({
            "success": True,
            "checkout_url": result["checkout_url"],
            "session_id": result["session_id"],
            "provider": "stripe",
        })

    except Exception as e:
        print(f"CV Builder checkout error: {str(e)}")
        return jsonify({"error": "Could not create payment session."}), 500


# ============================================================
# BUNDLE ENDPOINTS (Phase 2)
# ============================================================

@app.route('/api/build/create-bundle-checkout', methods=['POST'])
@limiter.limit("10 per hour")
def create_bundle_checkout():
    """
    Create a payment session for a bundle purchase (Stripe-first, Paystack flagged).

    Body: { plan, email, provider ("stripe"|"paystack"), idempotency_key }
    Bundle token generated server-side, stored in metadata, NOT returned to client.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        plan = (data.get('plan') or '').strip().lower()
        email = (data.get('email') or '').strip()
        provider = (data.get('provider') or 'stripe').strip().lower()
        idempotency_key = (data.get('idempotency_key') or '').strip()

        # Validate plan
        if plan not in bundle_credits.PLANS:
            return jsonify({"error": "Invalid bundle plan."}), 400

        # Validate email (required for bundles)
        if not email or '@' not in email:
            return jsonify({"error": "Email is required for bundle purchases."}), 400

        # Cap body size
        if len(email) > 320:
            return jsonify({"error": "Invalid email."}), 400

        # Validate idempotency_key as UUIDv4 if provided
        if idempotency_key and not bundle_credits.is_valid_uuid4(idempotency_key):
            return jsonify({"error": "Invalid idempotency key format."}), 400

        # Idempotency check (H3)
        if idempotency_key and _redis_client:
            fingerprint = bundle_credits.compute_fingerprint(
                "create-bundle-checkout",
                plan=plan,
                email=email,
                provider=provider,
            )
            idem_key = f"resumeradar:bundle_checkout:{idempotency_key}"
            existing_raw = _redis_client.get(idem_key)
            if existing_raw:
                try:
                    stored = json.loads(existing_raw)
                    if stored.get("fingerprint") == fingerprint:
                        # Return stored response (safe retry)
                        resp = jsonify(stored.get("response", {}))
                        resp.headers['Cache-Control'] = 'no-store'
                        return resp
                    else:
                        # Same key, different fingerprint (H3 → 409)
                        return jsonify({"error": "Idempotency key reused with different request."}), 409
                except (json.JSONDecodeError, TypeError):
                    pass

        funnel_metrics.record("bundle_checkout_started")

        # Generate bundle token server-side
        bundle_token = secrets.token_urlsafe(32)
        base_url = _get_base_url()
        success_url = f"{base_url}/build?bundle_payment=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/build?payment=cancelled"

        if provider == "paystack":
            # Paystack bundle path (H4: behind feature flag)
            callback_url = f"{base_url}/build?bundle_payment=success&provider=paystack"
            result = create_paystack_bundle_transaction(plan, bundle_token, callback_url, email)
            if result.get("error"):
                return jsonify({"error": result["error"]}), 500
            response_data = {
                "success": True,
                "checkout_url": result["authorization_url"],
                "reference": result.get("reference", ""),
                "provider": "paystack",
            }
        else:
            # Stripe (default)
            result = create_bundle_checkout_session(plan, bundle_token, email, success_url, cancel_url)
            if result.get("error"):
                return jsonify({"error": result["error"]}), 500
            response_data = {
                "success": True,
                "checkout_url": result["checkout_url"],
                "session_id": result["session_id"],
                "provider": "stripe",
            }

        # Store idempotency response (H3)
        if idempotency_key and _redis_client:
            try:
                idem_data = json.dumps({
                    "fingerprint": fingerprint,
                    "response": response_data,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
                _redis_client.setex(idem_key, 3600, idem_data)
            except Exception:
                pass

        resp = jsonify(response_data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as e:
        print(f"Bundle checkout error: {str(e)}")
        return jsonify({"error": "Could not create payment session."}), 500


@app.route('/api/build/bundle-activate-from-payment', methods=['POST'])
@limiter.limit("30 per hour")
def bundle_activate_from_payment():
    """
    Post-payment browser auto-activation. Verifies payment via provider API,
    looks up bundle_token from session metadata, creates bundle in Redis,
    returns bundle data to client for localStorage storage.

    Idempotent within 24hr window (safe for flaky redirects/retries).

    Body: { session_id } (Stripe) or { reference } (Paystack)
    Returns: { bundle_token, plan, cv_remaining, cl_remaining, expires_in_hours }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        session_id = (data.get('session_id') or '').strip()
        reference = (data.get('reference') or '').strip()

        if not session_id and not reference:
            return jsonify({"error": "Missing session_id or reference."}), 400

        # Determine activation key for idempotency
        activation_key_suffix = session_id or reference
        activation_key = f"resumeradar:bundle_activated:{activation_key_suffix}"

        # Check for existing activation (idempotent 24hr window)
        if _redis_client:
            existing_raw = _redis_client.get(activation_key)
            if existing_raw:
                try:
                    stored = json.loads(existing_raw)
                    resp = jsonify(stored)
                    resp.headers['Cache-Control'] = 'no-store'
                    return resp
                except (json.JSONDecodeError, TypeError):
                    pass

        if session_id:
            # Stripe verification
            verify_result = verify_bundle_payment(session_id)
            if not verify_result.get("verified"):
                reason = verify_result.get("reason", "Verification failed.")
                return jsonify({"error": reason}), 400

            bundle_token = verify_result["bundle_token"]
            plan = verify_result["plan"]
            email = verify_result.get("delivery_email", "")
        elif reference:
            # Paystack: not supported in this endpoint yet (flagged)
            return jsonify({"error": "Paystack activation not yet supported."}), 400
        else:
            return jsonify({"error": "Missing payment reference."}), 400

        if not bundle_token or not plan:
            return jsonify({"error": "Invalid payment metadata."}), 400

        # Create bundle in Redis
        bundle_result = bundle_credits.create_bundle(plan, "stripe" if session_id else "paystack", email, bundle_token)
        if bundle_result.get("error"):
            return jsonify({"error": bundle_result["error"]}), 500

        # AUDIT: bundle created
        try:
            audit_log.log_event(
                "bundle_created",
                token=bundle_token,
                email=email,
                plan=plan,
                provider="stripe" if session_id else "paystack",
                bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                source="activate-from-payment",
            )
        except Exception:
            pass

        response_data = {
            "bundle_token": bundle_result["bundle_token"],
            "plan": bundle_result["plan"],
            "cv_remaining": bundle_result["cv_remaining"],
            "cl_remaining": bundle_result["cl_remaining"],
            "expires_in_hours": bundle_result["expires_in_hours"],
        }

        # Store activation for idempotency (24hr window)
        if _redis_client:
            try:
                _redis_client.setex(activation_key, 86400, json.dumps(response_data))
            except Exception:
                pass

        resp = jsonify(response_data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as e:
        print(f"Bundle activate error: {str(e)}")
        return jsonify({"error": "Something went wrong."}), 500


@app.route('/api/build/bundle-use', methods=['POST'])
@limiter.limit("30 per hour")
def bundle_use():
    """
    Consume a bundle credit atomically. Sets cv_paid flag on success.

    Body: { bundle_token, cv_token, type ("cv"|"cover_letter"), operation_id }
    operation_id is client-generated UUID for idempotency (H3).
    Bundle token in body, NOT URL path (avoids log/referrer leakage).

    Returns: { success, remaining } or { error } with appropriate status.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        bundle_token = (data.get('bundle_token') or '').strip()
        cv_token = (data.get('cv_token') or '').strip()
        credit_type = (data.get('type') or '').strip()
        operation_id = (data.get('operation_id') or '').strip()

        # Validate required fields
        if not bundle_token:
            return jsonify({"error": "Missing bundle token."}), 400
        if credit_type not in ("cv", "cover_letter"):
            return jsonify({"error": "Invalid credit type."}), 400
        if credit_type == "cv" and not cv_token:
            return jsonify({"error": "Missing CV token."}), 400

        # Validate operation_id as UUIDv4 (polish item)
        if operation_id and not bundle_credits.is_valid_uuid4(operation_id):
            return jsonify({"error": "Invalid operation ID format."}), 400

        # Idempotency check (H3)
        if operation_id:
            fingerprint = bundle_credits.compute_fingerprint(
                "bundle-use",
                bundle_token=bundle_token,
                cv_token=cv_token,
                type=credit_type,
            )
            existing = bundle_credits.check_operation_idempotency(operation_id, fingerprint)
            if existing is not None:
                if existing.get("error") == "conflict":
                    return jsonify({"error": "Idempotency key reused with different request."}), 409
                # Return stored response (safe retry)
                resp = jsonify(existing)
                resp.headers['Cache-Control'] = 'no-store'
                return resp

        # Atomic credit consumption
        result = bundle_credits.use_credit(bundle_token, credit_type, cv_token=cv_token)

        if result.get("error"):
            error = result["error"]
            if error == "expired":
                status = 410  # Gone
            elif error == "exhausted":
                status = 402  # Payment Required
            else:
                status = 500
            return jsonify({"error": error}), status

        response_data = {"success": True, "remaining": result.get("remaining")}

        # Store for idempotency (H3)
        if operation_id:
            bundle_credits.store_operation_result(operation_id, fingerprint, response_data)

        # AUDIT: bundle credit used
        try:
            audit_log.log_event(
                "bundle_credit_used",
                token=cv_token or bundle_token,
                type=credit_type,
                remaining=result.get("remaining"),
                bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                source="bundle-use",
            )
        except Exception:
            pass

        # Check if bundle is now exhausted (both CV and CL at 0)
        try:
            status_data = bundle_credits.get_status(bundle_token)
            if status_data.get("active"):
                cv_rem = status_data.get("cv_remaining", -1)
                cl_rem = status_data.get("cl_remaining", -1)
                if cv_rem == 0 and cl_rem == 0:
                    audit_log.log_event(
                        "bundle_exhausted",
                        token=bundle_token,
                        plan=status_data.get("plan", ""),
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="bundle-use",
                    )
        except Exception:
            pass

        resp = jsonify(response_data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as e:
        print(f"Bundle use error: {str(e)}")
        return jsonify({"error": "Something went wrong."}), 500


@app.route('/api/build/bundle-status', methods=['POST'])
@limiter.limit("60 per hour")
def bundle_status():
    """
    Check bundle status. Bundle token in body (not URL path).

    Body: { bundle_token }
    Returns: { active, plan, cv_remaining, cl_remaining, expires_in_hours }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        bundle_token = (data.get('bundle_token') or '').strip()
        if not bundle_token:
            return jsonify({"error": "Missing bundle token."}), 400

        status_data = bundle_credits.get_status(bundle_token)

        resp = jsonify(status_data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as e:
        print(f"Bundle status error: {str(e)}")
        return jsonify({"error": "Something went wrong."}), 500


@app.route('/api/build/bundle-exchange', methods=['POST'])
@limiter.limit("30 per hour")
def bundle_exchange():
    """
    Redeem a single-use exchange token for a bundle_token (H8).
    Exchange tokens are created during recovery email flow.

    Body: { exchange_token }
    Returns: { bundle_token, plan, cv_remaining, cl_remaining, expires_in_hours }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        exchange_token = (data.get('exchange_token') or '').strip()
        if not exchange_token:
            return jsonify({"error": "Missing exchange token."}), 400

        # Validate as UUID (exchange tokens are UUIDs)
        if not bundle_credits.is_valid_uuid4(exchange_token):
            return jsonify({"error": "Invalid exchange token format."}), 400

        # Atomic single-use redemption (GETDEL)
        bundle_token = bundle_credits.redeem_exchange_token(exchange_token)
        if not bundle_token:
            return jsonify({"error": "Exchange token expired or already used."}), 410

        # Get bundle status to return full data
        status_data = bundle_credits.get_status(bundle_token)
        if not status_data.get("active"):
            return jsonify({"error": "Bundle expired."}), 410

        response_data = {
            "bundle_token": bundle_token,
            "plan": status_data.get("plan", ""),
            "cv_remaining": status_data.get("cv_remaining", 0),
            "cl_remaining": status_data.get("cl_remaining", 0),
            "expires_in_hours": status_data.get("expires_in_hours", 0),
        }

        resp = jsonify(response_data)
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    except Exception as e:
        print(f"Bundle exchange error: {str(e)}")
        return jsonify({"error": "Something went wrong."}), 500


@app.route('/api/build/bundle-recover', methods=['POST'])
@limiter.limit("5 per hour")
def bundle_recover():
    """
    Recovery path for lost bundle tokens. Non-enumerable by contract (H5).
    Always returns { sent: true } whether email exists or not (no timing oracle).

    Body: { email }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request."}), 400

        email = (data.get('email') or '').strip()
        if not email or '@' not in email:
            return jsonify({"error": "Please provide a valid email."}), 400

        # Always return same response shape (non-enumerable)
        # Do the lookup + email send, but response is always { sent: true }
        try:
            bundle_token = bundle_credits.get_bundle_token_by_email(email)
            if bundle_token:
                # Verify the bundle is still active
                status_data = bundle_credits.get_status(bundle_token)
                if status_data.get("active"):
                    _send_bundle_email(email, bundle_token, status_data.get("plan", ""))
        except Exception:
            pass  # Non-enumerable: errors don't change response

        return jsonify({"sent": True})

    except Exception as e:
        print(f"Bundle recover error: {str(e)}")
        return jsonify({"sent": True})  # Always same response


@app.route('/api/build/download/<token>', methods=['GET', 'POST'])
@limiter.limit("30 per hour")
def build_download(token):
    """
    Verify payment, generate CV in chosen format, return download.

    GET (server storage / Redis):
        Query params: session_id, template, format
    POST (client storage fallback):
        JSON body: { session_id, template, cv_data, format }

    Format resolution: request param > payment metadata > "pdf" (backward compatible)
    """
    import zipfile
    import io

    VALID_FORMATS = ("pdf", "docx", "both")

    try:
        # Parse params from GET query string or POST body
        if request.method == 'POST':
            body = request.get_json() or {}
            session_id = body.get("session_id", "").strip()
            template = body.get("template", "classic").strip()
            client_cv_data = body.get("cv_data")
            provider = body.get("provider", "").strip()
            paystack_ref = body.get("reference", "").strip()
            dl_format = body.get("format", "").strip().lower()
        else:
            session_id = request.args.get("session_id", "").strip()
            template = request.args.get("template", "classic").strip()
            client_cv_data = None
            provider = request.args.get("provider", "").strip()
            paystack_ref = request.args.get("reference", "").strip()
            dl_format = request.args.get("format", "").strip().lower()

        # Verify payment based on provider, or check bundle cv_paid flag
        if provider == "paystack" and paystack_ref:
            payment = verify_paystack_payment(paystack_ref, token)
        elif session_id:
            payment = verify_checkout_payment(session_id, token)
        else:
            # No session_id or reference — check cv_paid flag (set by bundle-use)
            bundle_paid = False
            if _redis_client:
                try:
                    bundle_paid = bool(_redis_client.get(f"resumeradar:cv_paid:{token}"))
                except Exception:
                    pass
            if bundle_paid:
                payment = {"verified": True, "template": template, "delivery_email": "", "format": dl_format}
            else:
                return jsonify({"error": "Missing payment session."}), 400

        if not payment.get("verified"):
            return jsonify({"error": payment.get("reason", "Payment verification failed.")}), 403

        # Use template from payment metadata if available
        template = payment.get("template", template)

        # Format resolution: request param > payment metadata > "pdf"
        if dl_format not in VALID_FORMATS:
            dl_format = payment.get("format", "").strip().lower()
        if dl_format not in VALID_FORMATS:
            dl_format = "pdf"

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

        raw_name = cv_data.get("personal", {}).get("full_name", "Resume")
        safe_name = re_module.sub(r'[^\w.-]', '_', raw_name)

        # Check if email delivery was requested (from payment metadata)
        delivery_email = payment.get("delivery_email", "")

        # AUDIT: payment verified via download endpoint
        try:
            audit_log.log_event(
                "payment_verified",
                token=token,
                email=delivery_email if delivery_email else None,
                provider="paystack" if (provider == "paystack" and paystack_ref) else "stripe",
                session_id=session_id if session_id else None,
                reference=paystack_ref if paystack_ref else None,
                format=dl_format,
                source="download_verify",
            )
        except Exception:
            pass

        # Generate files based on format
        if dl_format == "docx":
            docx_bytes = bytes(generate_cv_docx(cv_data, template))
            filename = f"{safe_name}_CV.docx"
            response = Response(
                docx_bytes,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Length': str(len(docx_bytes))
                }
            )
        elif dl_format == "both":
            pdf_bytes = bytes(generate_cv_pdf(cv_data, template))
            docx_bytes = bytes(generate_cv_docx(cv_data, template))
            # Create in-memory zip with both files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{safe_name}_CV.pdf", pdf_bytes)
                zf.writestr(f"{safe_name}_CV.docx", docx_bytes)
            zip_bytes = zip_buffer.getvalue()
            filename = f"{safe_name}_CV.zip"
            response = Response(
                zip_bytes,
                mimetype='application/zip',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Length': str(len(zip_bytes))
                }
            )
        else:
            # Default: PDF only
            pdf_bytes = bytes(generate_cv_pdf(cv_data, template))
            filename = f"{safe_name}_CV.pdf"
            response = Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename={filename}',
                    'Content-Type': 'application/pdf',
                    'Content-Length': str(len(pdf_bytes))
                }
            )

        # AUDIT: successful download
        try:
            audit_log.log_event(
                "download_200",
                token=token,
                format=dl_format,
                content_length=response.headers.get('Content-Length', '0'),
                status_code=200,
                filename=filename,
            )
        except Exception:
            pass
        funnel_metrics.record("download_completed")

        response.headers['X-Email-Requested'] = 'true' if delivery_email else 'false'
        return response

    except Exception as e:
        print(f"CV Builder download error: {str(e)}")
        # AUDIT: download error (error class name only — no raw exception text)
        try:
            audit_log.log_event(
                "download_error",
                token=token,
                error=type(e).__name__,
                status_code=500,
            )
        except Exception:
            pass
        return jsonify({"error": "Failed to generate CV."}), 500


# ============================================================
# NIGERIA FREE DOWNLOAD (cancel-redirect flow)
# ============================================================

@app.route('/api/build/free-download-nigeria', methods=['POST'])
@limiter.limit("5 per hour")
def free_download_nigeria():
    """
    Grant free CV download for users who cancelled Stripe checkout.
    3-layer verification: cancel_nonce + nonce binding + Stripe API.
    """
    VALID_TEMPLATES = {"classic", "modern", "minimal"}
    VALID_FORMATS = {"pdf", "docx", "both"}

    try:
        body = request.get_json() or {}
        token = body.get("token", "").strip()
        session_id = body.get("session_id", "").strip()
        cancel_nonce = body.get("cancel_nonce", "").strip()
        template = body.get("template", "classic").strip()
        fmt = body.get("format", "both").strip().lower()

        # Input validation
        if not token or not session_id or not cancel_nonce:
            return jsonify({"error": "Missing required fields."}), 400
        if template not in VALID_TEMPLATES:
            template = "classic"
        if fmt not in VALID_FORMATS:
            fmt = "both"

        if not _redis_client:
            return jsonify({"error": "Service unavailable."}), 503

        # Layer 1: Read nonce (non-destructive — preserves retry on transient Stripe failure)
        nonce_key = f"resumeradar:cancel_nonce:{cancel_nonce}"
        nonce_raw = _redis_client.get(nonce_key)
        if not nonce_raw:
            return jsonify({"error": "Invalid or expired cancel session."}), 400

        try:
            nonce_data = json.loads(nonce_raw)
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "Invalid cancel session."}), 400

        if nonce_data.get("token") != token or nonce_data.get("session_id") != session_id:
            return jsonify({"error": "Session mismatch."}), 400

        # Check CV exists
        cv_key = f"resumeradar:cv:{token}"
        if not _redis_client.exists(cv_key):
            return jsonify({"error": "CV not found or expired."}), 404

        # Check not already granted (idempotent) — consume nonce via CAS even on early return
        paid_key = f"resumeradar:cv_paid:{token}"
        if _redis_client.get(paid_key):
            cas_result = _redis_client.eval(
                "if redis.call('GET',KEYS[1])==ARGV[1] then redis.call('DEL',KEYS[1]) return 1 end return 0",
                1, nonce_key, nonce_raw
            )
            if not cas_result:
                return jsonify({"error": "Cancel session already used."}), 400
            return jsonify({"already_granted": True}), 200

        # Layer 3: Verify Stripe session — unpaid + token matches metadata
        # Done BEFORE consuming nonce so transient Stripe failures allow retry
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception:
            return jsonify({"error": "Could not verify checkout session."}), 400

        if session.payment_status == "paid":
            return jsonify({"error": "Session already paid. Use normal download."}), 400

        if session.metadata.get("cv_token") != token:
            return jsonify({"error": "Token mismatch."}), 400

        # Consume nonce atomically AFTER all checks pass (Lua CAS — race-safe)
        consumed = _redis_client.eval(
            "if redis.call('GET',KEYS[1])==ARGV[1] then redis.call('DEL',KEYS[1]) return 1 end return 0",
            1, nonce_key, nonce_raw
        )
        if not consumed:
            return jsonify({"error": "Cancel session already used."}), 400

        # All checks passed — grant free access
        _redis_client.setex(paid_key, 86400, "1")       # 24h TTL
        _redis_client.expire(cv_key, 259200)             # Extend CV data to 72h
        _redis_client.setex(f"resumeradar:cv_template:{token}", 259200, template)
        _redis_client.setex(f"resumeradar:cv_format:{token}", 259200, fmt)

        # Audit (best-effort, uses only ALLOWED_KWARGS)
        try:
            audit_log.log_event("free_download_nigeria", token=token, format=fmt, source="cancel_redirect")
        except Exception:
            pass

        funnel_metrics.record("free_download_nigeria")

        return jsonify({"granted": True}), 200

    except Exception as e:
        print(f"Free download Nigeria error: {str(e)}")
        return jsonify({"error": "Could not process request."}), 500


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

        # Generate DOCX and decide whether to include it (10MB size guard)
        docx_bytes = generate_cv_docx(cv_data, template)
        total_size = len(pdf_bytes) + len(docx_bytes)
        include_docx = total_size <= 10_000_000

        # Sanitize user-derived values
        raw_name = cv_data.get('personal', {}).get('full_name', 'there')
        first_name = html_module.escape(
            raw_name.split()[0] if raw_name and raw_name != 'there' else 'there'
        )
        safe_name = re_module.sub(r'[^\w.-]', '_', raw_name) if raw_name != 'there' else 'ResumeRadar'

        # Build attachments list — always PDF, DOCX if under 10MB combined
        attachments = [{"filename": f"{safe_name}_CV.pdf", "content": pdf_base64}]
        if include_docx:
            docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')
            attachments.append({"filename": f"{safe_name}_CV.docx", "content": docx_base64})

        format_note = "PDF and Word format" if include_docx else "PDF format"
        edit_tip = '<li>Open the Word version to make quick edits</li>' if include_docx else ''

        html_body = f"""<div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #1f2937;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%); padding: 32px 24px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">ResumeRadar</h1>
                <p style="color: rgba(255,255,255,0.8); margin: 4px 0 0; font-size: 14px;">Your ATS-optimized CV is ready.</p>
            </div>
            <div style="background: white; padding: 32px 24px; border: 1px solid #e5e7eb; border-top: none;">
                <h2 style="margin: 0 0 12px; font-size: 20px;">Hi {first_name},</h2>
                <p style="font-size: 15px; line-height: 1.6; color: #4b5563;">Your polished CV is attached in {format_note}. It has been tailored for ATS systems.</p>
                <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">Next steps:</p>
                    <ul style="margin: 8px 0 0; padding-left: 20px; color: #374151; font-size: 14px; line-height: 1.8;">
                        {edit_tip}
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

        send_result = resend.Emails.send({
            "from": "ResumeRadar <reports@sholastechnotes.com>",
            "to": [email],
            "subject": f"Your ResumeRadar CV is ready, {first_name}",
            "html": html_body,
            "attachments": attachments,
        })

        # AUDIT: email accepted by Resend (capture message ID for webhook correlation)
        resend_message_id = getattr(send_result, 'id', None) or (
            send_result.get('id') if isinstance(send_result, dict) else None)
        try:
            audit_log.log_event(
                "email_accepted",
                token=token,
                email=email,
                resend_message_id=resend_message_id,
            )
        except Exception:
            pass

    except Exception as e:
        print(f"CV email error (best-effort): {e}")
        # AUDIT: email send failure (error class name only)
        try:
            audit_log.log_event(
                "email_send_error",
                token=token,
                email=email,
                error=type(e).__name__,
            )
        except Exception:
            pass
        # Release dedup flag on failure so Stripe retries can succeed
        try:
            if _redis_client:
                _redis_client.delete(f"resumeradar:cv_emailed:{event_id}")
        except Exception:
            pass


def _send_bundle_email(email, bundle_token, plan):
    """
    Send bundle access email with single-use exchange token (H8).
    Exchange token link lets user activate bundle in browser without
    raw bundle_token ever appearing in email URLs.
    Best-effort: failures are logged but don't break the webhook.
    """
    try:
        if not email or not bundle_token:
            return

        resend_key = os.getenv("RESEND_API_KEY")
        if not resend_key:
            return

        # Create single-use exchange token (H8)
        exchange_id = bundle_credits.create_exchange_token(bundle_token)
        if not exchange_id:
            print("Bundle email: failed to create exchange token")
            return

        base_url = _get_base_url()
        activate_link = f"{base_url}/build?activate={exchange_id}"

        plan_names = {
            "jobhunt": "Job Hunt Pack",
            "sprint": "Unlimited Sprint",
        }
        plan_display = plan_names.get(plan, plan.title())

        plan_details = {
            "jobhunt": "5 CV downloads + 5 cover letters (valid for 48 hours)",
            "sprint": "Unlimited CV downloads + cover letters (valid for 7 days)",
        }
        details = plan_details.get(plan, "")

        import resend
        resend.api_key = resend_key

        result = resend.Emails.send({
            "from": "ResumeRadar <noreply@resumeradar.sholastechnotes.com>",
            "to": [email],
            "subject": f"Your ResumeRadar {plan_display} is ready!",
            "html": f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #1a1a2e;">Your {plan_display} is Active!</h2>
                <p>Thank you for your purchase. Your bundle includes:</p>
                <p style="background: #f0f4ff; padding: 12px 16px; border-radius: 8px; font-weight: 500;">{details}</p>
                <p>Click the button below to activate your bundle:</p>
                <p style="text-align: center; margin: 24px 0;">
                    <a href="{activate_link}" style="display: inline-block; background: #4361ee; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600;">Activate Bundle</a>
                </p>
                <p style="color: #666; font-size: 14px;">This activation link expires in 15 minutes. If it expires, use the "Lost your bundle?" recovery form on the builder page with this email address.</p>
                <p style="color: #666; font-size: 14px;">Your new bundle is now active. If you had a previous bundle, it remains valid but recovery emails will link to your latest purchase.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
                <p style="color: #999; font-size: 12px;">ResumeRadar — Privacy-first resume optimization</p>
            </div>
            """,
        })

        # AUDIT: email accepted
        try:
            audit_log.log_event(
                "email_accepted",
                token=bundle_token,
                email=email,
                resend_message_id=str(result.get("id", "")) if isinstance(result, dict) else "",
                source="bundle-email",
            )
        except Exception:
            pass

    except Exception as e:
        print(f"Bundle email error: {type(e).__name__}: {str(e)}")
        try:
            audit_log.log_event(
                "email_send_error",
                token=bundle_token,
                email=email,
                error=type(e).__name__,
                source="bundle-email",
            )
        except Exception:
            pass


@app.route('/api/build/webhook', methods=['POST'])
@limiter.exempt
def build_webhook():
    """
    Stripe webhook handler. Handles both single CV payments and bundle payments.
    Order: (1) verify signature → (2) dedup on event.id (H3) → (3) side effects.
    """
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature', '')

        # (1) Verify signature FIRST — never dedup before sig check
        event = verify_webhook_signature(payload, sig_header)
        if not event:
            return jsonify({"error": "Invalid signature."}), 400

        if event['type'] == 'checkout.session.completed':
            event_id = event['id']
            session = event['data']['object']
            metadata = session.get('metadata', {})

            # (2) Dedup on event.id (H3) — after signature verification
            if event_id and _redis_client:
                dedup_key = f"resumeradar:stripe_processed:{event_id}"
                was_set = _redis_client.set(dedup_key, "1", nx=True, ex=259200)  # 72h
                if not was_set:
                    return jsonify({"received": True}), 200  # Already processed

            product_type = metadata.get('product_type', '')

            if product_type == 'bundle':
                # (3) Bundle payment side effects
                bundle_token = metadata.get('bundle_token', '')
                plan = metadata.get('plan', '')
                delivery_email = metadata.get('delivery_email', '')

                if bundle_token and plan and _redis_client:
                    try:
                        # Create bundle in Redis (H9: email_hash, not plaintext)
                        bundle_result = bundle_credits.create_bundle(plan, "stripe", delivery_email, bundle_token)

                        if bundle_result.get("error"):
                            print(f"Webhook bundle creation failed: {bundle_result['error']}")
                            # Release dedup so retries can succeed
                            try:
                                _redis_client.delete(dedup_key)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"Webhook bundle error: {e}")
                        try:
                            _redis_client.delete(dedup_key)
                        except Exception:
                            pass

                # AUDIT: bundle payment verified
                try:
                    audit_log.log_event(
                        "payment_verified",
                        token=bundle_token,
                        email=delivery_email,
                        provider="stripe",
                        plan=plan,
                        session_id=session.get('id', ''),
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="webhook",
                    )
                except Exception:
                    pass
                funnel_metrics.record("purchase_completed")

                # AUDIT: bundle created
                try:
                    audit_log.log_event(
                        "bundle_created",
                        token=bundle_token,
                        email=delivery_email,
                        plan=plan,
                        provider="stripe",
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="webhook",
                    )
                except Exception:
                    pass

                # Send bundle access email with exchange token (H8)
                if delivery_email and bundle_token:
                    _send_bundle_email(delivery_email, bundle_token, plan)

            else:
                # (3) Single CV payment side effects (existing flow)
                cv_token = metadata.get('cv_token', '')
                template = metadata.get('template', 'classic')
                delivery_email = metadata.get('delivery_email', '')

                if cv_token and _redis_client:
                    try:
                        paid_key = f"resumeradar:cv_paid:{cv_token}"
                        _redis_client.setex(paid_key, 7200, "1")
                        _redis_client.expire(f"resumeradar:cv:{cv_token}", 259200)
                    except Exception:
                        pass

                # AUDIT: payment confirmed
                try:
                    audit_log.log_event(
                        "payment_verified",
                        token=cv_token,
                        email=delivery_email,
                        provider="stripe",
                        session_id=session.get('id', ''),
                        payment_intent_id=session.get('payment_intent', ''),
                        source="webhook",
                    )
                except Exception:
                    pass
                funnel_metrics.record("purchase_completed")

                # Send email if requested
                if delivery_email and cv_token:
                    _send_cv_email(delivery_email, cv_token, template, event_id)

        return jsonify({"received": True}), 200

    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return jsonify({"error": "Webhook processing failed."}), 500


@app.route('/api/build/webhook/paystack', methods=['POST'])
@limiter.exempt
def build_webhook_paystack():
    """
    Paystack webhook handler. Handles both single CV payments and bundle payments.
    Order: (1) verify signature → (2) dedup on reference (H3) → (3) side effects.
    Bundle flow gated behind PAYSTACK_BUNDLES_ENABLED (H4).
    """
    try:
        payload = request.get_data()
        signature = request.headers.get('X-Paystack-Signature', '')

        # (1) Verify signature FIRST
        if not verify_paystack_webhook(payload, signature):
            return jsonify({"error": "Invalid signature."}), 400

        event = request.get_json()

        if event.get('event') == 'charge.success':
            data = event.get('data', {})
            reference = data.get('reference', '')
            metadata = data.get('metadata', {})
            product_type = metadata.get('product_type', '')
            delivery_email = metadata.get('delivery_email', '')

            # (2) Dedup on reference — after signature verification
            if reference and _redis_client:
                dedup_key = f"resumeradar:paystack_processed:{reference}"
                was_set = _redis_client.set(dedup_key, "1", nx=True, ex=259200)  # 72h
                if not was_set:
                    return jsonify({"received": True}), 200  # Already processed this reference

            if product_type == 'bundle' and os.getenv("PAYSTACK_BUNDLES_ENABLED", "false").lower() == "true":
                # (3) Bundle payment side effects (H4: behind feature flag)
                bundle_token = metadata.get('bundle_token', '')
                plan = metadata.get('plan', '')

                if bundle_token and plan and _redis_client:
                    try:
                        bundle_result = bundle_credits.create_bundle(plan, "paystack", delivery_email, bundle_token)
                        if bundle_result.get("error"):
                            print(f"Paystack webhook bundle creation failed: {bundle_result['error']}")
                            try:
                                _redis_client.delete(dedup_key)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"Paystack webhook bundle error: {e}")
                        try:
                            _redis_client.delete(dedup_key)
                        except Exception:
                            pass

                # AUDIT
                try:
                    audit_log.log_event(
                        "payment_verified",
                        token=bundle_token,
                        email=delivery_email,
                        provider="paystack",
                        plan=plan,
                        reference=reference,
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="webhook",
                    )
                except Exception:
                    pass
                funnel_metrics.record("purchase_completed")

                try:
                    audit_log.log_event(
                        "bundle_created",
                        token=bundle_token,
                        email=delivery_email,
                        plan=plan,
                        provider="paystack",
                        bundle_token_hash=bundle_credits.hmac_token(bundle_token),
                        source="webhook",
                    )
                except Exception:
                    pass

                if delivery_email and bundle_token:
                    _send_bundle_email(delivery_email, bundle_token, plan)
            else:
                # (3) Single CV payment side effects (existing flow)
                cv_token = metadata.get('cv_token', '')
                template = metadata.get('template', 'classic')

                if cv_token and _redis_client:
                    try:
                        paid_key = f"resumeradar:cv_paid:{cv_token}"
                        _redis_client.setex(paid_key, 259200, "1")
                        _redis_client.expire(f"resumeradar:cv:{cv_token}", 259200)
                        _redis_client.setex(f"resumeradar:cv_paystack_ref:{cv_token}", 259200, reference)
                    except Exception as redis_err:
                        print(f"Paystack webhook Redis error: {redis_err}")
                        try:
                            _redis_client.delete(dedup_key)
                        except Exception:
                            pass

                try:
                    audit_log.log_event(
                        "payment_verified",
                        token=cv_token,
                        email=delivery_email,
                        provider="paystack",
                        reference=reference,
                        source="webhook",
                    )
                except Exception:
                    pass
                funnel_metrics.record("purchase_completed")

                if delivery_email and cv_token:
                    _send_cv_email(delivery_email, cv_token, template, f"paystack_{reference}")

        return jsonify({"received": True}), 200

    except Exception as e:
        print(f"Paystack webhook error: {str(e)}")
        return jsonify({"error": "Webhook processing failed."}), 500


@app.route('/api/build/webhook/resend', methods=['POST'])
@limiter.exempt
def build_webhook_resend():
    """
    Resend webhook handler. Records email delivery events in the audit trail.
    Uses Svix signature verification (Resend's webhook infrastructure).
    """
    # Check secret BEFORE importing svix (fail-closed even if svix not installed)
    resend_secret = os.getenv('RESEND_WEBHOOK_SECRET', '')
    if not resend_secret:
        return jsonify({"error": "Webhook not configured."}), 503

    try:
        from svix.webhooks import Webhook, WebhookVerificationError

        # Use raw bytes exactly as received for signature verification
        payload_bytes = request.get_data()
        headers = {
            "svix-id": request.headers.get("svix-id", ""),
            "svix-timestamp": request.headers.get("svix-timestamp", ""),
            "svix-signature": request.headers.get("svix-signature", ""),
        }

        try:
            wh = Webhook(resend_secret)
            event_data = wh.verify(payload_bytes, headers)
        except WebhookVerificationError:
            return jsonify({"error": "Invalid signature."}), 400

        # Map Resend event types to audit event names
        event_map = {
            "email.delivered": "email_delivered",
            "email.bounced": "email_bounced",
            "email.delivery_delayed": "email_delivery_delayed",
            "email.complained": "email_complained",
        }

        resend_event_type = event_data.get("type", "")
        audit_event = event_map.get(resend_event_type)
        if not audit_event:
            # Unhandled event type — acknowledge to stop retries
            return jsonify({"received": True}), 200

        # Extract email_id from payload data for reverse index lookup
        email_data = event_data.get("data", {})
        email_id = email_data.get("email_id", "")

        if not email_id or not _redis_client:
            print(f"Resend webhook: no email_id or Redis unavailable for {resend_event_type}")
            return jsonify({"received": True}), 200

        # Look up token_hash via reverse index
        idx_key = f"resumeradar:audit_idx:resend:{email_id}"
        token_hash = _redis_client.get(idx_key)

        if not token_hash:
            # Index miss — email_id was not tracked (e.g., sent before audit was enabled)
            print(f"Resend webhook: no audit index for email_id={email_id} event={resend_event_type}")
            return jsonify({"received": True}), 200

        # Write event directly to sorted set (we only have token_hash, not raw token)
        now = datetime.now(timezone.utc)
        ts_ms = now.timestamp()
        event_record = {
            "id": str(uuid.uuid4()),
            "event": audit_event,
            "ts": now.isoformat(),
            "ts_ms": ts_ms,
            "resend_message_id": email_id,
        }

        audit_key = f"resumeradar:audit:{token_hash}"
        _redis_client.zadd(audit_key, {json.dumps(event_record, separators=(',', ':')): ts_ms})
        _redis_client.expire(audit_key, 10_368_000)  # 120 days

        return jsonify({"received": True}), 200

    except Exception as e:
        print(f"Resend webhook error: {type(e).__name__}")
        return jsonify({"received": True}), 200  # Always 200 to prevent infinite retries


@app.route('/api/event', methods=['POST'])
@limiter.limit("60 per minute")
def track_client_event():
    """Accept client-side funnel events. Always returns 204 (silent)."""
    try:
        data = request.get_json(silent=True) or {}
        event = data.get('event', '')
        if event in funnel_metrics.CLIENT_EVENTS:
            funnel_metrics.record(event)
    except Exception:
        pass
    return '', 204


@app.route('/api/admin/funnel', methods=['GET'])
@limiter.exempt
def admin_funnel():
    """Return funnel analytics. Bearer token auth (AUDIT_ADMIN_TOKEN)."""
    admin_token = os.getenv('AUDIT_ADMIN_TOKEN', '')
    if not admin_token:
        return jsonify({"error": "Not configured."}), 503

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized."}), 401
    provided_token = auth_header[7:]
    if not hmac_module.compare_digest(provided_token, admin_token):
        return jsonify({"error": "Unauthorized."}), 401

    # Single date or range
    date_param = request.args.get('date', '')
    days_param = request.args.get('days', '7')

    if date_param:
        metrics = funnel_metrics.get_day(date_param)
        return jsonify({"date": date_param, "metrics": metrics}), 200

    try:
        days = min(int(days_param), 30)
    except (ValueError, TypeError):
        days = 7
    return jsonify(funnel_metrics.get_range(days)), 200


@app.route('/api/admin/audit/lookup', methods=['GET'])
@limiter.exempt
def admin_audit_lookup():
    """
    Admin endpoint to look up audit trails by provider identifier.
    Requires Bearer token auth. Fail-closed: 503 if AUDIT_ADMIN_TOKEN not configured.

    Usage: GET /api/admin/audit/lookup?type=session&id=cs_live_xxx
    Types: session, paystack_ref, pi, resend, token
    """
    # Fail closed — if admin token not configured, deny all access
    admin_token = os.getenv('AUDIT_ADMIN_TOKEN', '')
    if not admin_token:
        return jsonify({"error": "Audit lookup not configured."}), 503

    # Bearer token auth with timing-safe comparison
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Unauthorized."}), 401

    provided_token = auth_header[7:]  # Strip "Bearer "
    if not hmac_module.compare_digest(provided_token, admin_token):
        return jsonify({"error": "Unauthorized."}), 401

    # Parse query parameters
    lookup_type = request.args.get('type', '')
    lookup_id = request.args.get('id', '')

    if not lookup_type or not lookup_id:
        return jsonify({"error": "Missing 'type' and 'id' query parameters."}), 400

    # Route to the appropriate lookup method
    if lookup_type == 'token':
        result = audit_log.lookup_by_raw_token(lookup_id)
    elif lookup_type in ('session', 'paystack_ref', 'pi', 'resend'):
        result = audit_log.lookup_by_id(lookup_type, lookup_id)
    else:
        return jsonify({"error": f"Invalid type '{lookup_type}'. Use: session, paystack_ref, pi, resend, token"}), 400

    if not result:
        return jsonify({"error": "No audit trail found."}), 404

    return jsonify(result), 200


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
    # Cache static assets for 1 hour (not longer — filenames aren't fingerprinted)
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=3600, stale-while-revalidate=600'
    # Prevent browser caching of CV builder API responses (PII protection)
    elif request.path.startswith('/api/build/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    # Only add HSTS in production
    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Block search engine indexing on staging
    if os.environ.get('STAGING') == 'true':
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
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

# Startup banner — runs under both Gunicorn and python app.py
print(f"\n📡 ResumeRadar starting up...")
print(f"   AI Suggestions: {'✅ Enabled' if os.getenv('ANTHROPIC_API_KEY') else '❌ No API key found'}")
print(f"   Stripe Checkout: {'✅ Enabled' if os.getenv('STRIPE_PRICE_ID') else '❌ Not configured'}")
print(f"   Rate Limiter: {'Redis' if os.getenv('REDIS_URL') else 'In-memory'}")
print(f"   Email Delivery: {'✅ Enabled' if os.getenv('RESEND_API_KEY') else '❌ Not configured'}")
print(f"   Paystack: {'✅ Enabled' if os.getenv('PAYSTACK_SECRET_KEY') else '❌ Not configured'}")
print(f"   Audit Log: {'✅ Enabled' if (os.getenv('AUDIT_HMAC_SECRET') and _redis_client) else '❌ Disabled (needs AUDIT_HMAC_SECRET + Redis)'}")
print(f"   Funnel Analytics: {'✅ Enabled' if _redis_client else '❌ Disabled (needs Redis)'}")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('FLASK_ENV', 'development') == 'development'
    print(f"   Debug mode: {'On' if debug else 'Off'}")
    print(f"   URL: http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)

"""
ATS Job Scanner — Main Application
A tool that helps job seekers optimize their resumes for ATS systems.
Built by Olushola Oladipupo
"""

import os
import uuid
import secrets
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

from backend.resume_parser import parse_resume
from backend.keyword_engine import extract_keywords_from_text, calculate_match, analyze_ats_formatting
from backend.ai_analyzer import get_ai_suggestions

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

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================
# ROUTES
# ============================================================

@app.route('/')
def index():
    """Serve the main application page."""
    return render_template('index.html')


@app.route('/api/scan', methods=['POST'])
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

        # 8. Compile final response
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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    has_api_key = bool(os.getenv('ANTHROPIC_API_KEY')) and os.getenv('ANTHROPIC_API_KEY') != 'your-anthropic-api-key-here'
    return jsonify({
        "status": "healthy",
        "ai_enabled": has_api_key,
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum size is 5MB."}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found."}), 404


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

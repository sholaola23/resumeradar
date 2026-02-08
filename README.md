# ResumeRadar

**Beat the scan. Land the interview.**

ResumeRadar is a free ATS (Applicant Tracking System) resume scanner that helps job seekers understand why their resumes get filtered out — and how to fix them. Upload your resume, paste a job description, and get instant feedback on keyword matches, gaps, and actionable improvements.

**Live at:** [resumeradar.sholastechnotes.com](https://resumeradar.sholastechnotes.com)

---

## Features

- **ATS Match Score** — See your resume-to-job match percentage using a curved scoring formula
- **Keyword Analysis** — Identify matched and missing keywords across 5 categories (technical skills, soft skills, certifications, education, action verbs)
- **AI-Powered Suggestions** — Get personalised improvement tips powered by Claude (Anthropic)
- **ATS Formatting Check** — Detect formatting issues that trip up ATS systems (contact info, section headers, word count, action verbs)
- **PDF Report** — Download a branded, multi-page PDF report of your full analysis
- **Email Delivery** — Send your report directly to your inbox with a PDF attachment
- **Newsletter Integration** — Beehiiv-powered newsletter subscription gate
- **Privacy-First** — Resumes are analysed in real-time and never stored

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python, Flask |
| **AI** | Anthropic Claude API (claude-sonnet-4-20250514) |
| **NLP** | Rule-based keyword extraction + AI analysis |
| **PDF Generation** | fpdf2 |
| **Email** | Resend API |
| **Newsletter** | Beehiiv API v2 |
| **Frontend** | Vanilla HTML, CSS, JavaScript |
| **Hosting** | Render |
| **Security** | flask-limiter, security headers, HSTS |

## How It Works

1. **Upload** your resume (PDF, DOCX, or paste text)
2. **Paste** the full job description
3. **Get** your ATS match score, missing keywords, AI suggestions, and formatting checks

The scanner uses a hybrid approach:
- **Rule-based NLP** extracts and categorises keywords from both documents
- **Curved scoring** (`raw_ratio^0.7 * 100`) rewards partial matches fairly
- **Claude AI** provides contextual suggestions, strengths, improvements, and keyword placement tips

## Project Structure

```
.
├── app.py                     # Flask application & API routes
├── backend/
│   ├── resume_parser.py       # PDF/DOCX/text parsing
│   ├── keyword_engine.py      # Keyword extraction, matching & ATS checks
│   ├── ai_analyzer.py         # Claude AI integration
│   └── report_generator.py    # PDF report generation (fpdf2)
├── templates/
│   ├── index.html             # Main application page
│   └── 404.html               # Branded 404 error page
├── static/
│   ├── css/style.css          # Styles (responsive, mobile-first)
│   └── js/app.js              # Frontend logic & API calls
├── requirements.txt           # Python dependencies
├── Procfile                   # Gunicorn start command
├── render.yaml                # Render deployment config
├── runtime.txt                # Python version
├── .env.example               # Environment variable template
└── .gitignore                 # Git ignore rules
```

## Getting Started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/) for AI suggestions

### Installation

```bash
# Clone the repository
git clone https://github.com/sholaola23/resumeradar.git
cd resumeradar

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude AI suggestions |
| `RESEND_API_KEY` | No | Resend API key for email delivery |
| `BEEHIIV_API_KEY` | No | Beehiiv API key for newsletter subscriptions |
| `BEEHIIV_PUBLICATION_ID` | No | Beehiiv publication ID |
| `FLASK_SECRET_KEY` | No | Flask secret key (auto-generated if not set) |
| `FLASK_ENV` | No | Set to `production` for production deployment |

### Running Locally

```bash
python app.py
```

The app will be available at `http://localhost:5001`

## API Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|------------|
| `GET` | `/` | Main application page | Default |
| `POST` | `/api/scan` | Analyse resume against job description | 10/hour |
| `POST` | `/api/download-report` | Generate and download PDF report | 20/hour |
| `POST` | `/api/email-report` | Send report via email | 5/hour |
| `POST` | `/api/subscribe` | Subscribe to newsletter | 10/hour |
| `GET` | `/api/health` | Health check | Default |

## Deployment

The app is configured for deployment on [Render](https://render.com):

1. Connect your GitHub repository
2. Set the environment variables in Render's dashboard
3. Render will auto-detect the `Procfile` and deploy

The `render.yaml` and `Procfile` are included for zero-config deployment.

## Security

- **Rate Limiting** — Protects API endpoints from abuse (flask-limiter)
- **Security Headers** — X-Content-Type-Options, X-Frame-Options, XSS Protection, Referrer-Policy, Permissions-Policy, HSTS
- **No Data Storage** — Uploaded files are deleted immediately after parsing
- **Environment Variables** — All API keys stored securely, never committed to git

## Built By

**[Olushola Oladipupo](https://www.linkedin.com/in/olushola-oladipupo/)** — AWS Solutions Architect

Helping people break into tech and cloud, one resume at a time.

## Licence

This project is open source and available under the [MIT Licence](LICENCE).

/**
 * ResumeRadar — Frontend Application
 * Handles form interaction, API calls, results rendering,
 * and report generation (copy, download, email).
 */

// Sanitize AI text — strip JSON/markdown artifacts that may leak through
function sanitizeAIText(text) {
    if (!text) return '';
    if (text.includes('```') || text.includes('"summary"') || text.trim().startsWith('{')) {
        text = text.replace(/```json/g, '').replace(/```/g, '').replace(/[{}]/g, '')
            .replace(/"summary"\s*:/g, '').replace(/"strengths"\s*:/g, '')
            .replace(/"critical_improvements"\s*:/g, '').replace(/"quick_wins"\s*:/g, '')
            .replace(/"keyword_suggestions"\s*:/g, '').replace(/"rewrite_suggestions"\s*:/g, '')
            .trim().replace(/^"|"$/g, '').trim();
    }
    return text;
}

// Escape HTML before interpolating ANY AI- or user-derived string into
// innerHTML. AI output is steered by the pasted job description, so a
// poisoned JD can prompt-inject markup into suggestions (XSS otherwise).
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    // ============================================================
    // FUNNEL ANALYTICS (fire-and-forget via sendBeacon)
    // ============================================================
    let journeyId = '';
    try {
        journeyId = sessionStorage.getItem('resumeradar_journey_id') || crypto.randomUUID();
        sessionStorage.setItem('resumeradar_journey_id', journeyId);
    } catch (e) { /* analytics must never block scanning */ }
    function trackEvent(eventName) {
        try {
            var blob = new Blob([JSON.stringify({ event: eventName, journey_id: journeyId })], { type: 'application/json' });
            navigator.sendBeacon('/api/event', blob);
        } catch (e) { /* best-effort */ }
    }
    window._rr_trackEvent = trackEvent;
    try {
        if (!sessionStorage.getItem('resumeradar_visit_recorded')) {
            if (localStorage.getItem('resumeradar_visited')) trackEvent('repeat_visit');
            localStorage.setItem('resumeradar_visited', '1');
            sessionStorage.setItem('resumeradar_visit_recorded', '1');
        }
    } catch (e) { /* optional local repeat-use signal, no persistent server identity */ }
    let activeJobKey = '';


    // Per-scan event deduplication
    let currentScanId = null;
    const firedEvents = new Set();

    function trackOncePerScan(eventName) {
        if (!currentScanId) { trackEvent(eventName); return; }
        const key = currentScanId + ':' + eventName;
        if (firedEvents.has(key)) return;
        firedEvents.add(key);
        trackEvent(eventName);
    }

    // ============================================================
    // SUBSCRIBER STATE — localStorage (persists across sessions)
    // ============================================================
    // One-time migration from sessionStorage to localStorage
    if (sessionStorage.getItem('resumeradar_subscribed') === 'true') {
        localStorage.setItem('resumeradar_subscribed', 'true');
        sessionStorage.removeItem('resumeradar_subscribed');
    }

    function isSubscribed() {
        return localStorage.getItem('resumeradar_subscribed') === 'true';
    }

    function markSubscribed() {
        localStorage.setItem('resumeradar_subscribed', 'true');
        sessionStorage.removeItem('resumeradar_subscribed');
    }

    function gateSkipped() {
        try {
            return sessionStorage.getItem('resumeradar_gate_skipped') === '1';
        } catch (e) {
            return false;
        }
    }


    // ============================================================
    // DOM ELEMENTS
    // ============================================================
    const scanForm = document.getElementById('scanForm');
    const scanBtn = document.getElementById('scanBtn');
    const scanProgress = document.getElementById('scanProgress');
    const errorMessage = document.getElementById('errorMessage');
    const uploadError = document.getElementById('uploadError');
    const resultsSection = document.getElementById('results');
    const scanAgainBtn = document.getElementById('scanAgainBtn');

    // File upload elements
    const dropZone = document.getElementById('dropZone');
    const resumeFile = document.getElementById('resumeFile');
    const fileSelected = document.getElementById('fileSelected');
    const fileName = document.getElementById('fileName');
    const removeFileBtn = document.getElementById('removeFile');

    // Tab elements
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    // Report action buttons
    const copyReportBtn = document.getElementById('copyReportBtn');
    const downloadReportBtn = document.getElementById('downloadReportBtn');
    const emailReportBtn = document.getElementById('emailReportBtn');

    // Email modal
    const emailModal = document.getElementById('emailModal');
    const closeModalBtn = document.getElementById('closeModal');
    const cancelModalBtn = document.getElementById('cancelModal');
    const sendEmailBtn = document.getElementById('sendEmailBtn');
    const emailInput = document.getElementById('emailInput');
    const emailFormStep = document.getElementById('emailFormStep');
    const emailWaitStep = document.getElementById('emailWaitStep');
    const emailWaitText = document.getElementById('emailWaitText');

    // Store the last scan data for report generation
    let lastScanData = null;
    let comparisonBaseline = null;
    // Job description segments for "View in job description". Kept apart from
    // lastScanData so the job text is never posted back with a report request.
    let lastJobView = [];
    let jobTermIndex = ResumeRadarScan.jobTermIndex([]);
    // Keep the optional newsletter after the complete report and free rescan action.
    resultsSection.appendChild(document.getElementById('inlineGateCard'));
    document.getElementById('topMissingKeywords').before(document.getElementById('quickWins'));

    // Show a recognised term the way people write it (CDN, not cdn). The
    // server sends the display names with each scan; matching stays lower-case.
    function kw(term) {
        const names = (lastScanData && lastScanData.keyword_display) || {};
        return Object.prototype.hasOwnProperty.call(names, term) ? names[term] : term;
    }

    // ============================================================
    // SOCIAL PROOF COUNTER
    // ============================================================
    const socialProof = document.getElementById('socialProof');
    const scanCountEl = document.getElementById('scanCount');

    function scanCountText(count) {
        const num = count.toLocaleString();
        if (count >= 1000) return `${num}+ CVs scanned. Join the movement`;
        if (count >= 750) return `${num}+ job seekers have scanned their CVs`;
        if (count >= 500) return `${num}+ CVs scanned and counting`;
        if (count >= 250) return `${num}+ CVs scanned. Are you next?`;
        return `${num}+ CVs scanned`;
    }

    // Used on first load and again after each scan, so the banner keeps its words.
    async function refreshScanCount() {
        if (!socialProof || !scanCountEl) return;
        try {
            const resp = await fetch('/api/scan-count');
            const data = await resp.json();
            const count = data.count || 0;
            const velocity = data.velocity || 0;
            if (count < 10) return;
            scanCountEl.textContent = scanCountText(count);

            // Show velocity badge when traffic is active
            const velocityEl = document.getElementById('scanVelocity');
            if (velocity >= 5 && velocityEl) {
                velocityEl.textContent = `${velocity} scans this hour`;
                velocityEl.style.display = 'inline';
            }

            socialProof.style.display = 'block';
        } catch (e) {
            // Silently fail — social proof is non-critical
        }
    }
    refreshScanCount();

    // ============================================================
    // INLINE GATE HANDLERS
    // ============================================================
    const inlineGateForm = document.getElementById('inlineGateForm');

    if (inlineGateForm) {
        inlineGateForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const firstName = document.getElementById('inlineGateFirstName').value.trim();
            const email = document.getElementById('inlineGateEmail').value.trim();

            if (!firstName) {
                document.getElementById('inlineGateFirstName').style.borderColor = '#dc2626';
                document.getElementById('inlineGateFirstName').focus();
                return;
            }
            if (!email || !email.includes('@')) {
                document.getElementById('inlineGateEmail').style.borderColor = '#dc2626';
                document.getElementById('inlineGateEmail').focus();
                return;
            }

            // Reset borders
            document.getElementById('inlineGateFirstName').style.borderColor = '';
            document.getElementById('inlineGateEmail').style.borderColor = '';

            const submitBtn = inlineGateForm.querySelector('.inline-gate-btn');
            const btnText = submitBtn ? submitBtn.querySelector('.gate-btn-text') : null;
            const btnLoading = submitBtn ? submitBtn.querySelector('.gate-btn-loading') : null;

            if (btnText) btnText.style.display = 'none';
            if (btnLoading) btnLoading.style.display = 'inline';
            if (submitBtn) submitBtn.disabled = true;

            try {
                const incomingUtm = new URLSearchParams(window.location.search).get('utm_source') || 'resumeradar';
                const response = await fetch('/api/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, first_name: firstName, utm_source: incomingUtm }),
                });

                const result = await response.json();
                if (!response.ok || result.error) {
                    throw new Error(result.error || 'Subscription failed');
                }

                markSubscribed();
                // subscribe_completed is recorded server-side in /api/subscribe
                showToast('Subscribed! Your free report is ready below.');

                if (lastScanData) renderDeepResults(lastScanData);

            } catch (err) {
                console.error('Inline gate signup error:', err);
                showToast('Signup did not complete. You can retry; your full report is still available.', true);
            } finally {
                if (btnText) btnText.style.display = 'inline';
                if (btnLoading) btnLoading.style.display = 'none';
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }

    // Skip-for-now: session-only unlock, deliberately low-key styling.
    // History: removed in 14b9ef1 (Mar 12, gate-primary funnel decision);
    // owner reinstated it 26 Aug 2026 — "there, but not prominent".
    const inlineGateSkip = document.getElementById('inlineGateSkip');
    if (inlineGateSkip) {
        inlineGateSkip.addEventListener('click', () => {
            try {
                sessionStorage.setItem('resumeradar_gate_skipped', '1');
            } catch (e) { /* private mode — unlock still works this render */ }
            trackOncePerScan('gate_skipped');
            if (lastScanData) renderDeepResults(lastScanData);
        });
    }

    // ============================================================
    // COLLAPSIBLE SECTIONS (deep results)
    // ============================================================
    document.addEventListener('click', (e) => {
        const toggle = e.target.closest('.card-header-toggle');
        if (!toggle) return;

        const targetId = toggle.dataset.target;
        const section = toggle.dataset.section;
        const content = document.getElementById(targetId);
        const icon = toggle.querySelector('.toggle-icon');
        if (!content) return;

        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
        if (icon) icon.textContent = isHidden ? '−' : '+';
        toggle.setAttribute('aria-expanded', isHidden ? 'true' : 'false');

        // Fire section expand event (once per scan)
        if (isHidden && section) {
            trackOncePerScan('section_expanded_' + section);
        }
    });

    // ============================================================
    // MOBILE STICKY CTA (visible when results are in viewport)
    // ============================================================
    const stickyCta = document.getElementById('stickyCta');
    if (stickyCta && resultsSection && window.IntersectionObserver) {
        // Show the bar only after the reader has scrolled past the score and the
        // improvement cards, so it never covers a report they have not read yet.
        let resultsInView = false;
        function updateStickyCta() {
            const deep = document.getElementById('deepResults');
            const passedImprovements = !!deep && deep.offsetParent !== null && deep.getBoundingClientRect().top < 0;
            stickyCta.style.display = resultsInView && passedImprovements ? 'block' : 'none';
        }
        const stickyObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => { resultsInView = entry.isIntersecting; });
            updateStickyCta();
        }, { threshold: 0 });
        stickyObserver.observe(resultsSection);
        window.addEventListener('scroll', updateStickyCta, { passive: true });

        // Track sticky CTA click
        stickyCta.querySelector('button').addEventListener('click', () => {
            trackOncePerScan('sticky_cta_clicked');
        });
    }

    // ============================================================
    // JUMP MENU (results) + in-page links to folded sections
    // ============================================================
    function openSection(el) {
        // Unfold a collapsed card, or a <details>, before scrolling to it.
        if (!el) return;
        if (el.tagName === 'DETAILS') { el.open = true; return; }
        const toggle = el.querySelector('.card-header-toggle');
        const content = toggle && document.getElementById(toggle.dataset.target);
        if (content && content.style.display === 'none') toggle.click();
    }

    function jumpTarget(link) {
        const visible = el => el && el.offsetParent !== null;
        const main = document.querySelector(link.getAttribute('href'));
        if (visible(main)) return main;
        const fallback = link.dataset.fallback && document.querySelector(link.dataset.fallback);
        return visible(fallback) ? fallback : null;
    }

    function updateJumpMenu() {
        document.querySelectorAll('#resultsJump a').forEach(link => { link.hidden = !jumpTarget(link); });
    }

    document.addEventListener('click', (e) => {
        const link = e.target.closest('#resultsJump a, a[href="#privacy"]');
        if (!link) return;
        const target = link.closest('#resultsJump') ? jumpTarget(link) : document.querySelector(link.getAttribute('href'));
        if (!target) return;
        e.preventDefault();
        openSection(target);
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // ============================================================
    // TAB SWITCHING
    // ============================================================
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;

            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById(`tab-${targetTab}`).classList.add('active');
            uploadError.hidden = true; // an old file error no longer applies
        });
    });

    // ============================================================
    // FILE UPLOAD HANDLING
    // ============================================================

    // Click to upload
    dropZone.addEventListener('click', () => resumeFile.click());

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    // File input change
    resumeFile.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Remove file
    removeFileBtn.addEventListener('click', () => {
        resumeFile.value = '';
        fileSelected.style.display = 'none';
        dropZone.style.display = 'block';
    });

    function handleFileSelect(file) {
        const allowedTypes = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ];
        const allowedExtensions = ['.pdf', '.docx'];
        const ext = '.' + file.name.split('.').pop().toLowerCase();

        if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(ext)) {
            showUploadError('Please upload a PDF or DOCX file.');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showUploadError('File too large. Maximum size is 5MB.');
            return;
        }

        // Transfer file to the input
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        resumeFile.files = dataTransfer.files;

        // Show file selected UI
        fileName.textContent = file.name;
        fileSelected.style.display = 'flex';
        dropZone.style.display = 'none';
        hideError();
    }

    // ============================================================
    // FORM SUBMISSION
    // ============================================================
    scanForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError();

        // Validate inputs
        const jobDescription = document.getElementById('jobDescription').value.trim();
        const resumeText = document.getElementById('resumeText').value.trim();
        const hasFile = resumeFile.files.length > 0;
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;

        if (!jobDescription) {
            showError('Please paste a job description.', document.getElementById('jobDescription'));
            return;
        }

        if (activeTab === 'upload' && !hasFile) {
            showUploadError('Please upload your CV, or switch to the "Paste text" tab.', dropZone);
            return;
        }

        if (activeTab === 'paste' && !resumeText) {
            showError('Please paste your CV text.', document.getElementById('resumeText'));
            return;
        }

        // Reset per-scan events
        firedEvents.clear();
        trackEvent('scan_started');

        // Show loading state
        setLoading(true);

        try {
            const formData = new FormData();
            formData.append('job_description', jobDescription);
            formData.append('journey_id', journeyId);

            if (activeTab === 'upload' && hasFile) {
                formData.append('resume_file', resumeFile.files[0]);
            } else if (activeTab === 'paste' && resumeText) {
                formData.append('resume_text', resumeText);
            }

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);

            let response;
            try {
                response = await fetch('/api/scan', {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal,
                });
            } catch (err) {
                clearTimeout(timeoutId);
                if (err.name === 'AbortError') {
                    trackEvent('scan_failed');
                    setLoading(false); // bring the form back first, so the error is not pushed off screen
                    showError('The scan is taking longer than usual. Please try again in a moment. Your text is still here.');
                    return;
                }
                throw err;
            }
            clearTimeout(timeoutId);

            const data = await response.json();

            if (!response.ok || data.error) {
                trackEvent('scan_failed');
                setLoading(false);
                showError(data.error || 'Something went wrong. Please try again.');
                return;
            }

            // Store data for report generation
            lastJobView = data.job_description_view || [];
            delete data.job_description_view;
            lastScanData = data;
            try { activeJobKey = await ResumeRadarScan.jobKey(jobDescription); } catch (e) { activeJobKey = ''; }

            // Set scan ID for event deduplication
            currentScanId = data.scan_id || data.request_id || String(Date.now());

            // Update social proof counter after successful scan (not awaited: non-critical)
            refreshScanCount();

            // Every scan includes the complete free report; signup is optional.
            renderResults(data);

        } catch (err) {
            console.error('Scan error:', err);
            trackEvent('scan_failed');
            setLoading(false);
            showError('We could not reach ResumeRadar. Check your connection and try again. Your text is still here.');
        } finally {
            setLoading(false);
        }
    });

    // Scan Again button — clear everything so user starts fresh
    scanAgainBtn.addEventListener('click', () => {
        comparisonBaseline = null;
        document.getElementById('rescanHint').hidden = true;
        resultsSection.style.display = 'none';

        // Clear form fields
        const resumeTextarea = document.getElementById('resumeText');
        const jobTextarea = document.getElementById('jobDescription');
        if (resumeTextarea) resumeTextarea.value = '';
        if (jobTextarea) jobTextarea.value = '';

        // Clear file upload
        if (resumeFile) resumeFile.value = '';
        if (fileSelected) fileSelected.style.display = 'none';
        if (dropZone) dropZone.style.display = 'block';

        // Switch back to Upload tab
        const uploadTabBtn = document.querySelector('.tab-btn[data-tab="upload"]');
        if (uploadTabBtn) {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            uploadTabBtn.classList.add('active');
            document.getElementById('tab-upload').classList.add('active');
        }

        hideError();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    function scanSnapshot(data) {
        return {score: data.match_score, jobKey: activeJobKey, scoreVersion: data.score_version || '2',
            matchedKeywords: Object.values(data.matched_keywords || {}).flat()};
    }

    function rescanUpdatedCV() {
        if (lastScanData) comparisonBaseline = scanSnapshot(lastScanData);
        // Keep the target job and pasted text available for editing; replace an uploaded file.
        resultsSection.style.display = 'none';
        if (resumeFile) resumeFile.value = '';
        if (fileSelected) fileSelected.style.display = 'none';
        if (dropZone) dropZone.style.display = 'block';
        document.getElementById('rescanHint').hidden = false;
        hideError();
        document.getElementById('scanForm').scrollIntoView({behavior:'smooth', block:'start'});
        const target = document.querySelector('.tab-btn.active');
        if (target) target.focus({preventScroll:true});
    }
    document.getElementById('rescanUpdatedBtn').addEventListener('click', rescanUpdatedCV);
    document.getElementById('stickyRescanBtn').addEventListener('click', rescanUpdatedCV);

    // ============================================================
    // EXAMPLE REPORT: fills in a sample CV and job, then scans
    // ============================================================
    const demoScanBtn = document.getElementById('demoScanBtn');

    const DEMO_RESUME = `JAMIE SMITH
London, UK | jamie.smith@example.com | +44 7700 900123 | linkedin.com/in/jamiesmith-demo

PROFESSIONAL SUMMARY
Software Engineer with 4 years of experience building web applications and APIs for growing product teams. Skilled in Python, Django and React, with a focus on clean code, automated testing and fast, reliable releases.

EXPERIENCE

Software Engineer | TechStream Solutions | Jan 2022 - Present
- Built and maintained a Django and PostgreSQL booking platform used by 40,000 customers a month
- Designed REST APIs consumed by web and mobile apps, cutting page load time by 35%
- Set up CI/CD pipelines with GitHub Actions, reducing release time from a day to 20 minutes
- Introduced pytest and unit testing standards, raising test coverage from 30% to 85%
- Moved background jobs to Redis queues, removing timeouts at peak traffic
- Added monitoring and alerting that cut the time to spot incidents by half

Junior Developer | DataFlow Inc | Jun 2020 - Dec 2021
- Built React components and JavaScript features for a customer dashboard
- Wrote SQL reports and Python scripts that saved the support team 15 hours a week
- Packaged services with Docker so new developers could set up in under an hour
- Took part in code reviews and Agile sprint planning

EDUCATION
BSc Computer Science | University of Manchester | 2020

SKILLS
Python, Django, Flask, JavaScript, React, HTML, CSS
PostgreSQL, SQL, Redis, REST, Docker, Git, GitHub Actions, Linux
CI/CD, pytest, unit testing, Agile, Scrum`;

    const DEMO_JOB = `Senior Software Engineer

About the Role
We are looking for a Senior Software Engineer to join our Product team and help us build features our customers love. You will design, build and run the web services and interfaces behind our booking platform.

Responsibilities
- Build new features across our Python back end and TypeScript front end
- Design and maintain REST and GraphQL APIs used by our web and mobile apps
- Write well-tested code and keep our CI/CD pipelines fast and reliable
- Run services in Docker and Kubernetes and improve how we deploy them
- Monitor performance and fix issues before customers notice them
- Work closely with product managers and designers to shape new features
- Review code, mentor junior engineers and help set engineering standards

Requirements
- 5+ years of experience in software engineering
- Strong Python skills with a web framework (Django, FastAPI or Flask)
- Commercial experience with TypeScript and React
- Solid knowledge of PostgreSQL and SQL
- Experience with Docker and Kubernetes
- Experience building and running microservices
- Experience designing GraphQL or REST APIs
- Experience with CI/CD tools (GitHub Actions, Jenkins or CircleCI)
- Knowledge of monitoring tools (Prometheus, Grafana or similar)
- Excellent communication and collaboration skills
- Problem-solving mindset with attention to detail

Nice to Have
- Experience with Kafka or other event streaming tools
- Knowledge of OAuth and web security best practices
- Understanding of GDPR and handling personal data
- Experience with Elasticsearch
- Familiarity with Terraform`;

    if (demoScanBtn) {
        demoScanBtn.addEventListener('click', (e) => {
            e.preventDefault();

            // 1. Switch to the "Paste Text" tab
            const pasteTabBtn = document.querySelector('.tab-btn[data-tab="paste"]');
            if (pasteTabBtn) {
                tabBtns.forEach(b => b.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));
                pasteTabBtn.classList.add('active');
                document.getElementById('tab-paste').classList.add('active');
            }

            // 2. Fill in the sample CV and job description
            const resumeTextarea = document.getElementById('resumeText');
            const jobTextarea = document.getElementById('jobDescription');

            if (resumeTextarea) resumeTextarea.value = DEMO_RESUME;
            if (jobTextarea) jobTextarea.value = DEMO_JOB;

            // 3. Clear any uploaded file (in case they had one)
            if (resumeFile) resumeFile.value = '';
            if (fileSelected) fileSelected.style.display = 'none';
            if (dropZone) dropZone.style.display = 'block';

            // 4. Track demo scan for funnel analytics
            trackEvent('demo_scan');

            // 5. Run the scan straight away, so one click shows a full report
            if (!scanBtn.disabled) {
                if (scanForm.requestSubmit) scanForm.requestSubmit();
                else scanBtn.click();
            }
        });
    }

    // ============================================================
    // REPORT GENERATION
    // ============================================================

    /**
     * Generate a clean, readable text report from the scan data.
     */
    function generateTextReport(data) {
        const ai = data.ai_suggestions || {};
        const ats = data.ats_formatting || {};
        const now = new Date().toLocaleDateString('en-US', {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });

        let report = [];

        report.push('═══════════════════════════════════════════');
        report.push('  RESUMERADAR: ATS SCAN REPORT');
        report.push('  Make your experience clear.');
        report.push('═══════════════════════════════════════════');
        report.push(`  Generated: ${now}`);
        report.push('');

        // Score
        report.push('───────────────────────────────────────────');
        report.push(`  JOB-DESCRIPTION MATCH ESTIMATE: ${ResumeRadarScan.scoreText(data.match_score)}`);
        report.push('───────────────────────────────────────────');
        report.push(`  Keywords Matched: ${data.total_matched}`);
        report.push(`  Keywords Missing: ${data.total_missing}`);
        report.push(`  Total Job Keywords: ${data.total_job_keywords}`);
        report.push('');

        // AI Summary
        if (ai.summary) {
            report.push('SUMMARY');
            report.push(sanitizeAIText(ai.summary));
            report.push('');
        }

        // Category Breakdown
        report.push('───────────────────────────────────────────');
        report.push('  CATEGORY BREAKDOWN');
        report.push('───────────────────────────────────────────');
        const catLabels = {
            technical_skills: 'Technical Skills',
            soft_skills: 'Soft Skills',
            certifications: 'Certifications',
            education: 'Education',
            action_verbs: 'Action Verbs',
        };
        for (const [key, info] of Object.entries(data.category_scores || {})) {
            if (info.total >= MIN_TERMS_FOR_CATEGORY_SCORE) {
                report.push(`  ${catLabels[key] || key}: ${Math.round(info.score)}% (${info.matched}/${info.total})`);
            }
        }
        report.push('');

        // Missing Keywords
        const missingEntries = Object.entries(data.missing_keywords || {}).filter(([, v]) => v && v.length > 0);
        if (missingEntries.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  KEYWORDS NOT FOUND IN YOUR CV');
            report.push('  (Already have these? Add them. Don\'t? Consider learning them.)');
            report.push('───────────────────────────────────────────');
            for (const [cat, words] of missingEntries) {
                report.push(`  ${catLabels[cat] || cat}: ${words.map(kw).join(', ')}`);
            }
            report.push('');
        }

        // Matched Keywords
        const matchedEntries = Object.entries(data.matched_keywords || {}).filter(([, v]) => v && v.length > 0);
        if (matchedEntries.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  MATCHED KEYWORDS');
            report.push('───────────────────────────────────────────');
            for (const [cat, words] of matchedEntries) {
                report.push(`  ${catLabels[cat] || cat}: ${words.map(kw).join(', ')}`);
            }
            report.push('');
        }

        // Strengths
        if (ai.strengths && ai.strengths.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  YOUR STRENGTHS');
            report.push('───────────────────────────────────────────');
            ai.strengths.forEach(s => report.push(`  + ${s}`));
            report.push('');
        }

        // Key Improvements
        if (ai.critical_improvements && ai.critical_improvements.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  KEY IMPROVEMENTS');
            report.push('───────────────────────────────────────────');
            ai.critical_improvements.forEach(item => {
                report.push(`  [${(item.priority || 'medium').toUpperCase()}] ${item.section}: ${item.issue}`);
                report.push(`    → ${item.suggestion}`);
                report.push('');
            });
        }

        // Keyword Suggestions
        if (ai.keyword_suggestions && ai.keyword_suggestions.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  HOW TO ADD MISSING KEYWORDS');
            report.push('───────────────────────────────────────────');
            ai.keyword_suggestions.forEach(item => {
                report.push(`  "${item.keyword}" → ${item.where_to_add}`);
                report.push(`    ${item.how_to_add}`);
                report.push('');
            });
        }

        // Quick Wins
        if (ai.quick_wins && ai.quick_wins.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  QUICK WINS');
            report.push('───────────────────────────────────────────');
            ai.quick_wins.forEach(w => report.push(`  * ${w}`));
            report.push('');
        }

        // ATS Formatting
        if (ats.issues && ats.issues.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  ATS FORMATTING ISSUES');
            report.push('───────────────────────────────────────────');
            ats.issues.forEach(issue => {
                const icons = { critical: '[!!]', warning: '[!]', info: '[i]' };
                report.push(`  ${icons[issue.type] || '[i]'} ${issue.message}`);
                report.push(`    ${issue.detail}`);
            });
            report.push('');
        }

        report.push('═══════════════════════════════════════════');
        report.push('  Report by ResumeRadar');
        report.push('  Built by Olushola Oladipupo');
        report.push('  https://www.linkedin.com/in/olushola-oladipupo/');
        report.push('  Check your own CV free at');
        report.push('  https://resumeradar.sholastechnotes.com');
        report.push('═══════════════════════════════════════════');

        return report.join('\n');
    }

    // ============================================================
    // COPY REPORT
    // ============================================================
    copyReportBtn.addEventListener('click', async () => {
        if (!lastScanData) return;

        const reportText = generateTextReport(lastScanData);

        try {
            await navigator.clipboard.writeText(reportText);
            showToast('Report copied to clipboard!');
        } catch (err) {
            // Fallback for browsers that don't support clipboard API
            const textarea = document.createElement('textarea');
            textarea.value = reportText;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            showToast('Report copied to clipboard!');
        }
    });

    // ============================================================
    // DOWNLOAD REPORT (PDF)
    // ============================================================
    downloadReportBtn.addEventListener('click', async () => {
        if (!lastScanData) return;

        showToast('Generating PDF...');
        downloadReportBtn.disabled = true;

        try {
            const response = await fetch('/api/download-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(lastScanData),
            });

            if (!response.ok) {
                // A 403 means the signed result is too old or was changed;
                // the server says what to do, so show its message.
                let serverError = '';
                try { serverError = (await response.json()).error || ''; } catch (e) { /* not JSON */ }
                const failure = new Error('PDF generation failed');
                failure.serverError = serverError;
                throw failure;
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const date = new Date().toISOString().split('T')[0];
            a.download = `ResumeRadar_Report_${date}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            showToast('PDF report downloaded!');
        } catch (err) {
            console.error('PDF download error:', err);
            showToast(err.serverError
                ? err.serverError + ' Downloading a text version for now.'
                : 'Failed to generate PDF. Downloading text version...', true);

            // Fallback to text download
            const reportText = generateTextReport(lastScanData);
            const blob = new Blob([reportText], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const date = new Date().toISOString().split('T')[0];
            a.download = `ResumeRadar_Report_${date}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } finally {
            downloadReportBtn.disabled = false;
        }
    });

    // ============================================================
    // EMAIL REPORT (via mailto)
    // ============================================================
    let modalReturnFocus = null;
    function openEmailModal() {
        modalReturnFocus = document.activeElement;
        emailModal.style.display = 'flex';
        fitModalToViewport();
        if (emailConfirmWait) {
            // Still waiting for a click on the confirm link: show that, not a blank form.
            showEmailStep('wait');
            return;
        }
        showEmailStep('form');
        emailInput.value = '';
        emailInput.focus();
    }

    function showEmailStep(step) {
        emailFormStep.hidden = step !== 'form';
        emailWaitStep.hidden = step !== 'wait';
        if (step === 'wait') emailWaitText.focus();
    }
    emailReportBtn.addEventListener('click', openEmailModal);
    // The same dialog, offered beside the score where people first see their result.
    const scoreEmailBtn = document.getElementById('scoreEmailBtn');
    if (scoreEmailBtn) scoreEmailBtn.addEventListener('click', openEmailModal);

    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);
    document.getElementById('emailWaitCloseBtn').addEventListener('click', closeModal);
    document.getElementById('emailChangeBtn').addEventListener('click', () => {
        stopConfirmWait();
        showEmailStep('form');
        emailInput.focus();
    });

    // Close modal on backdrop click
    emailModal.addEventListener('click', (e) => {
        if (e.target === emailModal) closeModal();
    });

    // Close modal on Escape key, and keep Tab focus inside the dialog
    document.addEventListener('keydown', (e) => {
        if (emailModal.style.display !== 'flex') return;
        if (e.key === 'Escape') {
            closeModal();
            return;
        }
        if (e.key !== 'Tab') return;
        const focusable = Array.from(emailModal.querySelectorAll('button, input, a[href]'))
            .filter(el => !el.disabled && el.offsetParent !== null);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!emailModal.contains(document.activeElement)) {
            e.preventDefault();
            first.focus();
        } else if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    });

    // On a phone the on-screen keyboard shrinks the visible area but not the layout
    // viewport the fixed overlay is sized to, so Send ended up behind the keyboard.
    // Size the overlay to the visible area instead (the CSS keeps Send pinned).
    const visualViewport = window.visualViewport;
    function fitModalToViewport() {
        if (!visualViewport || emailModal.style.display !== 'flex') return;
        if (Math.abs(visualViewport.scale - 1) > 0.01) {
            // Pinch-zoomed: leave the overlay at full size rather than squash the dialog.
            emailModal.style.removeProperty('--modal-top');
            emailModal.style.removeProperty('--modal-height');
            return;
        }
        emailModal.style.setProperty('--modal-top', `${visualViewport.offsetTop}px`);
        emailModal.style.setProperty('--modal-height', `${visualViewport.height}px`);
        // The keyboard has just shrunk the dialog: keep the field being typed in on screen.
        if (emailModal.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') {
            document.activeElement.scrollIntoView({ block: 'nearest' });
        }
    }
    if (visualViewport) {
        visualViewport.addEventListener('resize', fitModalToViewport);
        visualViewport.addEventListener('scroll', fitModalToViewport);
    }

    // Return in the email field sends, as it would in a form.
    emailInput.addEventListener('keydown', (e) => {
        // keyCode 229: Safari's Return that confirms an input-method word.
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        if (!sendEmailBtn.disabled) sendEmailBtn.click();
    });

    function closeModal() {
        emailModal.style.display = 'none';
        emailModal.style.removeProperty('--modal-top');
        emailModal.style.removeProperty('--modal-height');
        if (modalReturnFocus && document.contains(modalReturnFocus)) modalReturnFocus.focus();
        modalReturnFocus = null;
    }

    // ------------------------------------------------------------
    // Waiting for the address to be confirmed. The first email is only a
    // confirm link; once its owner presses Confirm, this page sends the report.
    // ------------------------------------------------------------
    // Every 5 seconds for the first 5 minutes, then every 15, then every 60
    // if the server says to slow down: well inside the status route's limit.
    const CONFIRM_WAIT_MS = 60 * 60 * 1000; // the link's own lifetime
    let emailConfirmWait = null; // { email, scan, timer, until, started, busy, slow }

    function confirmPollDelay(wait) {
        if (wait.slow) return 60000;
        return Date.now() - wait.started < 5 * 60 * 1000 ? 5000 : 15000;
    }

    // The server only needs the signed report fields, never the CV text.
    function reportPayload(scan) {
        const { resume_text, ...rest } = scan; // eslint-disable-line no-unused-vars
        return rest;
    }

    function stopConfirmWait() {
        if (emailConfirmWait && emailConfirmWait.timer) clearTimeout(emailConfirmWait.timer);
        emailConfirmWait = null;
    }

    function startConfirmWait(email, scan) {
        stopConfirmWait();
        const now = Date.now();
        emailConfirmWait = { email, scan, timer: null, until: now + CONFIRM_WAIT_MS, started: now, busy: false, slow: false };
        emailWaitText.textContent = `We've sent a confirmation link to ${email}. Check your inbox (and spam folder).`;
        showEmailStep('wait');
        scheduleConfirmCheck();
    }

    function scheduleConfirmCheck() {
        const wait = emailConfirmWait;
        if (!wait) return;
        wait.timer = setTimeout(() => checkConfirmed(wait), confirmPollDelay(wait));
    }

    async function checkConfirmed(wait) {
        if (wait !== emailConfirmWait || wait.busy) return;
        // A new scan replaces the report this address was confirming.
        if (wait.scan !== lastScanData || Date.now() > wait.until) {
            stopConfirmWait();
            if (emailModal.style.display === 'flex') showEmailStep('form');
            return;
        }
        wait.busy = true;
        let confirmed = false;
        try {
            const response = await fetch('/api/email-report/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: wait.email, scan_data: reportPayload(wait.scan) }),
            });
            if (response.ok) confirmed = (await response.json()).confirmed === true;
            wait.slow = response.status === 429;
        } catch (err) {
            // Network blip: try again on the next tick.
        } finally {
            wait.busy = false;
        }
        if (wait !== emailConfirmWait) return;
        if (confirmed) {
            stopConfirmWait();
            emailWaitText.textContent = `Address confirmed. Sending your report to ${wait.email}...`;
            await sendReportEmail(wait.email, wait.scan);
        } else {
            scheduleConfirmCheck();
        }
    }

    // Coming back from the inbox: check straight away rather than on the next tick.
    function checkConfirmedNow() {
        if (!emailConfirmWait || emailConfirmWait.busy || document.visibilityState !== 'visible') return;
        clearTimeout(emailConfirmWait.timer);
        checkConfirmed(emailConfirmWait);
    }
    document.addEventListener('visibilitychange', checkConfirmedNow);
    window.addEventListener('focus', checkConfirmedNow);

    async function sendReportEmail(email, scan) {
        const response = await fetch('/api/email-report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email, scan_data: reportPayload(scan) }),
        }).catch(() => null);
        let result = {};
        try { result = response ? await response.json() : {}; } catch (e) { result = {}; }

        if (response && response.ok && result.status === 'confirm_sent') {
            startConfirmWait(email, scan);
            return;
        }
        if (response && response.ok && !result.error) {
            if (emailModal.style.display === 'flex') closeModal();
            showEmailStep('form');
            showToast(`Report sent to ${email}!`);
            return;
        }

        const message = result.error || 'Failed to send email. Please try again.';
        // If the API isn't configured, fall back to mailto
        if (message.includes('not configured')) {
            showToast('Email service not set up yet. Opening email client...', true);
            const reportText = generateShortReport(scan);
            const score = ResumeRadarScan.scoreText(scan.match_score);
            const subject = encodeURIComponent(`ResumeRadar Report (match estimate: ${score})`);
            const mailtoUrl = `mailto:${encodeURIComponent(email)}?subject=${subject}&body=${encodeURIComponent(reportText)}`;
            window.location.href = mailtoUrl;
            closeModal();
            return;
        }
        if (!emailWaitStep.hidden) showEmailStep('form');
        showToast(message, true);
    }

    sendEmailBtn.addEventListener('click', async () => {
        const email = emailInput.value.trim();

        if (!email || !email.includes('@')) {
            emailInput.style.borderColor = '#dc2626';
            emailInput.focus();
            return;
        }

        if (!lastScanData) return;

        // Show loading state
        const sendText = sendEmailBtn.querySelector('.send-text');
        const sendLoading = sendEmailBtn.querySelector('.send-loading');
        sendText.style.display = 'none';
        sendLoading.style.display = 'inline';
        sendEmailBtn.disabled = true;
        emailInput.style.borderColor = '';

        try {
            await sendReportEmail(email, lastScanData);
        } finally {
            sendText.style.display = 'inline';
            sendLoading.style.display = 'none';
            sendEmailBtn.disabled = false;
        }
    });

    /**
     * Generate a shorter report for email (mailto has URL length limits)
     */
    function generateShortReport(data) {
        const ai = data.ai_suggestions || {};
        let report = [];

        report.push('RESUMERADAR: ATS SCAN REPORT');
        report.push(`Generated: ${new Date().toLocaleDateString()}`);
        report.push('');
        report.push(`JOB-DESCRIPTION MATCH ESTIMATE: ${ResumeRadarScan.scoreText(data.match_score)}`);
        report.push(`Keywords Matched: ${data.total_matched} | Missing: ${data.total_missing} | Total: ${data.total_job_keywords}`);
        report.push('');

        if (ai.summary) {
            report.push(sanitizeAIText(ai.summary));
            report.push('');
        }

        // Missing keywords (compact)
        const missing = Object.entries(data.missing_keywords || {})
            .filter(([, v]) => v && v.length > 0)
            .map(([, words]) => words.map(kw).join(', '));
        if (missing.length > 0) {
            report.push('MISSING KEYWORDS: ' + missing.join(', '));
            report.push('');
        }

        // Quick wins
        if (ai.quick_wins && ai.quick_wins.length > 0) {
            report.push('QUICK WINS:');
            ai.quick_wins.forEach(w => report.push(`* ${w}`));
            report.push('');
        }

        report.push('---');
        report.push('Built by Olushola Oladipupo');
        report.push('Check your own CV free at https://resumeradar.sholastechnotes.com');

        return report.join('\n');
    }

    // ============================================================
    // TOAST NOTIFICATION
    // ============================================================
    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        const toastIcon = toast.querySelector('.toast-icon');

        toastMessage.textContent = message;
        toastIcon.textContent = isError ? '⚠️' : '✅';
        toast.className = isError ? 'toast toast-error' : 'toast';
        toast.style.display = 'flex';
        announce(document.getElementById('toastLive'), message);

        // Auto-hide after 3 seconds
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }

    // ============================================================
    // RENDER RESULTS
    // ============================================================
    function renderResults(data) {
        // Show results section
        resultsSection.style.display = 'block';
        trackOncePerScan('partial_results_viewed');
        try {
            if (sessionStorage.getItem('resumeradar_ref')) trackOncePerScan('referred_scan_completed');
        } catch (e) { /* optional aggregate count */ }

        // ===== FREE TIER =====
        // 1. Score
        renderScore(data);

        // 2. Top 3 Missing Keywords
        renderTopMissingKeywords(data);

        // 3. Quick Wins
        renderQuickWins(data);

        renderDeepResults(data);
        if (!isSubscribed() && !gateSkipped()) showInlineGate();
        // Lets feedback.js reset the "Was this useful?" card for each new report.
        document.dispatchEvent(new CustomEvent('rr:results-rendered'));
        const comparison = document.getElementById('rescanComparison');
        comparison.hidden = !comparisonBaseline;
        document.getElementById('sharePrompt').hidden = true;
        if (comparisonBaseline) {
            const change = ResumeRadarScan.compareScan(scanSnapshot(data), comparisonBaseline);
            if (change) {
                comparison.innerHTML = `<h2>What changed for this job</h2><p>Keyword coverage ${change.delta > 0 ? 'increased by ' : change.delta < 0 ? 'decreased by ' : 'changed by '}${Math.abs(change.delta).toFixed(1)} percentage points.</p>
                    <details><summary>Review keyword changes</summary><p>Newly found: ${escapeHtml(change.added.map(kw).join(', ') || 'none')}.</p><p>No longer found: ${escapeHtml(change.removed.map(kw).join(', ') || 'none')}.</p></details>
                    <p>This measures keyword evidence, not your chances of being hired.</p>`;
                // Best moment to ask: the user has just seen the tool help them.
                if (change.delta > 0) {
                    document.getElementById('sharePrompt').hidden = false;
                    trackOncePerScan('share_prompt_shown');
                }
            } else {
                comparison.textContent = 'This scan uses a different job description, scoring version, or has no numeric estimate, so a score comparison would not be meaningful.';
            }
        }

        updateJumpMenu();

        // Scroll to results, and move keyboard and screen reader focus there too, so the
        // reader says "Your keyword coverage, 59%" and the next Tab starts in the report.
        setTimeout(() => {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            const heading = document.getElementById('scoreHeading');
            if (heading) heading.focus({ preventScroll: true });
        }, 100);
    }

    function renderDeepResults(data) {
        // Idempotent: safe to call multiple times
        const deepContainer = document.getElementById('deepResults');
        if (!deepContainer) return;

        // Hide inline gate if visible
        const gateCard = document.getElementById('inlineGateCard');
        if (gateCard) gateCard.style.display = 'none';

        // Show deep results container
        deepContainer.style.display = 'block';

        // Category Breakdown
        renderCategories(data.category_scores);

        // Sub-score bars (Formatting + Recruiter Tips)
        renderSubScoreBars(data);

        // Job description view first: the keyword lists link into it
        renderJobView(data);

        // Missing Keywords (full)
        renderKeywords('missingKeywords', data.missing_keywords, 'missing');

        // Matched Keywords
        renderKeywords('matchedKeywords', data.matched_keywords, 'matched');
        for (const id of ['missingKeywords', 'matchedKeywords']) {
            const card = document.getElementById(id).closest('.result-card');
            if (card) card.style.display = Number.isFinite(data.match_score) ? '' : 'none';
        }

        // AI Suggestions
        renderAISuggestions(data.ai_suggestions);

        // Cover Letter Key Points
        renderCoverLetterPoints(data.ai_suggestions);

        // ATS Formatting
        renderATSFormatting(data.ats_formatting);


        // Scan History
        saveScanToHistory(data);
        renderScanHistory();

        trackOncePerScan('deep_results_unlocked');
    }

    function renderTopMissingKeywords(data) {
        const card = document.getElementById('topMissingKeywords');
        const list = document.getElementById('topMissingList');
        if (!card || !list) return;

        const recommendations = data.priority_recommendations || [];
        if (!recommendations.length) { card.style.display = 'none'; return; }
        list.innerHTML = recommendations.slice(0, 3).map(item => {
            const labels = [item.priority === 'unspecified' ? 'Mentioned in job' : item.priority];
            if (item.one_of && item.one_of.length) labels.push('one of several options');
            if (item.mentions > 1) labels.push(`mentioned ${item.mentions} times`);
            return `
            <div class="top-missing-item">
                <strong class="top-missing-keyword">${escapeHtml(item.display || item.keyword)}</strong>
                <span class="top-missing-category">${escapeHtml(labels.join(' · '))}</span>
                <div class="recommendation-detail"><p>${escapeHtml(item.reason)}</p><p>${escapeHtml(item.suggestion)}</p></div>
            </div>`;
        }).join('');
        card.style.display = 'block';
    }

    function renderQuickWins(data) {
        const card = document.getElementById('quickWins');
        const list = document.getElementById('quickWinsList');
        if (!card || !list) return;

        const suggestions = data.ai_suggestions;
        // Without AI, the rule-based "quick wins" repeat the "Priorities for
        // this job" card word for word, so hide this card and say why.
        const aiResting = !!suggestions && typeof suggestions === 'object' && !suggestions.ai_powered;
        const restNote = document.getElementById('aiRestNote');
        if (restNote) restNote.hidden = !aiResting;
        if (!suggestions || aiResting) {
            card.style.display = 'none';
            return;
        }

        // Extract quick wins from AI suggestions
        let wins = [];
        if (suggestions.quick_wins && Array.isArray(suggestions.quick_wins)) {
            wins = suggestions.quick_wins.slice(0, 5);
        } else if (suggestions.critical_improvements && Array.isArray(suggestions.critical_improvements)) {
            wins = suggestions.critical_improvements.slice(0, 3);
        } else if (typeof suggestions === 'string') {
            // Fallback: split text into sentences
            const sentences = sanitizeAIText(suggestions).split(/[.\n]/).filter(s => s.trim().length > 10);
            wins = sentences.slice(0, 3);
        }

        if (wins.length === 0) {
            card.style.display = 'none';
            return;
        }

        list.innerHTML = wins.map((win, i) => {
            const text = escapeHtml(sanitizeAIText(typeof win === 'string' ? win : (win.suggestion || win.text || JSON.stringify(win))));
            return `<div class="quick-win-item">
                <span class="quick-win-number">${i + 1}</span>
                <span class="quick-win-text">${text}</span>
            </div>`;
        }).join('');

        card.style.display = 'block';
    }

    function showInlineGate() {
        const gateCard = document.getElementById('inlineGateCard');
        if (gateCard) gateCard.style.display = 'block';
    }

    function renderScore(data) {
        const score = data.match_score;
        const scoreNumber = document.getElementById('scoreNumber');
        const scoreFill = document.getElementById('scoreFill');
        const scoreSummary = document.getElementById('scoreSummary');
        const scoreStats = document.getElementById('scoreStats');

        // Reset circle for re-scans
        scoreFill.style.strokeDashoffset = 339.292;

        const scored = Number.isFinite(score);
        scoreNumber.classList.toggle('unscored', !scored);
        if (scored) animateNumber(scoreNumber, score);
        else scoreNumber.textContent = 'Not scored';
        // The visible number counts up; screen readers get the final figure with the heading.
        const headingValue = document.getElementById('scoreHeadingValue');
        if (headingValue) headingValue.textContent = scored ? `, ${Math.round(score)}%` : ', not scored';
        const explanation = document.getElementById('scoreExplanation');
        const method = document.getElementById('scoreMethod');
        if (method) method.hidden = !scored;
        if (explanation) explanation.textContent = data.score_explanation || 'A custom keyword coverage estimate, not an employer’s score, applicant ranking, or interview prediction.';

        // Animate circle
        const circumference = 339.292;
        const offset = circumference - ((Number.isFinite(score) ? score : 0) / 100) * circumference;
        setTimeout(() => {
            scoreFill.style.strokeDashoffset = offset;
        }, 100);

        // Color based on score
        let color;
        if (!Number.isFinite(score)) color = '#64748b';
        else if (score >= 75) color = '#0E5C4A';
        else if (score >= 50) color = '#B45309';
        else color = '#B91C1C';
        scoreFill.style.stroke = color;

        // Summary text
        let summaryText = '';
        if (data.ai_suggestions && data.ai_suggestions.summary) {
            summaryText = sanitizeAIText(data.ai_suggestions.summary);
        }
        // Fallback if AI summary is empty or was all artifacts
        if (!summaryText) {
            const N = data.total_missing || 0;
            if (score >= 75) {
                summaryText = `Your CV covers many recognised terms in this job description. Review the ${N} missing term${N !== 1 ? 's' : ''} and prioritise requirements you can support with evidence.`;
            } else if (score >= 50) {
                summaryText = `Your CV covers some recognised terms. Review the priorities below and describe relevant experience you already have.`;
            } else {
                summaryText = `We found ${N} terms not mentioned in your CV. This may reflect missing wording, unfamiliar vocabulary, or experience to develop.`;
            }
        }
        if (!scored) summaryText = 'There is not enough recognised job information to give a useful estimate. You can still review the writing suggestions and check the requirements manually.';
        scoreSummary.innerHTML = `<p>${escapeHtml(summaryText)}</p>`;

        // Stats boxes
        scoreStats.innerHTML = `
            <div class="stat-box">
                <span class="stat-number">${data.total_matched}</span>
                <span class="stat-label">Keywords matched</span>
            </div>
            <div class="stat-box">
                <span class="stat-number">${data.total_missing}</span>
                <span class="stat-label">Keywords missing</span>
            </div>
            <div class="stat-box">
                <span class="stat-number">${data.total_job_keywords}</span>
                <span class="stat-label">Total job keywords</span>
            </div>
        `;

        // === Role Fit Meter ===
        renderRoleFitMeter(data);
    }

    function renderRoleFitMeter(data) {
        const meter = document.getElementById('roleFitMeter');
        const fill = document.getElementById('fitMeterFill');
        const marker = document.getElementById('fitMeterMarker');
        const verdict = document.getElementById('fitVerdict');
        if (!meter || !fill || !marker || !verdict) return;

        const score = data.match_score;
        if (!Number.isFinite(score)) { meter.style.display = 'none'; return; }

        // Determine fit tier and messaging
        let tier, tierColor, tierText, tierBg, tierMsg;
        if (score >= 75) {
            tier = 'High keyword coverage';
            tierColor = '#0E5C4A';
            tierText = '#0A4638';
            tierBg = '#E6F1EC';
            tierMsg = 'This describes recognised terms, not your suitability for the role. Check required experience and qualifications separately.';
        } else if (score >= 50) {
            tier = 'Moderate keyword coverage';
            tierColor = '#B45309';
            tierText = '#92400e';
            tierBg = '#fef3c7';
            tierMsg = 'This describes recognised terms, not your suitability for the role. Check required experience and qualifications separately.';
        } else if (score >= 30) {
            tier = 'Some keyword coverage';
            tierColor = '#C2410C';
            tierText = '#9a3412';
            tierBg = '#fff7ed';
            tierMsg = 'This describes recognised terms, not your suitability for the role. Check required experience and qualifications separately.';
        } else {
            tier = 'Low keyword coverage';
            tierColor = '#B91C1C';
            tierText = '#991B1B';
            tierBg = '#fee2e2';
            tierMsg = 'This describes recognised terms, not your suitability for the role. Check required experience and qualifications separately.';
        }

        // Fill width = score percentage
        const fillPercent = Math.min(100, Math.max(2, score));

        // Animate
        setTimeout(() => {
            fill.style.width = fillPercent + '%';
            fill.style.background = `linear-gradient(90deg, ${tierColor}88, ${tierColor})`;
            marker.style.left = fillPercent + '%';
            marker.style.borderColor = tierColor;
        }, 300);

        verdict.innerHTML = `
            <div class="fit-verdict-badge" style="background: ${tierBg}; color: ${tierText};">
                <span class="fit-tier">${tier}</span>
            </div>
            <p class="fit-msg">${tierMsg}</p>
        `;

        meter.style.display = 'block';
    }

    function animateNumber(element, target) {
        let current = 0;
        const increment = target / 40;
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                current = target;
                clearInterval(timer);
            }
            element.textContent = `${Math.round(current)}%`;
        }, 30);
    }

    // Category percentages are only shown when the job names at least this many terms.
    const MIN_TERMS_FOR_CATEGORY_SCORE = 3;

    function renderCategories(categories) {
        const container = document.getElementById('categoryBars');
        container.innerHTML = '';

        const labels = {
            technical_skills: 'Technical skills',
            soft_skills: 'Soft skills',
            certifications: 'Certifications',
            education: 'Education',
            action_verbs: 'Action verbs',
        };

        let leftOut = false;
        for (const [key, data] of Object.entries(categories)) {
            if (data.total === 0) continue;
            // A percentage built on one or two job terms misleads, so skip it.
            if (data.total < MIN_TERMS_FOR_CATEGORY_SCORE) { leftOut = true; continue; }

            const score = data.score;
            let barClass = 'high';
            if (score < 50) barClass = 'low';
            else if (score < 75) barClass = 'medium';

            const bar = document.createElement('div');
            bar.className = 'category-bar';
            bar.innerHTML = `
                <div class="category-header">
                    <span class="category-name">${labels[key] || key}</span>
                    <span class="category-score">${Math.round(score)}% (${data.matched}/${data.total})</span>
                </div>
                <div class="bar-bg">
                    <div class="bar-fill ${barClass}" style="width: 0%"></div>
                </div>
            `;
            container.appendChild(bar);

            // Animate bar fill
            setTimeout(() => {
                bar.querySelector('.bar-fill').style.width = `${score}%`;
            }, 200);
        }
        if (leftOut) {
            const note = document.createElement('p');
            note.className = 'category-note';
            note.textContent = 'Groups where this job names fewer than three terms are left out, because a percentage on one or two words would mislead.';
            container.appendChild(note);
        }
    }

    function renderSubScoreBars(data) {
        const container = document.getElementById('categoryBars');
        if (!container) return;

        // Formatting score bar
        const ats = data.ats_formatting;
        if (ats && typeof ats.formatting_score === 'number') {
            renderSubScoreBar(container, 'ATS formatting', ats.formatting_score, ats.checklist, null);
        }

        // Recruiter Tips bar
        const rt = data.recruiter_tips;
        if (rt && typeof rt.score === 'number') {
            renderSubScoreBar(container, 'Recruiter tips', rt.score, rt.checklist, rt.quantification);
        }
    }

    function renderSubScoreBar(container, label, score, checklist, quantification) {
        let barClass = 'high';
        if (score < 50) barClass = 'low';
        else if (score < 80) barClass = 'medium';

        const bar = document.createElement('div');
        bar.className = 'category-bar subscore-bar';

        // Build checklist HTML
        let detailsHTML = '';
        if (checklist && checklist.length > 0) {
            const items = checklist.map(item => {
                const icon = item.passed ? '✅' : '❌';
                const detail = item.detail ? `: ${escapeHtml(item.detail)}` : '';
                return `<div class="subscore-item"><span class="subscore-icon">${icon}</span><span class="subscore-label">${escapeHtml(item.label)}${detail}</span><span class="subscore-pts">${escapeHtml(String(item.points))} pts</span></div>`;
            }).join('');
            detailsHTML = `<div class="subscore-details" style="display:none;">${items}</div>`;
        }

        // Flagged bullets section (for recruiter tips with quantification data)
        let flaggedHTML = '';
        if (quantification && quantification.flagged_bullets && quantification.flagged_bullets.length > 0) {
            const bullets = quantification.flagged_bullets.slice(0, 5).map(b => {
                const truncated = b.length > 100 ? b.substring(0, 100) + '...' : b;
                return `<div class="flagged-bullet"><span>${escapeHtml(truncated)}</span></div>`;
            }).join('');
            flaggedHTML = `<div class="flagged-bullets" style="display:none;">
                <div class="flagged-header">Bullets that could use metrics:</div>
                ${bullets}
            </div>`;
        }

        bar.innerHTML = `
            <div class="category-header subscore-header" style="cursor:pointer;">
                <span class="category-name">${label}</span>
                <span class="category-score">${Math.round(score)}%<span class="subscore-toggle"> ▸</span></span>
            </div>
            <div class="bar-bg">
                <div class="bar-fill ${barClass}" style="width: 0%"></div>
            </div>
            ${detailsHTML}
            ${flaggedHTML}
        `;
        container.appendChild(bar);

        // Animate bar fill
        setTimeout(() => {
            bar.querySelector('.bar-fill').style.width = `${score}%`;
        }, 200);

        // Toggle expand/collapse
        const header = bar.querySelector('.subscore-header');
        header.addEventListener('click', () => {
            const details = bar.querySelector('.subscore-details');
            const flagged = bar.querySelector('.flagged-bullets');
            const toggle = bar.querySelector('.subscore-toggle');
            if (details) {
                const visible = details.style.display !== 'none';
                details.style.display = visible ? 'none' : 'block';
                if (flagged) flagged.style.display = visible ? 'none' : 'block';
                toggle.textContent = visible ? ' ▸' : ' ▾';
            }
        });
    }

    function renderKeywords(containerId, keywords, type) {
        const container = document.getElementById(containerId);
        container.innerHTML = '';

        const labels = {
            technical_skills: 'Technical Skills',
            soft_skills: 'Soft Skills',
            certifications: 'Certifications',
            education: 'Education',
            action_verbs: 'Action Verbs',
        };

        let hasAny = false;

        for (const [category, words] of Object.entries(keywords)) {
            if (!words || words.length === 0) continue;
            hasAny = true;

            const section = document.createElement('div');
            section.className = 'keywords-section';
            section.innerHTML = `
                <div class="keywords-section-title">${labels[category] || category}</div>
                <div class="keyword-tags">
                    ${words.map(w => category !== 'action_verbs' && jobTermIndex.positions[w]
                        ? `<button type="button" class="keyword-tag keyword-jump ${type}" data-jd-keyword="${escapeHtml(w)}" aria-label="${escapeHtml(kw(w))}: show in job description">${escapeHtml(kw(w))}</button>`
                        : `<span class="keyword-tag ${type}">${escapeHtml(kw(w))}</span>`).join('')}
                </div>
            `;
            container.appendChild(section);
        }

        if (!hasAny) {
            container.innerHTML = `<p class="no-keywords">${
                type === 'missing'
                    ? 'No missing recognised terms detected. This does not confirm that all job requirements are met.'
                    : 'No keyword matches found.'
            }</p>`;
        }
    }

    // ============================================================
    // VIEW IN JOB DESCRIPTION
    // ============================================================
    function renderJobView(data) {
        const card = document.getElementById('jobViewCard');
        const text = document.getElementById('jobViewText');
        if (!card || !text) return;
        jobTermIndex = ResumeRadarScan.jobTermIndex(lastJobView);
        const marked = jobTermIndex.matched + jobTermIndex.missing;
        card.hidden = !marked || !Number.isFinite(data.match_score);
        text.textContent = '';
        if (card.hidden) { jobTermIndex = ResumeRadarScan.jobTermIndex([]); return; }
        const notes = {matched: ' (found in your CV)', missing: ' (not found in your CV)'};
        // Browsers submit line breaks as CRLF; show them as single breaks.
        const clean = (value) => String(value).replace(/\r\n?/g, '\n');
        const markFor = (piece, id) => {
            const mark = document.createElement('mark');
            mark.className = `jd-term ${piece.status}`;
            mark.id = id;
            mark.tabIndex = -1;
            return mark;
        };
        const noteFor = (status) => {
            const note = document.createElement('span');
            note.className = 'jd-term-note';
            note.textContent = notes[status];
            return note;
        };
        lastJobView.forEach((segment, index) => {
            if (!notes[segment.status]) { text.append(clean(segment.text)); return; }
            const mark = markFor(segment, `jd-term-${index}`);
            if (Array.isArray(segment.parts)) {
                segment.parts.forEach((part, partIndex) => {
                    if (!notes[part.status]) { mark.append(clean(part.text)); return; }
                    const inner = markFor(part, `jd-term-${index}-${partIndex}`);
                    inner.append(clean(part.text), noteFor(part.status));
                    mark.appendChild(inner);
                });
            } else {
                mark.append(clean(segment.text));
            }
            mark.appendChild(noteFor(segment.status));
            text.appendChild(mark);
        });
        const count = (n) => `${n} ${n === 1 ? 'term' : 'terms'}`;
        document.getElementById('jobViewMatchedCount').textContent = count(jobTermIndex.matched);
        document.getElementById('jobViewMissingCount').textContent = count(jobTermIndex.missing);
        document.getElementById('jobViewDetails').open = false;
    }

    // A keyword in the lists jumps to where the job mentions it; selecting it
    // again moves to the next mention.
    const jobJumpCursor = {};
    document.getElementById('deepResults').addEventListener('click', (event) => {
        const tag = event.target.closest('.keyword-jump');
        if (!tag) return;
        const keyword = tag.dataset.jdKeyword;
        const positions = jobTermIndex.positions[keyword];
        if (!positions) return;
        const visit = (jobJumpCursor[keyword] || 0) % positions.length;
        jobJumpCursor[keyword] = visit + 1;
        const mark = document.getElementById(positions[visit]);
        if (!mark) return;
        document.getElementById('jobViewDetails').open = true;
        document.querySelectorAll('.jd-term.active').forEach(el => el.classList.remove('active'));
        mark.classList.add('active');
        mark.focus({preventScroll: true});
        const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        mark.scrollIntoView({behavior: calm ? 'instant' : 'smooth', block: 'center'});
    });

    function renderAISuggestions(suggestions) {
        const container = document.getElementById('aiSuggestions');
        const badge = document.getElementById('aiBadge');
        container.innerHTML = '';

        if (suggestions.ai_powered) {
            badge.textContent = 'AI-powered analysis';
            badge.className = 'ai-badge powered';
        } else {
            badge.textContent = 'Rule-based analysis';
            badge.className = 'ai-badge fallback';
        }

        if (suggestions.api_error) {
            const notice = document.createElement('div');
            notice.className = 'ai-item';
            notice.innerHTML = `<p style="color: var(--warning);">${escapeHtml(suggestions.api_error)}</p>`;
            container.appendChild(notice);
        }

        // Strengths
        if (suggestions.strengths && suggestions.strengths.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `
                <h3>Your strengths</h3>
                ${suggestions.strengths.map(s => `<div class="strength-item">${escapeHtml(s)}</div>`).join('')}
            `;
            container.appendChild(section);
        }

        // Critical Improvements
        if (suggestions.critical_improvements && suggestions.critical_improvements.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>Key improvements</h3>`;
            suggestions.critical_improvements.forEach(item => {
                const priority = item.priority || 'medium';
                const div = document.createElement('div');
                div.className = `ai-item ${priority}-priority`;
                div.innerHTML = `
                    <p><span class="label">${escapeHtml(item.section)}:</span> ${escapeHtml(item.issue)}</p>
                    <p style="margin-top: 6px; color: var(--primary);">→ ${escapeHtml(item.suggestion)}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Keyword Suggestions
        if (suggestions.keyword_suggestions && suggestions.keyword_suggestions.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>How to add these keywords to your CV</h3>`;
            suggestions.keyword_suggestions.forEach(item => {
                const div = document.createElement('div');
                div.className = 'ai-item';
                div.innerHTML = `
                    <p><span class="label">"${escapeHtml(item.keyword)}"</span> → Add to: ${escapeHtml(item.where_to_add)}</p>
                    <p style="margin-top: 6px; color: var(--gray-500);">${escapeHtml(item.how_to_add)}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Rewrite Suggestions
        if (suggestions.rewrite_suggestions && suggestions.rewrite_suggestions.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>Section rewrite suggestions</h3>`;
            suggestions.rewrite_suggestions.forEach(item => {
                const div = document.createElement('div');
                div.className = 'ai-item';
                div.innerHTML = `
                    <p><span class="label">${escapeHtml(item.section)}:</span> ${escapeHtml(item.current_issue)}</p>
                    <p style="margin-top: 6px; color: var(--primary);">→ ${escapeHtml(item.suggested_approach)}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Quick wins are not repeated here: they are the "Start with these
        // improvements" card at the top of the report.
        if (!container.children.length) {
            container.innerHTML = '<p class="no-keywords">No extra suggestions for this scan. Start with the improvements at the top of the report.</p>';
        }
    }

    function renderCoverLetterPoints(suggestions) {
        const card = document.getElementById('coverLetterCard');
        const container = document.getElementById('coverLetterPoints');
        const copyBtn = document.getElementById('copyCoverLetterBtn');
        if (!card || !container) return;

        const points = (suggestions && suggestions.cover_letter_points) || [];
        if (!points.length) {
            card.style.display = 'none';
            return;
        }

        card.style.display = 'block';
        container.innerHTML = points.map((point, i) => `
            <div class="cover-point">
                <span class="cover-point-num">${i + 1}</span>
                <p class="cover-point-text">${escapeHtml(point)}</p>
            </div>
        `).join('');

        // Copy handler
        if (copyBtn) {
            copyBtn.onclick = function () {
                const text = points.map((p, i) => `${i + 1}. ${p}`).join('\n\n');
                const fullText = 'Cover Letter Key Points (from ResumeRadar)\n' + '='.repeat(45) + '\n\n' + text;
                navigator.clipboard.writeText(fullText).then(() => {
                    showToast('Cover letter points copied!');
                }).catch(() => {
                    showToast('Could not copy. Try selecting the text manually', true);
                });
            };
        }
    }

    // ============================================================
    // COVER LETTER GENERATOR
    // ============================================================
    (function initCoverLetterGenerator() {
        const btn = document.getElementById('generateCoverLetterBtn');
        if (!btn) return;

        btn.addEventListener('click', async () => {
            const output = document.getElementById('coverLetterOutput');
            const loading = document.getElementById('coverLetterLoading');
            const errorDiv = document.getElementById('coverLetterError');
            const body = document.getElementById('coverLetterBody');

            // Get CV text from last scan data, job description from form
            const resumeText = lastScanData && lastScanData.resume_text;
            const jobDesc = document.getElementById('jobDescription') && document.getElementById('jobDescription').value.trim();

            if (!resumeText || !jobDesc) {
                errorDiv.textContent = 'Please complete a scan first so we have your CV and job description.';
                errorDiv.style.display = 'block';
                return;
            }

            // Show loading, hide others
            btn.disabled = true;
            btn.querySelector('.cl-btn-text').textContent = 'Writing...';
            loading.style.display = 'flex';
            output.style.display = 'none';
            errorDiv.style.display = 'none';
            trackEvent('cover_letter_started');

            try {
                const resp = await fetch('/api/generate/cover-letter', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resume_text: resumeText, job_description: jobDesc }),
                });

                const data = await resp.json();

                if (!resp.ok || data.error) {
                    const msg = data.error || 'Something went wrong. Please try again.';
                    if (resp.status === 429) {
                        errorDiv.textContent = 'Daily limit reached (3/day). Try again tomorrow!';
                    } else {
                        errorDiv.textContent = msg;
                    }
                    errorDiv.style.display = 'block';
                    return;
                }

                // Render cover letter — escape BEFORE converting newlines to markup
                body.innerHTML = escapeHtml(data.cover_letter).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
                body.innerHTML = '<p>' + body.innerHTML + '</p>';
                output.style.display = 'block';

                // Copy handler
                document.getElementById('copyCoverLetterFull').onclick = () => {
                    const text = body.innerText;
                    navigator.clipboard.writeText(text).then(() => {
                        showToast('Cover letter copied!');
                    }).catch(() => {
                        showToast('Could not copy. Try selecting the text manually', true);
                    });
                };

                // Download handler
                document.getElementById('downloadCoverLetterTxt').onclick = () => {
                    const text = body.innerText;
                    const blob = new Blob([text], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'cover-letter.txt';
                    a.click();
                    URL.revokeObjectURL(url);
                    showToast('Cover letter downloaded!');
                };
            } catch (err) {
                errorDiv.textContent = 'Network error. Please check your connection and try again.';
                errorDiv.style.display = 'block';
            } finally {
                loading.style.display = 'none';
                btn.disabled = false;
                btn.querySelector('.cl-btn-text').textContent = 'Write a first draft';
            }
        });
    })();

    function renderATSFormatting(ats) {
        const container = document.getElementById('atsFormatting');
        container.innerHTML = '';

        // Contact info check
        const contactInfo = ats.has_contact_info;
        const contactDiv = document.createElement('div');
        contactDiv.className = 'contact-check';
        contactDiv.innerHTML = `
            <span class="contact-item ${contactInfo.email ? 'found' : 'missing'}">
                ${contactInfo.email ? '✅' : '❌'} Email
            </span>
            <span class="contact-item ${contactInfo.phone ? 'found' : 'missing'}">
                ${contactInfo.phone ? '✅' : '❌'} Phone
            </span>
            <span class="contact-item ${contactInfo.linkedin ? 'found' : 'missing'}">
                ${contactInfo.linkedin ? '✅' : '❌'} LinkedIn
            </span>
        `;
        container.appendChild(contactDiv);

        // Issues
        if (ats.issues && ats.issues.length > 0) {
            ats.issues.forEach(issue => {
                const icons = { critical: '🚫', warning: '⚠️', info: 'ℹ️' };
                const div = document.createElement('div');
                div.className = `ats-issue ${issue.type}`;
                div.innerHTML = `
                    <span class="ats-issue-icon">${icons[issue.type] || 'ℹ️'}</span>
                    <div class="ats-issue-content">
                        <div class="ats-issue-title">${escapeHtml(issue.message)}</div>
                        <div class="ats-issue-detail">${escapeHtml(issue.detail)}</div>
                    </div>
                `;
                container.appendChild(div);
            });
        } else {
            const success = document.createElement('div');
            success.className = 'ats-issue success';
            success.innerHTML = `
                <span class="ats-issue-icon">✅</span>
                <div class="ats-issue-content">
                    <div class="ats-issue-title">No major ATS formatting issues detected</div>
                    <div class="ats-issue-detail">Your CV structure looks good for ATS systems.</div>
                </div>
            `;
            container.appendChild(success);
        }

        // Tips
        if (ats.tips && ats.tips.length > 0) {
            const tipsDiv = document.createElement('div');
            tipsDiv.className = 'ats-tips';
            tipsDiv.innerHTML = `
                <h3>Tips</h3>
                ${ats.tips.map(t => `<div class="ats-tip">${escapeHtml(t)}</div>`).join('')}
            `;
            container.appendChild(tipsDiv);
        }
    }

    // ============================================================
    // SCAN HISTORY (localStorage)
    // ============================================================
    const HISTORY_KEY = 'resumeradar_scan_history';
    const MAX_HISTORY = 20;

    function saveScanToHistory(data) {
        try {
            const history = getScanHistory();
            if (history.some(entry => entry.id === currentScanId)) return;

            // Label the entry with the job title: the first line of the job description.
            const jdEl = document.getElementById('jobDescription');
            const jdSnippet = ResumeRadarScan.jobTitle(jdEl ? jdEl.value : '');

            const entry = {
                id: currentScanId,
                jobKey: activeJobKey,
                scoreVersion: data.score_version || '2',
                date: new Date().toISOString(),
                score: Number.isFinite(data.match_score) ? Math.round(data.match_score) : null,
                matched: data.total_matched,
                missing: data.total_missing,
                total: data.total_job_keywords,
                jdSnippet: jdSnippet,
            };

            history.unshift(entry); // newest first
            if (history.length > MAX_HISTORY) history.length = MAX_HISTORY;
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {
            // localStorage might be full or disabled — silently ignore
        }
    }

    function getScanHistory() {
        try {
            const entries = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
            return Array.isArray(entries) ? entries.filter(entry => entry && typeof entry.jdSnippet === 'string') : [];
        } catch (e) {
            return [];
        }
    }

    function renderScanHistory() {
        const card = document.getElementById('scanHistoryCard');
        const chart = document.getElementById('historyChart');
        const list = document.getElementById('historyList');
        const clearBtn = document.getElementById('clearHistoryBtn');
        if (!card || !chart || !list) return;

        const history = getScanHistory();

        if (history.length < 2) {
            // Need at least 2 scans to show progress
            card.style.display = 'none';
            return;
        }

        card.style.display = 'block';

        // --- Mini bar chart (last 10 scans, oldest to newest) ---
        const latest = history[0];
        const chartData = history.filter(entry => ResumeRadarScan.scoreDelta(latest, entry) !== null).slice(0, 10).reverse();
        const maxScore = 100;
        chart.innerHTML = `
            <p class="history-chart-title">This job: ${escapeHtml(ResumeRadarScan.jobTitle(latest.jdSnippet))}</p>
            <div class="history-bars">
                ${chartData.map((entry, i) => {
                    const height = Math.max(4, (entry.score / maxScore) * 100);
                    let barColor = entry.score >= 75 ? 'var(--success)' : entry.score >= 50 ? 'var(--warning)' : 'var(--danger)';
                    const isLatest = i === chartData.length - 1;
                    return `
                        <div class="history-bar-wrap ${isLatest ? 'latest' : ''}" title="${entry.score}%, ${new Date(entry.date).toLocaleDateString()}">
                            <span class="history-bar-score">${entry.score}%</span>
                            <div class="history-bar" style="height: ${height}%; background: ${barColor};"></div>
                        </div>
                    `;
                }).join('')}
            </div>
            ${_trendIndicator(chartData)}
        `;

        // --- History list (last 5) ---
        const recent = history.slice(0, 5);
        list.innerHTML = '<p class="history-list-title">Recent scans, all jobs</p>' + recent.map((entry, i) => {
            const date = new Date(entry.date);
            const timeStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' at ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            const snippet = ResumeRadarScan.jobTitle(entry.jdSnippet);
            let scoreColor = entry.score >= 75 ? 'var(--success)' : entry.score >= 50 ? 'var(--warning)' : 'var(--danger)';

            let delta = '';
            const previous = history.slice(history.indexOf(entry) + 1).find(other => ResumeRadarScan.scoreDelta(entry, other) !== null);
            const diff = ResumeRadarScan.scoreDelta(entry, previous);
            if (diff > 0) delta = `<span class="history-delta positive">+${diff} points</span>`;
            else if (diff < 0) delta = `<span class="history-delta negative">${diff} points</span>`;

            return `
                <div class="history-entry">
                    <div class="history-entry-score" style="color: ${scoreColor};">${ResumeRadarScan.scoreText(entry.score)} ${delta}</div>
                    <div class="history-entry-detail">
                        <span class="history-entry-snippet">${escapeHtml(snippet)}</span>
                        <span class="history-entry-time">${timeStr}</span>
                    </div>
                </div>
            `;
        }).join('');

        // Clear button handler
        if (clearBtn) {
            clearBtn.onclick = function () {
                localStorage.removeItem(HISTORY_KEY);
                card.style.display = 'none';
                showToast('Scan history cleared');
            };
        }
    }

    function _trendIndicator(chartData) {
        if (chartData.length < 2) return '<p class="history-trend neutral">Scan a revision against the same job to compare keyword coverage.</p>';
        const first = chartData[0].score;
        const last = chartData[chartData.length - 1].score;
        const diff = last - first;
        if (diff > 5) return `<div class="history-trend positive">Up ${diff} points across revisions for this job.</div>`;
        if (diff < -5) return `<div class="history-trend negative">Down ${Math.abs(diff)} points for this job. Review the changes before adding any claims.</div>`;
        return `<div class="history-trend neutral">Score is holding steady. Check the missing keywords for your next edit.</div>`;
    }

    // ============================================================
    // HELPERS
    // ============================================================
    // Waiting state: a progress panel takes the place of the form. The steps
    // tick off on a timer (the server sends one answer, not progress events).
    const PROGRESS_STEP_DELAYS = [0, 2000, 5000];
    const SLOW_SCAN_AFTER = 25000;
    const PROGRESS_NOTE = 'Usually about 20 seconds.';
    let loadingTimers = [];

    function setProgressStep(active) {
        scanProgress.querySelectorAll('.scan-progress-steps li').forEach((li, i) => {
            li.classList.toggle('done', i < active);
            li.classList.toggle('active', i === active);
        });
    }

    function setLoading(loading) {
        scanBtn.disabled = loading;
        scanForm.classList.toggle('is-scanning', loading);
        loadingTimers.forEach(t => clearTimeout(t));
        loadingTimers = [];
        if (!scanProgress) return;
        scanProgress.hidden = !loading;
        const note = document.getElementById('scanProgressNote');
        note.textContent = PROGRESS_NOTE;
        if (!loading) return;
        PROGRESS_STEP_DELAYS.forEach((delay, i) => {
            loadingTimers.push(setTimeout(() => setProgressStep(i), delay));
        });
        loadingTimers.push(setTimeout(() => {
            note.textContent = 'This is taking longer than usual. Still working on it.';
        }, SLOW_SCAN_AFTER));
        // A short wait, so a scan that fails at once never starts this smooth scroll:
        // it would carry on after the error message has been focused and scroll it away.
        loadingTimers.push(setTimeout(() => {
            scanProgress.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 150));
    }

    // Put text into a live region a moment after it is shown, so screen readers
    // notice the change even when the region has just been unhidden.
    function announce(region, msg) {
        if (!region) return;
        region.textContent = '';
        setTimeout(() => { region.textContent = msg; }, 50);
    }

    // focusEl: the field the error is about. Without one, focus moves to the message
    // itself, because a disabled Scan button has usually dropped focus to the page.
    function showError(msg, focusEl) {
        uploadError.hidden = true;
        errorMessage.style.display = 'block';
        if (focusEl) {
            announce(errorMessage, msg);
            focusEl.focus();
        } else {
            // Moving focus to the message reads it, so fill it in before focusing.
            errorMessage.textContent = msg;
            // An instant scroll first, so a smooth scroll still running from the
            // progress panel can't carry the message off screen after it is focused.
            errorMessage.scrollIntoView({ block: 'center', behavior: 'instant' });
            errorMessage.focus({ preventScroll: true });
        }
    }

    // Errors about the CV file sit beside the upload box, not below the Scan button.
    function showUploadError(msg, focusEl) {
        errorMessage.style.display = 'none';
        uploadError.hidden = false;
        announce(uploadError, msg);
        if (focusEl) focusEl.focus();
    }

    function hideError() {
        errorMessage.style.display = 'none';
        uploadError.hidden = true;
    }
});


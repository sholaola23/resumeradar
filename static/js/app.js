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

document.addEventListener('DOMContentLoaded', () => {
    // ============================================================
    // DOM ELEMENTS
    // ============================================================
    const scanForm = document.getElementById('scanForm');
    const scanBtn = document.getElementById('scanBtn');
    const scanBtnText = document.querySelector('.scan-btn-text');
    const scanBtnLoading = document.querySelector('.scan-btn-loading');
    const errorMessage = document.getElementById('errorMessage');
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

    // Store the last scan data for report generation
    let lastScanData = null;

    // ============================================================
    // SOCIAL PROOF COUNTER
    // ============================================================
    const socialProof = document.getElementById('socialProof');
    const scanCountEl = document.getElementById('scanCount');

    (async function loadScanCount() {
        try {
            const resp = await fetch('/api/scan-count');
            const data = await resp.json();
            const count = data.count || 0;
            const velocity = data.velocity || 0;
            if (count >= 10 && socialProof && scanCountEl) {
                // Milestone-aware copy
                const num = count.toLocaleString();
                let text = `${num}+ resumes scanned`;
                if (count >= 1000) text = `${num}+ resumes scanned — join the movement`;
                else if (count >= 750) text = `${num}+ job seekers have scanned their resumes`;
                else if (count >= 500) text = `${num}+ resumes scanned and counting`;
                else if (count >= 250) text = `${num}+ resumes scanned — are you next?`;

                scanCountEl.textContent = text;

                // Show velocity badge when traffic is active
                const velocityEl = document.getElementById('scanVelocity');
                if (velocity >= 5 && velocityEl) {
                    velocityEl.textContent = `${velocity} scans this hour`;
                    velocityEl.style.display = 'inline';
                }

                socialProof.style.display = 'block';
            }
        } catch (e) {
            // Silently fail — social proof is non-critical
        }
    })();

    // Newsletter popup elements
    const newsletterPopup = document.getElementById('newsletterPopup');
    const newsletterForm = document.getElementById('newsletterForm');
    const newsletterEmail = document.getElementById('newsletterEmail');
    const newsletterFirstName = document.getElementById('newsletterFirstName');

    // Track if user has already subscribed this session
    let hasSubscribed = sessionStorage.getItem('resumeradar_subscribed') === 'true';

    // ============================================================
    // NEWSLETTER POPUP (MANDATORY)
    // ============================================================

    function showNewsletterPopup(data) {
        if (!newsletterPopup) {
            renderResults(data);
            return;
        }

        // Show score preview in the popup header
        const score = data.match_score || 0;
        const scorePreview = document.getElementById('scorePreview');
        const scorePreviewNumber = document.getElementById('scorePreviewNumber');
        const scorePreviewFill = document.getElementById('scorePreviewFill');

        if (scorePreview && scorePreviewNumber && scorePreviewFill) {
            // Set score text
            scorePreviewNumber.textContent = `${score}%`;

            // Animate the circle fill
            const circumference = 226.195; // 2 * π * 36
            const offset = circumference - (score / 100) * circumference;
            scorePreviewFill.style.strokeDashoffset = circumference; // reset
            scorePreview.style.display = 'block';

            // Color based on score
            let color = '#dc2626';
            if (score >= 75) color = '#059669';
            else if (score >= 50) color = '#d97706';
            scorePreviewFill.style.stroke = color;

            // Animate after a brief delay
            setTimeout(() => {
                scorePreviewFill.style.strokeDashoffset = offset;
            }, 300);
        }

        // Update heading to include score context
        if (newsletterHeading) {
            newsletterHeading.textContent = `Your score: ${score}%`;
        }
        if (newsletterSubtitle) {
            newsletterSubtitle.textContent = 'Subscribe to Shola\'s Tech Notes to unlock your full report — missing keywords, AI suggestions, and ATS fixes. Plus get weekly tech career tips in just 3 minutes.';
        }

        newsletterPopup.style.display = 'flex';
        if (newsletterFirstName) newsletterFirstName.focus();
    }

    // Post-subscribe confirmation elements
    const newsletterFormWrapper = document.getElementById('newsletterFormWrapper');
    const newsletterConfirmation = document.getElementById('newsletterConfirmation');
    const confirmName = document.getElementById('confirmName');
    const viewResultsBtn = document.getElementById('viewResultsBtn');
    const newsletterHeading = document.getElementById('newsletterHeading');
    const newsletterSubtitle = document.getElementById('newsletterSubtitle');

    function showNewsletterConfirmation(firstName) {
        // Hide the form, show the confirmation
        if (newsletterFormWrapper) newsletterFormWrapper.style.display = 'none';
        if (newsletterConfirmation) {
            newsletterConfirmation.style.display = 'block';
            if (confirmName) confirmName.textContent = firstName;
        }
        // Update header text to post-subscribe message
        if (newsletterHeading) newsletterHeading.textContent = "You're subscribed! 🎉";
        if (newsletterSubtitle) newsletterSubtitle.textContent = "Welcome to Shola's Tech Notes — you'll get practical tech career tips, certification guides, and AI fundamentals in just 3 minutes a week.";

        hasSubscribed = true;
        sessionStorage.setItem('resumeradar_subscribed', 'true');
    }

    function closeNewsletterAfterSubscribe() {
        if (newsletterPopup) newsletterPopup.style.display = 'none';

        // Reset the popup to form state for next time (shouldn't happen since we track session)
        if (newsletterFormWrapper) newsletterFormWrapper.style.display = 'block';
        if (newsletterConfirmation) newsletterConfirmation.style.display = 'none';

        // Now show the results
        if (lastScanData) {
            renderResults(lastScanData);
        }
    }

    // "View My Results" button on confirmation screen
    if (viewResultsBtn) {
        viewResultsBtn.addEventListener('click', () => {
            closeNewsletterAfterSubscribe();
        });
    }

    // NO backdrop close — subscription is mandatory
    // NO skip button — subscription is mandatory
    // NO close button — subscription is mandatory

    // Newsletter form submission
    if (newsletterForm) {
        newsletterForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const firstName = newsletterFirstName ? newsletterFirstName.value.trim() : '';
            const email = newsletterEmail ? newsletterEmail.value.trim() : '';

            // Validate first name
            if (!firstName) {
                if (newsletterFirstName) {
                    newsletterFirstName.style.borderColor = '#dc2626';
                    newsletterFirstName.focus();
                }
                return;
            }

            // Validate email
            if (!email || !email.includes('@')) {
                if (newsletterEmail) {
                    newsletterEmail.style.borderColor = '#dc2626';
                    newsletterEmail.focus();
                }
                return;
            }

            // Reset border colors
            if (newsletterFirstName) newsletterFirstName.style.borderColor = '';
            if (newsletterEmail) newsletterEmail.style.borderColor = '';

            const submitBtn = newsletterForm.querySelector('.newsletter-submit-btn');
            const btnText = submitBtn ? submitBtn.querySelector('.nl-btn-text') : null;
            const btnLoading = submitBtn ? submitBtn.querySelector('.nl-btn-loading') : null;

            if (btnText) btnText.style.display = 'none';
            if (btnLoading) btnLoading.style.display = 'inline';
            if (submitBtn) submitBtn.disabled = true;

            try {
                // Subscribe via our backend (which calls Beehiiv API)
                // Thread incoming UTM source so Beehiiv tracks where this subscriber came from
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

                // Show the confirmation screen with email tip
                showNewsletterConfirmation(firstName);

            } catch (err) {
                console.error('Newsletter signup error:', err);
                // Fallback: open the newsletter page directly
                window.open('https://www.sholastechnotes.com/', '_blank');
                showToast('Opening newsletter page — subscribe there to see results.');
                closeNewsletterAfterSubscribe();
            } finally {
                if (btnText) btnText.style.display = 'inline';
                if (btnLoading) btnLoading.style.display = 'none';
                if (submitBtn) submitBtn.disabled = false;
            }
        });
    }

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
            showError('Please upload a PDF or DOCX file.');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            showError('File too large. Maximum size is 5MB.');
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
            showError('Please paste a job description.');
            return;
        }

        if (activeTab === 'upload' && !hasFile) {
            showError('Please upload your resume file, or switch to the "Paste Text" tab.');
            return;
        }

        if (activeTab === 'paste' && !resumeText) {
            showError('Please paste your resume text.');
            return;
        }

        // Show loading state
        setLoading(true);

        try {
            const formData = new FormData();
            formData.append('job_description', jobDescription);

            if (activeTab === 'upload' && hasFile) {
                formData.append('resume_file', resumeFile.files[0]);
            } else if (activeTab === 'paste' && resumeText) {
                formData.append('resume_text', resumeText);
            }

            const response = await fetch('/api/scan', {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (!response.ok || data.error) {
                showError(data.error || 'Something went wrong. Please try again.');
                setLoading(false);
                return;
            }

            // Store data for report generation
            lastScanData = data;

            // Update social proof counter after successful scan
            if (socialProof && scanCountEl) {
                try {
                    const countResp = await fetch('/api/scan-count');
                    const countData = await countResp.json();
                    const newCount = countData.count || 0;
                    if (newCount >= 10) {
                        scanCountEl.textContent = newCount.toLocaleString() + '+';
                        socialProof.style.display = 'block';
                    }
                } catch (e) { /* non-critical */ }
            }

            // Show newsletter popup before results (mandatory, but only once per session)
            if (!hasSubscribed && newsletterPopup) {
                showNewsletterPopup(data);
            } else {
                renderResults(data);
            }

        } catch (err) {
            console.error('Scan error:', err);
            showError('Could not connect to the server. Please make sure the app is running and try again.');
        } finally {
            setLoading(false);
        }
    });

    // Scan Again button — clear everything so user starts fresh
    scanAgainBtn.addEventListener('click', () => {
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

    // ============================================================
    // DEMO SCAN — "Try a demo scan" feature
    // ============================================================
    const demoScanBtn = document.getElementById('demoScanBtn');

    const DEMO_RESUME = `JAMIE SMITH
London, UK | jamie.smith@example.com | +44 7700 900123 | linkedin.com/in/jamiesmith-demo

PROFESSIONAL SUMMARY
Cloud Engineer with 4 years of experience designing and deploying scalable infrastructure on AWS. Skilled in CI/CD pipelines, infrastructure as code, and container orchestration. Passionate about automation, cost optimisation, and building reliable cloud-native systems.

EXPERIENCE

Cloud Engineer | TechStream Solutions | Jan 2022 - Present
- Designed and deployed AWS infrastructure using Terraform across 3 production environments
- Built CI/CD pipelines with GitHub Actions reducing deployment time by 60%
- Managed Kubernetes clusters on EKS serving 2M+ daily requests
- Implemented CloudWatch monitoring and alerting, reducing incident response time by 45%
- Led migration of 12 legacy applications to containerised microservices on Docker

Junior Cloud Engineer | DataFlow Inc | Jun 2020 - Dec 2021
- Provisioned and maintained EC2, S3, RDS, and Lambda resources for development teams
- Automated routine tasks using Python and Bash scripting, saving 15 hours per week
- Assisted in achieving SOC 2 compliance by implementing IAM best practices
- Created CloudFormation templates for repeatable environment deployments

EDUCATION
BSc Computer Science | University of Manchester | 2020

SKILLS
AWS (EC2, S3, RDS, Lambda, EKS, CloudWatch, IAM, VPC, CloudFormation)
Terraform, Docker, Kubernetes, GitHub Actions, Linux, Python, Bash
CI/CD, Infrastructure as Code, Monitoring, Agile

CERTIFICATIONS
AWS Solutions Architect Associate
AWS Cloud Practitioner`;

    const DEMO_JOB = `Senior Cloud Engineer

About the Role
We are looking for a Senior Cloud Engineer to join our Platform team and help scale our cloud infrastructure. You will design, build, and maintain reliable, secure, and cost-effective cloud solutions on AWS.

Responsibilities
- Design and implement scalable, highly available cloud architectures on AWS
- Build and maintain CI/CD pipelines for automated deployments
- Manage container orchestration using Kubernetes and Docker
- Implement infrastructure as code using Terraform and CloudFormation
- Monitor system performance and optimise for cost and reliability
- Collaborate with development teams to improve deployment workflows
- Implement security best practices including IAM policies, VPC networking, and encryption
- Participate in on-call rotation and incident response
- Mentor junior engineers and contribute to engineering standards

Requirements
- 5+ years of experience in cloud engineering or DevOps
- Strong expertise with AWS services (EC2, S3, RDS, Lambda, EKS, CloudFront, Route 53, DynamoDB)
- Proficiency in Infrastructure as Code (Terraform, CloudFormation, or Pulumi)
- Experience with container technologies (Docker, Kubernetes, ECS)
- Strong scripting skills (Python, Bash, or Go)
- Experience with CI/CD tools (Jenkins, GitHub Actions, GitLab CI, or CircleCI)
- Knowledge of monitoring and observability tools (CloudWatch, Datadog, Prometheus, Grafana)
- Understanding of networking concepts (VPC, DNS, load balancing, CDN)
- Excellent communication and collaboration skills
- Problem-solving mindset with attention to detail

Nice to Have
- AWS Solutions Architect Professional certification
- Experience with serverless architectures
- Knowledge of security frameworks (SOC 2, ISO 27001)
- Experience with cost optimisation and FinOps practices
- Familiarity with Ansible or other configuration management tools`;

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

            // 2. Fill in the sample resume and job description
            const resumeTextarea = document.getElementById('resumeText');
            const jobTextarea = document.getElementById('jobDescription');

            if (resumeTextarea) resumeTextarea.value = DEMO_RESUME;
            if (jobTextarea) jobTextarea.value = DEMO_JOB;

            // 3. Clear any uploaded file (in case they had one)
            if (resumeFile) resumeFile.value = '';
            if (fileSelected) fileSelected.style.display = 'none';
            if (dropZone) dropZone.style.display = 'block';

            // 4. Scroll up to the form so they see it filled in
            scanForm.scrollIntoView({ behavior: 'smooth', block: 'start' });

            // 5. Brief visual pulse on the scan button to draw attention
            scanBtn.classList.add('pulse-hint');
            setTimeout(() => scanBtn.classList.remove('pulse-hint'), 1500);
        });
    }

    // ============================================================
    // SHARE BUTTONS (UTM-tracked)
    // ============================================================
    const shareLinkedIn = document.getElementById('shareLinkedIn');
    const shareWhatsApp = document.getElementById('shareWhatsApp');
    const shareCopyLink = document.getElementById('shareCopyLink');
    const baseSiteUrl = 'https://resumeradar.sholastechnotes.com';

    /**
     * Build a share URL with UTM parameters for tracking in Beehiiv.
     * @param {string} source - e.g. 'linkedin', 'twitter', 'whatsapp', 'copy'
     * @param {string} campaign - e.g. 'user_share', 'post_subscribe'
     */
    function getShareUrl(source, campaign) {
        campaign = campaign || 'user_share';
        const score = lastScanData ? lastScanData.match_score : 0;
        const tier = score >= 70 ? 'high' : score >= 45 ? 'mid' : 'low';
        const params = new URLSearchParams({
            utm_source: source,
            utm_medium: 'social',
            utm_campaign: campaign,
            score_tier: tier,
        });
        return `${baseSiteUrl}?${params.toString()}`;
    }

    /**
     * Get score-tiered share text — works for job seekers AND curious users.
     * @param {string} platform - 'linkedin', 'whatsapp', or other
     */
    function getShareText(platform) {
        const score = lastScanData ? Math.round(lastScanData.match_score) : 0;
        const missing = lastScanData ? lastScanData.total_missing : 0;

        if (!score) {
            return platform === 'linkedin'
                ? 'Free tool that scans your resume against job descriptions and shows your ATS match score. Interesting to see what keywords you might be missing.'
                : 'Free tool that shows your ATS resume match score — interesting to see what keywords you might be missing 📡';
        }

        if (score >= 70) {
            return platform === 'linkedin'
                ? `Just scored ${score}% on ResumeRadar's ATS scanner. Useful free tool if you want to check how your resume stacks up against any job description.`
                : `Scored ${score}% on ResumeRadar 📡 Free ATS resume scanner — check how yours stacks up.`;
        } else if (score >= 45) {
            return platform === 'linkedin'
                ? `Scored ${score}% on an ATS resume scanner. Interesting to see the ${missing} keywords I was missing that hiring systems actually look for. Free tool worth checking.`
                : `${score}% ATS match — found ${missing} keywords I was missing 📡 Free resume scanner worth checking out.`;
        } else {
            return platform === 'linkedin'
                ? `I just found out my resume only matches ${score}% of what ATS systems look for. This free tool shows exactly what's missing — wish I'd used it earlier.`
                : `My resume only matches ${score}% of ATS keywords 😅 This free scanner shows exactly what to fix 📡`;
        }
    }

    if (shareLinkedIn) {
        shareLinkedIn.addEventListener('click', () => {
            const shareUrl = getShareUrl('linkedin');
            const text = getShareText('linkedin');
            const url = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}&summary=${encodeURIComponent(text)}`;
            window.open(url, '_blank', 'width=600,height=500');
        });
    }

    if (shareWhatsApp) {
        shareWhatsApp.addEventListener('click', () => {
            const shareUrl = getShareUrl('whatsapp');
            const text = getShareText('whatsapp') + '\n\n' + shareUrl;
            const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
            window.open(url, '_blank', 'width=600,height=500');
        });
    }

    if (shareCopyLink) {
        shareCopyLink.addEventListener('click', async () => {
            const shareUrl = getShareUrl('copy');
            try {
                await navigator.clipboard.writeText(shareUrl);
                showToast('Link copied! Share it with someone who could use it.');
            } catch (e) {
                const textarea = document.createElement('textarea');
                textarea.value = shareUrl;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                showToast('Link copied! Share it with someone who could use it.');
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
        report.push('  RESUMERADAR — ATS SCAN REPORT');
        report.push('  Beat the scan. Land the interview.');
        report.push('═══════════════════════════════════════════');
        report.push(`  Generated: ${now}`);
        report.push('');

        // Score
        report.push('───────────────────────────────────────────');
        report.push(`  ATS MATCH SCORE: ${data.match_score}%`);
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
            if (info.total > 0) {
                report.push(`  ${catLabels[key] || key}: ${Math.round(info.score)}% (${info.matched}/${info.total})`);
            }
        }
        report.push('');

        // Missing Keywords
        const missingEntries = Object.entries(data.missing_keywords || {}).filter(([, v]) => v && v.length > 0);
        if (missingEntries.length > 0) {
            report.push('───────────────────────────────────────────');
            report.push('  KEYWORDS NOT FOUND ON YOUR RESUME');
            report.push('  (Already have these? Add them. Don\'t? Consider learning them.)');
            report.push('───────────────────────────────────────────');
            for (const [cat, words] of missingEntries) {
                report.push(`  ${catLabels[cat] || cat}: ${words.join(', ')}`);
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
                report.push(`  ${catLabels[cat] || cat}: ${words.join(', ')}`);
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
                throw new Error('PDF generation failed');
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
            showToast('Failed to generate PDF. Downloading text version...', true);

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
    emailReportBtn.addEventListener('click', () => {
        emailModal.style.display = 'flex';
        emailInput.value = '';
        emailInput.focus();
    });

    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);

    // Close modal on backdrop click
    emailModal.addEventListener('click', (e) => {
        if (e.target === emailModal) closeModal();
    });

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && emailModal.style.display === 'flex') {
            closeModal();
        }
    });

    function closeModal() {
        emailModal.style.display = 'none';
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
            const response = await fetch('/api/email-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email,
                    scan_data: lastScanData,
                }),
            });

            const result = await response.json();

            if (!response.ok || result.error) {
                throw new Error(result.error || 'Failed to send email');
            }

            closeModal();
            showToast(`Report sent to ${email}!`);

        } catch (err) {
            console.error('Email send error:', err);

            // If the API isn't configured, fallback to mailto
            if (err.message.includes('not configured')) {
                showToast('Email service not set up yet. Opening email client...', true);
                const reportText = generateShortReport(lastScanData);
                const score = lastScanData.match_score;
                const subject = encodeURIComponent(`ResumeRadar Report — ATS Match Score: ${score}%`);
                const mailtoUrl = `mailto:${encodeURIComponent(email)}?subject=${subject}&body=${encodeURIComponent(reportText)}`;
                window.location.href = mailtoUrl;
                closeModal();
            } else {
                showToast(err.message || 'Failed to send email. Please try again.', true);
            }
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

        report.push('RESUMERADAR — ATS SCAN REPORT');
        report.push(`Generated: ${new Date().toLocaleDateString()}`);
        report.push('');
        report.push(`ATS MATCH SCORE: ${data.match_score}%`);
        report.push(`Keywords Matched: ${data.total_matched} | Missing: ${data.total_missing} | Total: ${data.total_job_keywords}`);
        report.push('');

        if (ai.summary) {
            report.push(sanitizeAIText(ai.summary));
            report.push('');
        }

        // Missing keywords (compact)
        const missing = Object.entries(data.missing_keywords || {})
            .filter(([, v]) => v && v.length > 0)
            .map(([, words]) => words.join(', '));
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
        report.push('Full report available at ResumeRadar');
        report.push('Built by Olushola Oladipupo');

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

        // 1. Score
        renderScore(data);

        // 2. Category Breakdown
        renderCategories(data.category_scores);

        // 3. Missing Keywords
        renderKeywords('missingKeywords', data.missing_keywords, 'missing');

        // 4. Matched Keywords
        renderKeywords('matchedKeywords', data.matched_keywords, 'matched');

        // 5. AI Suggestions
        renderAISuggestions(data.ai_suggestions);

        // 6. Cover Letter Key Points
        renderCoverLetterPoints(data.ai_suggestions);

        // 7. ATS Formatting
        renderATSFormatting(data.ats_formatting);

        // 8. Scan History
        saveScanToHistory(data);
        renderScanHistory();

        // Scroll to results
        setTimeout(() => {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
    }

    function renderScore(data) {
        const score = data.match_score;
        const scoreNumber = document.getElementById('scoreNumber');
        const scoreFill = document.getElementById('scoreFill');
        const scoreSummary = document.getElementById('scoreSummary');
        const scoreStats = document.getElementById('scoreStats');

        // Reset circle for re-scans
        scoreFill.style.strokeDashoffset = 339.292;

        // Animate score number
        animateNumber(scoreNumber, score);

        // Animate circle
        const circumference = 339.292;
        const offset = circumference - (score / 100) * circumference;
        setTimeout(() => {
            scoreFill.style.strokeDashoffset = offset;
        }, 100);

        // Color based on score
        let color;
        if (score >= 75) color = '#059669';
        else if (score >= 50) color = '#d97706';
        else color = '#dc2626';
        scoreFill.style.stroke = color;

        // Summary text
        let summaryText = '';
        if (data.ai_suggestions && data.ai_suggestions.summary) {
            summaryText = sanitizeAIText(data.ai_suggestions.summary);
        }
        // Fallback if AI summary is empty or was all artifacts
        if (!summaryText) {
            if (score >= 75) {
                summaryText = "Strong match! Your resume aligns well with this job description. A few targeted tweaks could push you even higher.";
            } else if (score >= 50) {
                summaryText = "Decent foundation, but there are noticeable gaps. Focus on adding the missing technical keywords and you'll see a significant jump.";
            } else {
                summaryText = "Your resume needs significant optimization for this role. Don't worry — the suggestions below will show you exactly what to add and change.";
            }
        }
        scoreSummary.innerHTML = `<p>${summaryText}</p>`;

        // Stats boxes
        scoreStats.innerHTML = `
            <div class="stat-box">
                <span class="stat-number">${data.total_matched}</span>
                <span class="stat-label">Keywords Matched</span>
            </div>
            <div class="stat-box">
                <span class="stat-number">${data.total_missing}</span>
                <span class="stat-label">Keywords Missing</span>
            </div>
            <div class="stat-box">
                <span class="stat-number">${data.total_job_keywords}</span>
                <span class="stat-label">Total Job Keywords</span>
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

        // Determine fit tier and messaging
        let tier, tierColor, tierBg, tierIcon, tierMsg;
        if (score >= 75) {
            tier = 'Strong Fit';
            tierColor = '#059669';
            tierBg = '#d1fae5';
            tierIcon = '🎯';
            tierMsg = 'Your skills closely match this role. Focus on tailoring your experience bullets and you\'re in great shape.';
        } else if (score >= 50) {
            tier = 'Good Fit';
            tierColor = '#d97706';
            tierBg = '#fef3c7';
            tierIcon = '👍';
            tierMsg = 'Solid foundation for this role. Adding the missing keywords to your resume could move you into the strong fit zone.';
        } else if (score >= 30) {
            tier = 'Stretch';
            tierColor = '#ea580c';
            tierBg = '#fff7ed';
            tierIcon = '🔄';
            tierMsg = 'This role is a stretch right now. You\'d need to close some skill gaps — check the missing keywords for your roadmap.';
        } else {
            tier = 'Long Shot';
            tierColor = '#dc2626';
            tierBg = '#fee2e2';
            tierIcon = '📈';
            tierMsg = 'Significant gaps for this role. Consider using the missing keywords as a learning path before applying.';
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
            <div class="fit-verdict-badge" style="background: ${tierBg}; color: ${tierColor};">
                <span class="fit-icon">${tierIcon}</span>
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

    function renderCategories(categories) {
        const container = document.getElementById('categoryBars');
        container.innerHTML = '';

        const labels = {
            technical_skills: '💻 Technical Skills',
            soft_skills: '🤝 Soft Skills',
            certifications: '📜 Certifications',
            education: '🎓 Education',
            action_verbs: '⚡ Action Verbs',
        };

        for (const [key, data] of Object.entries(categories)) {
            if (data.total === 0) continue;

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
                    ${words.map(w => `<span class="keyword-tag ${type}">${w}</span>`).join('')}
                </div>
            `;
            container.appendChild(section);
        }

        if (!hasAny) {
            container.innerHTML = `<p class="no-keywords">${
                type === 'missing'
                    ? 'No missing keywords detected — great job!'
                    : 'No keyword matches found.'
            }</p>`;
        }
    }

    function renderAISuggestions(suggestions) {
        const container = document.getElementById('aiSuggestions');
        const badge = document.getElementById('aiBadge');
        container.innerHTML = '';

        if (suggestions.ai_powered) {
            badge.textContent = '✨ AI-Powered Analysis';
            badge.className = 'ai-badge powered';
        } else {
            badge.textContent = '📊 Rule-Based Analysis';
            badge.className = 'ai-badge fallback';
        }

        if (suggestions.api_error) {
            const notice = document.createElement('div');
            notice.className = 'ai-item';
            notice.innerHTML = `<p style="color: var(--warning);">${suggestions.api_error}</p>`;
            container.appendChild(notice);
        }

        // Strengths
        if (suggestions.strengths && suggestions.strengths.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `
                <h3>💪 Your Strengths</h3>
                ${suggestions.strengths.map(s => `<div class="strength-item">${s}</div>`).join('')}
            `;
            container.appendChild(section);
        }

        // Critical Improvements
        if (suggestions.critical_improvements && suggestions.critical_improvements.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>🎯 Key Improvements</h3>`;
            suggestions.critical_improvements.forEach(item => {
                const priority = item.priority || 'medium';
                const div = document.createElement('div');
                div.className = `ai-item ${priority}-priority`;
                div.innerHTML = `
                    <p><span class="label">${item.section}:</span> ${item.issue}</p>
                    <p style="margin-top: 6px; color: var(--primary);">→ ${item.suggestion}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Keyword Suggestions
        if (suggestions.keyword_suggestions && suggestions.keyword_suggestions.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>🔑 How to Add These Keywords to Your Resume</h3>`;
            suggestions.keyword_suggestions.forEach(item => {
                const div = document.createElement('div');
                div.className = 'ai-item';
                div.innerHTML = `
                    <p><span class="label">"${item.keyword}"</span> → Add to: ${item.where_to_add}</p>
                    <p style="margin-top: 6px; color: var(--gray-500);">${item.how_to_add}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Rewrite Suggestions
        if (suggestions.rewrite_suggestions && suggestions.rewrite_suggestions.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `<h3>✏️ Section Rewrite Suggestions</h3>`;
            suggestions.rewrite_suggestions.forEach(item => {
                const div = document.createElement('div');
                div.className = 'ai-item';
                div.innerHTML = `
                    <p><span class="label">${item.section}:</span> ${item.current_issue}</p>
                    <p style="margin-top: 6px; color: var(--primary);">→ ${item.suggested_approach}</p>
                `;
                section.appendChild(div);
            });
            container.appendChild(section);
        }

        // Quick Wins
        if (suggestions.quick_wins && suggestions.quick_wins.length > 0) {
            const section = document.createElement('div');
            section.className = 'ai-section';
            section.innerHTML = `
                <h3>⚡ Quick Wins</h3>
                ${suggestions.quick_wins.map(w => `<div class="quick-win">${w}</div>`).join('')}
            `;
            container.appendChild(section);
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
                <p class="cover-point-text">${point}</p>
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
                    showToast('Could not copy — try selecting the text manually', true);
                });
            };
        }
    }

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
                        <div class="ats-issue-title">${issue.message}</div>
                        <div class="ats-issue-detail">${issue.detail}</div>
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
                    <div class="ats-issue-detail">Your resume structure looks good for ATS systems.</div>
                </div>
            `;
            container.appendChild(success);
        }

        // Tips
        if (ats.tips && ats.tips.length > 0) {
            const tipsDiv = document.createElement('div');
            tipsDiv.className = 'ats-tips';
            tipsDiv.innerHTML = `
                <h3>💡 Pro Tips</h3>
                ${ats.tips.map(t => `<div class="ats-tip">${t}</div>`).join('')}
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
            const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');

            // Extract first ~60 chars of job description for label
            const jdEl = document.getElementById('jobDescription');
            const jdSnippet = jdEl ? jdEl.value.trim().substring(0, 80).replace(/\s+/g, ' ') : 'Job scan';

            const entry = {
                id: Date.now(),
                date: new Date().toISOString(),
                score: Math.round(data.match_score),
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
            return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
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
        const chartData = history.slice(0, 10).reverse();
        const maxScore = 100;
        chart.innerHTML = `
            <div class="history-bars">
                ${chartData.map((entry, i) => {
                    const height = Math.max(4, (entry.score / maxScore) * 100);
                    let barColor = entry.score >= 75 ? 'var(--success)' : entry.score >= 50 ? 'var(--warning)' : 'var(--danger)';
                    const isLatest = i === chartData.length - 1;
                    return `
                        <div class="history-bar-wrap ${isLatest ? 'latest' : ''}" title="${entry.score}% — ${new Date(entry.date).toLocaleDateString()}">
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
        list.innerHTML = recent.map((entry, i) => {
            const date = new Date(entry.date);
            const timeStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' at ' + date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
            const snippet = entry.jdSnippet.length > 50 ? entry.jdSnippet.substring(0, 50) + '...' : entry.jdSnippet;
            let scoreColor = entry.score >= 75 ? 'var(--success)' : entry.score >= 50 ? 'var(--warning)' : 'var(--danger)';

            // Show delta from previous scan
            let delta = '';
            if (i < recent.length - 1) {
                const diff = entry.score - recent[i + 1].score;
                if (diff > 0) delta = `<span class="history-delta positive">+${diff}%</span>`;
                else if (diff < 0) delta = `<span class="history-delta negative">${diff}%</span>`;
            }

            return `
                <div class="history-entry">
                    <div class="history-entry-score" style="color: ${scoreColor};">${entry.score}% ${delta}</div>
                    <div class="history-entry-detail">
                        <span class="history-entry-snippet">${snippet}</span>
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
        if (chartData.length < 2) return '';
        const first = chartData[0].score;
        const last = chartData[chartData.length - 1].score;
        const diff = last - first;
        if (diff > 5) return `<div class="history-trend positive">📈 Up ${diff}% since your first scan — great progress!</div>`;
        if (diff < -5) return `<div class="history-trend negative">📉 Down ${Math.abs(diff)}% — try matching more keywords from the job description.</div>`;
        return `<div class="history-trend neutral">➡️ Score is holding steady. Check the missing keywords for your next optimization.</div>`;
    }

    // ============================================================
    // HELPERS
    // ============================================================
    function setLoading(loading) {
        scanBtn.disabled = loading;
        scanBtnText.style.display = loading ? 'none' : 'inline';
        scanBtnLoading.style.display = loading ? 'inline' : 'none';
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.style.display = 'block';
    }

    function hideError() {
        errorMessage.style.display = 'none';
    }
});

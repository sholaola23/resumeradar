/**
 * ResumeRadar — CV Builder Frontend
 * Handles form collection, dynamic entries, AI generation,
 * template picking, Stripe payment, post-scan auto-populate.
 */

(function () {
    'use strict';

    // ============================================================
    // STATE
    // ============================================================
    let currentToken = null;
    let currentPolished = null;
    let storageMode = 'server'; // 'server' (Redis) or 'client' (sessionStorage fallback)
    let lastTargetJD = ''; // Stores the last job description for form pre-populate

    // Loading message rotation
    const LOADING_MESSAGES = [
        'Analyzing the job description...',
        'Extracting your experience...',
        'Matching keywords to the role...',
        'Polishing your bullet points...',
        'Optimizing for ATS systems...',
        'Finalizing your CV...',
    ];
    let loadingInterval = null;
    let loadingMsgIndex = 0;

    function startLoadingRotation(el) {
        if (!el) return;
        loadingMsgIndex = 0;
        el.textContent = LOADING_MESSAGES[0];
        loadingInterval = setInterval(function () {
            loadingMsgIndex = (loadingMsgIndex + 1) % LOADING_MESSAGES.length;
            el.style.opacity = '0';
            setTimeout(function () {
                el.textContent = LOADING_MESSAGES[loadingMsgIndex];
                el.style.opacity = '1';
            }, 200);
        }, 2500);
    }

    function stopLoadingRotation() {
        if (loadingInterval) {
            clearInterval(loadingInterval);
            loadingInterval = null;
        }
    }

    // ============================================================
    // DOM REFERENCES
    // ============================================================
    const builderForm = document.getElementById('builderForm');
    const generateBtn = document.getElementById('generateBtn');
    const previewSection = document.getElementById('previewSection');
    const previewContent = document.getElementById('previewContent');
    const aiPolishBadge = document.getElementById('aiPolishBadge');
    const editBtn = document.getElementById('editBtn');
    const paymentBtn = document.getElementById('paymentBtn');
    const builderError = document.getElementById('builderError');
    const prefillBanner = document.getElementById('prefillBanner');

    // Upload section DOM references
    const uploadSection = document.getElementById('uploadSection');
    const manualFormSection = document.getElementById('manualFormSection');
    const buildDropZone = document.getElementById('buildDropZone');
    const buildResumeFile = document.getElementById('buildResumeFile');
    const buildFileSelected = document.getElementById('buildFileSelected');
    const buildFileName = document.getElementById('buildFileName');
    const buildRemoveFile = document.getElementById('buildRemoveFile');
    const uploadTargetJD = document.getElementById('uploadTargetJD');
    const uploadGenerateBtn = document.getElementById('uploadGenerateBtn');
    const uploadError = document.getElementById('uploadError');
    const showManualFormLink = document.getElementById('showManualForm');
    const showUploadLink = document.getElementById('showUploadSection');

    // ============================================================
    // INIT: CHECK FOR POST-SCAN OR POST-PAYMENT
    // ============================================================
    document.addEventListener('DOMContentLoaded', function () {
        const params = new URLSearchParams(window.location.search);

        // Post-scan: hide upload section, auto-generate CV from scan data
        if (params.get('from') === 'scan') {
            if (uploadSection) uploadSection.style.display = 'none';
            autoGenerateFromScan();
        }

        // Post-payment download — hide upload section
        if (params.get('payment') === 'success') {
            if (uploadSection) uploadSection.style.display = 'none';
            const token = params.get('token');
            const sessionId = params.get('session_id');
            if (token && sessionId) {
                handlePostPayment(token, sessionId);
            }
        }

        // Payment cancelled — hide upload, show form so they can see their preview
        if (params.get('payment') === 'cancelled') {
            showPaymentCancelledMessage();
        }
    });

    // ============================================================
    // POST-SCAN: SKIP FORM, AUTO-GENERATE CV FROM SCAN DATA
    // ============================================================
    async function autoGenerateFromScan() {
        try {
            const scanDataRaw = sessionStorage.getItem('resumeradar_scan_for_builder');
            if (!scanDataRaw) {
                // No scan data — show upload section as fallback
                if (uploadSection) uploadSection.style.display = 'block';
                return;
            }

            const scanData = JSON.parse(scanDataRaw);
            // Don't remove yet — keep for retry
            // sessionStorage.removeItem('resumeradar_scan_for_builder');

            const resumeText = scanData.resumeText || '';
            const jobDescription = scanData.jobDescription || '';
            lastTargetJD = jobDescription; // Store for form pre-populate

            if (!resumeText || !jobDescription) {
                // Missing data — show upload section as fallback
                if (uploadSection) uploadSection.style.display = 'block';
                return;
            }

            // Hide the form, show a generating state
            builderForm.style.display = 'none';
            previewSection.style.display = 'block';
            previewContent.innerHTML = `
                <div class="scan-generating">
                    <div class="spinner"></div>
                    <h3 class="scan-loading-text">Analyzing the job description...</h3>
                    <p>Our AI is extracting your details and tailoring everything to the job description.</p>
                    <div class="loading-progress"><div class="loading-progress-bar"></div></div>
                </div>
            `;
            startLoadingRotation(previewContent.querySelector('.scan-loading-text'));

            // Build scan keywords for the AI
            const scanKeywords = {};
            const matched = scanData.matchedKeywords || {};
            const missing = scanData.missingKeywords || {};
            const matchedList = [];
            const missingList = [];
            Object.values(matched).forEach(arr => { if (Array.isArray(arr)) matchedList.push(...arr); });
            Object.values(missing).forEach(arr => { if (Array.isArray(arr)) missingList.push(...arr); });
            if (matchedList.length) scanKeywords.matched = matchedList;
            if (missingList.length) scanKeywords.missing = missingList;

            // Call the one-shot extract+polish endpoint
            const response = await fetch('/api/build/generate-from-scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    resume_text: resumeText,
                    job_description: jobDescription,
                    scan_keywords: scanKeywords,
                }),
            });

            const result = await response.json();

            if (!response.ok || result.error) {
                stopLoadingRotation();
                previewContent.innerHTML = `
                    <div class="scan-generating scan-error">
                        <p>${result.error || 'Something went wrong. Please try again.'}</p>
                        <button type="button" class="btn-retry" onclick="location.reload()">Try Again</button>
                    </div>
                `;
                return;
            }

            stopLoadingRotation();

            // Success — store data and render preview
            currentToken = result.token;
            currentPolished = result.polished;
            storageMode = result.storage || 'server';

            if (storageMode === 'client') {
                sessionStorage.setItem(`resumeradar_cv_${currentToken}`, JSON.stringify(currentPolished));
            }

            // Now we can clean up scan data
            sessionStorage.removeItem('resumeradar_scan_for_builder');

            // Show the polished preview
            if (result.polished.ai_polished && aiPolishBadge) {
                aiPolishBadge.style.display = 'inline-block';
            }
            renderPreview(result.polished);

            // Show the edit button (leads to form for manual tweaks)
            if (editBtn) editBtn.style.display = 'inline-block';

            window.scrollTo({ top: previewSection.offsetTop - 20, behavior: 'smooth' });

        } catch (e) {
            console.error('Auto-generate error:', e);
            stopLoadingRotation();
            previewContent.innerHTML = `
                <div class="scan-generating scan-error">
                    <p>Network error. Please check your connection and try again.</p>
                    <button type="button" class="btn-retry" onclick="location.reload()">Try Again</button>
                </div>
            `;
        }
    }

    // ============================================================
    // DYNAMIC FORM ENTRIES (Add/Remove)
    // ============================================================

    // Experience
    document.getElementById('addExperience').addEventListener('click', function () {
        const container = document.getElementById('experienceEntries');
        const entries = container.querySelectorAll('.experience-entry');
        const newIndex = entries.length;

        const template = entries[0].cloneNode(true);
        template.setAttribute('data-index', newIndex);
        // Clear all inputs
        template.querySelectorAll('input, textarea').forEach(el => el.value = '');
        // Show remove button
        template.querySelector('.remove-entry-btn').style.display = 'block';
        template.querySelector('.remove-entry-btn').addEventListener('click', function () {
            template.remove();
            updateRemoveButtons('experienceEntries', '.experience-entry');
        });

        container.appendChild(template);
        updateRemoveButtons('experienceEntries', '.experience-entry');
    });

    // Education
    document.getElementById('addEducation').addEventListener('click', function () {
        const container = document.getElementById('educationEntries');
        const entries = container.querySelectorAll('.education-entry');
        const newIndex = entries.length;

        const template = entries[0].cloneNode(true);
        template.setAttribute('data-index', newIndex);
        template.querySelectorAll('input').forEach(el => el.value = '');
        template.querySelector('.remove-entry-btn').style.display = 'block';
        template.querySelector('.remove-entry-btn').addEventListener('click', function () {
            template.remove();
            updateRemoveButtons('educationEntries', '.education-entry');
        });

        container.appendChild(template);
        updateRemoveButtons('educationEntries', '.education-entry');
    });

    // Certifications
    document.getElementById('addCert').addEventListener('click', function () {
        const container = document.getElementById('certEntries');
        const entries = container.querySelectorAll('.cert-entry');
        const newIndex = entries.length;

        const template = entries[0].cloneNode(true);
        template.setAttribute('data-index', newIndex);
        template.querySelectorAll('input').forEach(el => el.value = '');
        template.querySelector('.remove-entry-btn').style.display = 'block';
        template.querySelector('.remove-entry-btn').addEventListener('click', function () {
            template.remove();
            updateRemoveButtons('certEntries', '.cert-entry');
        });

        container.appendChild(template);
        updateRemoveButtons('certEntries', '.cert-entry');
    });

    function updateRemoveButtons(containerId, entrySelector) {
        const container = document.getElementById(containerId);
        const entries = container.querySelectorAll(entrySelector);
        entries.forEach((entry, i) => {
            const btn = entry.querySelector('.remove-entry-btn');
            // Only show remove on entries after the first, when there's more than 1
            btn.style.display = (entries.length > 1 && i > 0) ? 'block' : 'none';
        });
    }

    // ============================================================
    // UPLOAD SECTION: TOGGLE, FILE HANDLING, SUBMIT
    // ============================================================

    // Toggle: show manual form, hide upload section
    if (showManualFormLink) {
        showManualFormLink.addEventListener('click', function (e) {
            e.preventDefault();
            if (uploadSection) uploadSection.style.display = 'none';
            if (manualFormSection) manualFormSection.style.display = 'block';
            window.scrollTo({ top: manualFormSection.offsetTop - 20, behavior: 'smooth' });
        });
    }

    // Toggle: show upload section, hide manual form
    if (showUploadLink) {
        showUploadLink.addEventListener('click', function (e) {
            e.preventDefault();
            if (manualFormSection) manualFormSection.style.display = 'none';
            if (uploadSection) uploadSection.style.display = 'block';
            window.scrollTo({ top: uploadSection.offsetTop - 20, behavior: 'smooth' });
        });
    }

    // --- File upload handling for build drop zone ---
    if (buildDropZone) {
        buildDropZone.addEventListener('click', function () { buildResumeFile.click(); });

        buildDropZone.addEventListener('dragover', function (e) {
            e.preventDefault();
            buildDropZone.classList.add('dragover');
        });
        buildDropZone.addEventListener('dragleave', function () {
            buildDropZone.classList.remove('dragover');
        });
        buildDropZone.addEventListener('drop', function (e) {
            e.preventDefault();
            buildDropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                handleBuildFileSelect(e.dataTransfer.files[0]);
            }
        });

        buildResumeFile.addEventListener('change', function (e) {
            if (e.target.files.length > 0) {
                handleBuildFileSelect(e.target.files[0]);
            }
        });

        if (buildRemoveFile) {
            buildRemoveFile.addEventListener('click', function () {
                buildResumeFile.value = '';
                buildFileSelected.style.display = 'none';
                buildDropZone.style.display = 'block';
            });
        }
    }

    function handleBuildFileSelect(file) {
        var allowedTypes = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ];
        var ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowedTypes.includes(file.type) && ext !== '.pdf' && ext !== '.docx') {
            showUploadError('Please upload a PDF or DOCX file.');
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            showUploadError('File too large. Maximum size is 5MB.');
            return;
        }
        // Assign file to the hidden input
        var dt = new DataTransfer();
        dt.items.add(file);
        buildResumeFile.files = dt.files;
        // Show selected file indicator
        buildFileName.textContent = file.name;
        buildFileSelected.style.display = 'flex';
        buildDropZone.style.display = 'none';
        hideUploadError();
    }

    function showUploadError(msg) {
        if (uploadError) {
            uploadError.textContent = msg;
            uploadError.style.display = 'block';
            uploadError.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    function hideUploadError() {
        if (uploadError) {
            uploadError.style.display = 'none';
        }
    }

    function setUploadGenerateLoading(loading) {
        if (!uploadGenerateBtn) return;
        var textEl = uploadGenerateBtn.querySelector('.gen-btn-text');
        var loadEl = uploadGenerateBtn.querySelector('.gen-btn-loading');
        var loadingTextEl = uploadGenerateBtn.querySelector('.gen-loading-text');
        if (loading) {
            textEl.style.display = 'none';
            loadEl.style.display = 'inline-flex';
            uploadGenerateBtn.disabled = true;
            if (loadingTextEl) startLoadingRotation(loadingTextEl);
        } else {
            textEl.style.display = 'inline';
            loadEl.style.display = 'none';
            uploadGenerateBtn.disabled = false;
            stopLoadingRotation();
        }
    }

    // --- Upload + Generate submit ---
    if (uploadGenerateBtn) {
        uploadGenerateBtn.addEventListener('click', async function () {
            hideUploadError();

            // Validation
            if (!buildResumeFile || !buildResumeFile.files.length) {
                showUploadError('Please upload your CV file.');
                return;
            }
            var jd = uploadTargetJD ? uploadTargetJD.value.trim() : '';
            if (!jd) {
                showUploadError('Please paste the target job description.');
                return;
            }

            lastTargetJD = jd;
            setUploadGenerateLoading(true);

            try {
                var formData = new FormData();
                formData.append('resume_file', buildResumeFile.files[0]);
                formData.append('job_description', jd);

                var response = await fetch('/api/build/generate-from-upload', {
                    method: 'POST',
                    body: formData,
                });

                // Handle rate limiting
                if (response.status === 429) {
                    var retryAfter = response.headers.get('Retry-After');
                    var mins = 5;
                    if (retryAfter) {
                        var secs = parseInt(retryAfter, 10);
                        if (!isNaN(secs)) {
                            mins = Math.max(1, Math.ceil(secs / 60));
                        } else {
                            var retryDate = new Date(retryAfter);
                            if (!isNaN(retryDate.getTime())) {
                                mins = Math.max(1, Math.ceil((retryDate - Date.now()) / 60000));
                            }
                        }
                    }
                    showUploadError('Too many requests. Please wait ' + mins + ' minute' + (mins > 1 ? 's' : '') + ' and try again.');
                    setUploadGenerateLoading(false);
                    return;
                }

                var result = await response.json();

                if (!response.ok || result.error) {
                    showUploadError(result.error || 'Something went wrong. Please try again.');
                    setUploadGenerateLoading(false);
                    return;
                }

                // Success — same post-processing as autoGenerateFromScan
                currentToken = result.token;
                currentPolished = result.polished;
                storageMode = result.storage || 'server';

                if (storageMode === 'client' && currentToken) {
                    sessionStorage.setItem('resumeradar_cv_' + currentToken, JSON.stringify(currentPolished));
                }

                if (result.polished.ai_polished && aiPolishBadge) {
                    aiPolishBadge.style.display = 'inline-block';
                }

                // Hide upload section, show preview
                if (uploadSection) uploadSection.style.display = 'none';
                previewSection.style.display = 'block';
                renderPreview(result.polished);

                if (editBtn) editBtn.style.display = 'inline-block';
                window.scrollTo({ top: previewSection.offsetTop - 20, behavior: 'smooth' });

            } catch (e) {
                console.error('Upload generate error:', e);
                showUploadError('Network error. Please check your connection and try again.');
            }

            setUploadGenerateLoading(false);
        });
    }

    // ============================================================
    // COLLECT FORM DATA
    // ============================================================
    function collectFormData() {
        const personal = {
            full_name: document.getElementById('fullName').value.trim(),
            email: document.getElementById('email').value.trim(),
            phone: document.getElementById('phone').value.trim(),
            location: document.getElementById('location').value.trim(),
            linkedin: document.getElementById('linkedin').value.trim(),
            portfolio: document.getElementById('portfolio').value.trim(),
        };

        const summary = document.getElementById('summary').value.trim();

        // Experience
        const experience = [];
        document.querySelectorAll('.experience-entry').forEach(entry => {
            const title = entry.querySelector('.exp-title').value.trim();
            const company = entry.querySelector('.exp-company').value.trim();
            if (!title && !company) return; // Skip empty entries

            const bulletsText = entry.querySelector('.exp-bullets').value.trim();
            const bullets = bulletsText
                ? bulletsText.split('\n').map(b => b.trim()).filter(b => b.length > 0)
                : [];

            experience.push({
                title: title,
                company: company,
                start_date: entry.querySelector('.exp-start').value.trim(),
                end_date: entry.querySelector('.exp-end').value.trim() || 'Present',
                bullets: bullets,
            });
        });

        // Education
        const education = [];
        document.querySelectorAll('.education-entry').forEach(entry => {
            const degree = entry.querySelector('.edu-degree').value.trim();
            const institution = entry.querySelector('.edu-institution').value.trim();
            if (!degree && !institution) return;

            education.push({
                degree: degree,
                institution: institution,
                graduation_date: entry.querySelector('.edu-date').value.trim(),
                details: entry.querySelector('.edu-details').value.trim(),
            });
        });

        // Skills
        const skillsText = document.getElementById('skills').value.trim();
        const skills = skillsText
            ? skillsText.split(',').map(s => s.trim()).filter(s => s.length > 0)
            : [];

        // Certifications
        const certifications = [];
        document.querySelectorAll('.cert-entry').forEach(entry => {
            const name = entry.querySelector('.cert-name').value.trim();
            if (!name) return;

            certifications.push({
                name: name,
                issuer: entry.querySelector('.cert-issuer').value.trim(),
                date: entry.querySelector('.cert-date').value.trim(),
            });
        });

        const target_job_description = document.getElementById('targetJD').value.trim();
        lastTargetJD = target_job_description; // Store for form pre-populate

        return {
            personal,
            summary,
            experience,
            education,
            skills,
            certifications,
            target_job_description,
        };
    }

    // ============================================================
    // GENERATE CV
    // ============================================================
    builderForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        hideError();

        const data = collectFormData();

        // Basic validation
        if (!data.personal.full_name) {
            showError('Please enter your full name.');
            return;
        }
        if (!data.target_job_description) {
            showError('Please paste the target job description.');
            return;
        }
        if (data.experience.length === 0) {
            showError('Please add at least one work experience entry.');
            return;
        }

        // Show loading
        setGenerateLoading(true);

        try {
            const response = await fetch('/api/build/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });

            const result = await response.json();

            if (!response.ok || result.error) {
                showError(result.error || 'Something went wrong. Please try again.');
                setGenerateLoading(false);
                return;
            }

            currentToken = result.token;
            currentPolished = result.polished;
            storageMode = result.storage || 'server';

            // If client storage mode, also save to sessionStorage
            if (storageMode === 'client') {
                sessionStorage.setItem(`resumeradar_cv_${currentToken}`, JSON.stringify(currentPolished));
            }

            // Render preview
            renderPreview(currentPolished);

            // Show preview section, hide form + upload
            if (uploadSection) uploadSection.style.display = 'none';
            if (manualFormSection) manualFormSection.style.display = 'none';
            builderForm.style.display = 'none';
            previewSection.style.display = 'block';
            window.scrollTo({ top: previewSection.offsetTop - 20, behavior: 'smooth' });

        } catch (err) {
            console.error('Generate error:', err);
            showError('Network error. Please check your connection and try again.');
        }

        setGenerateLoading(false);
    });

    // ============================================================
    // RENDER PREVIEW
    // ============================================================
    function renderPreview(data) {
        if (data.ai_polished) {
            aiPolishBadge.style.display = 'inline-block';
        }

        const personal = data.personal || {};
        const experience = data.experience || [];
        const education = data.education || [];
        // Skills can be array (from form flow) or object (from scan flow)
        let skillsList = [];
        const smartSuggestions = data.smart_suggestions || [];
        // Backward compat: old responses may use suggested_additions
        const legacySuggested = data.suggested_additions || [];
        if (Array.isArray(data.skills)) {
            skillsList = data.skills;
        } else if (data.skills && typeof data.skills === 'object') {
            skillsList = [
                ...(data.skills.matched || []),
                ...(data.skills.additional || []),
            ];
        }
        const certifications = data.certifications || [];

        let html = '';

        // ---- VISIBLE SECTION (not blurred) ----
        // Name + Contact
        html += `<div class="preview-name">${escapeHtml(personal.full_name || '')}</div>`;
        const contactParts = [personal.email, personal.phone, personal.location, personal.linkedin, personal.portfolio].filter(Boolean);
        if (contactParts.length) {
            html += `<div class="preview-contact">${contactParts.map(escapeHtml).join(' | ')}</div>`;
        }

        // Summary (visible — hooks the user, inline editable)
        if (data.summary) {
            html += `<div class="preview-section-title">Professional Summary</div>`;
            html += `<div class="preview-text preview-summary-editable" contenteditable="true">${escapeHtml(data.summary)}</div>`;
        }

        // ---- BLURRED/LOCKED SECTION ----
        html += `<div class="preview-locked-section">`;
        html += `<div class="preview-blurred">`;

        // Experience
        if (experience.length) {
            html += `<div class="preview-section-title">Experience</div>`;
            experience.forEach(exp => {
                html += `<div class="preview-exp-header">`;
                html += `<strong>${escapeHtml(exp.title || '')}</strong>`;
                if (exp.company) html += ` | ${escapeHtml(exp.company)}`;
                html += `</div>`;
                const dates = [exp.start_date, exp.end_date].filter(Boolean).join(' - ');
                if (dates) html += `<div class="preview-exp-dates">${escapeHtml(dates)}</div>`;
                if (exp.bullets && exp.bullets.length) {
                    html += '<ul class="preview-bullets">';
                    exp.bullets.forEach(b => {
                        html += `<li>${escapeHtml(b)}</li>`;
                    });
                    html += '</ul>';
                }
            });
        }

        // Education
        if (education.length) {
            html += `<div class="preview-section-title">Education</div>`;
            education.forEach(edu => {
                html += `<div class="preview-exp-header">`;
                html += `<strong>${escapeHtml(edu.degree || '')}</strong>`;
                if (edu.institution) html += ` | ${escapeHtml(edu.institution)}`;
                html += `</div>`;
                if (edu.graduation_date) html += `<div class="preview-exp-dates">${escapeHtml(edu.graduation_date)}</div>`;
                if (edu.details) html += `<div class="preview-text">${escapeHtml(edu.details)}</div>`;
            });
        }

        // Skills
        if (skillsList.length) {
            html += `<div class="preview-section-title">Skills</div>`;
            html += `<div class="preview-skills">${skillsList.map(s => `<span class="preview-skill-tag">${escapeHtml(s)}</span>`).join('')}</div>`;
        }

        // Smart Suggestions (coaching tips — not added to CV)
        const allSuggestions = [...smartSuggestions, ...legacySuggested];
        if (allSuggestions.length) {
            html += `<div class="preview-section-title">💡 Smart Suggestions to Strengthen Your CV</div>`;
            html += `<div class="smart-suggestions-list">`;
            allSuggestions.forEach(tip => {
                html += `<div class="smart-suggestion-item">💬 ${escapeHtml(tip)}</div>`;
            });
            html += `</div>`;
        }

        // Certifications
        if (certifications.length) {
            html += `<div class="preview-section-title">Certifications</div>`;
            certifications.forEach(cert => {
                let line = escapeHtml(cert.name || '');
                if (cert.issuer) line += ` - ${escapeHtml(cert.issuer)}`;
                if (cert.date) line += ` (${escapeHtml(cert.date)})`;
                html += `<div class="preview-text">${line}</div>`;
            });
        }

        // Close the blurred section and add lock overlay
        html += `</div>`; // close .preview-blurred
        html += `<div class="preview-locked-overlay">`;
        html += `<p>🔒 Download the full ATS-optimized CV for $2</p>`;
        html += `<small>Pick a template below and click Download PDF</small>`;
        html += `</div>`;
        html += `</div>`; // close .preview-locked-section

        previewContent.innerHTML = html;

        // Attach blur listener for inline summary editing
        const editableSummary = previewContent.querySelector('.preview-summary-editable');
        if (editableSummary) {
            editableSummary.addEventListener('blur', function () {
                const newText = editableSummary.textContent.trim();
                if (currentPolished) {
                    currentPolished.summary = newText;
                    // Sync to sessionStorage if in client mode
                    if (storageMode === 'client' && currentToken) {
                        sessionStorage.setItem(`resumeradar_cv_${currentToken}`, JSON.stringify(currentPolished));
                    }
                }
            });
        }
    }

    // ============================================================
    // FORM PRE-POPULATE HELPER
    // ============================================================
    function populateDynamicEntries(type, entries) {
        if (!entries || !entries.length) return;

        let containerId, entrySelector, addBtnId;
        if (type === 'experience') {
            containerId = 'experienceEntries';
            entrySelector = '.experience-entry';
            addBtnId = 'addExperience';
        } else if (type === 'education') {
            containerId = 'educationEntries';
            entrySelector = '.education-entry';
            addBtnId = 'addEducation';
        } else if (type === 'certifications') {
            containerId = 'certEntries';
            entrySelector = '.cert-entry';
            addBtnId = 'addCert';
        } else {
            return;
        }

        const container = document.getElementById(containerId);
        const addBtn = document.getElementById(addBtnId);

        // Clear stale extra entries — keep only the first one, reset it
        const existingEntries = container.querySelectorAll(entrySelector);
        for (let i = existingEntries.length - 1; i > 0; i--) {
            existingEntries[i].remove();
        }

        // Fill first entry
        const firstEntry = container.querySelector(entrySelector);
        fillEntry(type, firstEntry, entries[0]);

        // Add + fill remaining entries
        for (let i = 1; i < entries.length; i++) {
            addBtn.click(); // triggers the add handler which clones + appends
            const allEntries = container.querySelectorAll(entrySelector);
            fillEntry(type, allEntries[allEntries.length - 1], entries[i]);
        }
    }

    function fillEntry(type, el, data) {
        if (!el || !data) return;
        if (type === 'experience') {
            el.querySelector('.exp-title').value = data.title || '';
            el.querySelector('.exp-company').value = data.company || '';
            el.querySelector('.exp-start').value = data.start_date || '';
            el.querySelector('.exp-end').value = data.end_date || '';
            const bullets = Array.isArray(data.bullets) ? data.bullets.join('\n') : '';
            el.querySelector('.exp-bullets').value = bullets;
        } else if (type === 'education') {
            el.querySelector('.edu-degree').value = data.degree || '';
            el.querySelector('.edu-institution').value = data.institution || '';
            el.querySelector('.edu-date').value = data.graduation_date || '';
            el.querySelector('.edu-details').value = data.details || '';
        } else if (type === 'certifications') {
            el.querySelector('.cert-name').value = data.name || '';
            el.querySelector('.cert-issuer').value = data.issuer || '';
            el.querySelector('.cert-date').value = data.date || '';
        }
    }

    // ============================================================
    // EDIT & REGENERATE
    // ============================================================
    editBtn.addEventListener('click', function () {
        // Pre-populate form from polished data
        if (currentPolished) {
            const p = currentPolished.personal || {};
            document.getElementById('fullName').value = p.full_name || '';
            document.getElementById('email').value = p.email || '';
            document.getElementById('phone').value = p.phone || '';
            document.getElementById('location').value = p.location || '';
            document.getElementById('linkedin').value = p.linkedin || '';
            document.getElementById('portfolio').value = p.portfolio || '';
            document.getElementById('summary').value = currentPolished.summary || '';

            // Skills: flatten object or array to comma string
            let skillsStr = '';
            if (Array.isArray(currentPolished.skills)) {
                skillsStr = currentPolished.skills.join(', ');
            } else if (currentPolished.skills && typeof currentPolished.skills === 'object') {
                const all = [
                    ...(currentPolished.skills.matched || []),
                    ...(currentPolished.skills.additional || []),
                ];
                skillsStr = all.join(', ');
            }
            document.getElementById('skills').value = skillsStr;

            // Dynamic entries
            populateDynamicEntries('experience', currentPolished.experience);
            populateDynamicEntries('education', currentPolished.education);
            populateDynamicEntries('certifications', currentPolished.certifications);

            // Target JD
            if (lastTargetJD) {
                document.getElementById('targetJD').value = lastTargetJD;
            }
        }

        // Hide upload section, show manual form (pre-populated)
        if (uploadSection) uploadSection.style.display = 'none';
        if (manualFormSection) manualFormSection.style.display = 'block';
        previewSection.style.display = 'none';
        builderForm.style.display = 'block';
        window.scrollTo({ top: manualFormSection.offsetTop - 20, behavior: 'smooth' });
    });

    // ============================================================
    // PAYMENT FLOW
    // ============================================================
    paymentBtn.addEventListener('click', async function () {
        if (!currentToken) {
            showError('Please generate your CV first.');
            return;
        }

        const selectedTemplate = document.querySelector('input[name="template"]:checked').value;

        setPaymentLoading(true);

        try {
            const deliveryEmail = (document.getElementById('deliveryEmail') || {}).value || '';
            const response = await fetch('/api/build/create-checkout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    token: currentToken,
                    template: selectedTemplate,
                    delivery_email: deliveryEmail.trim(),
                }),
            });

            // Handle rate limiting with Retry-After guidance
            if (response.status === 429) {
                const retryAfter = response.headers.get('Retry-After');
                let mins = 5; // safe default
                if (retryAfter) {
                    const secs = parseInt(retryAfter, 10);
                    if (!isNaN(secs)) {
                        mins = Math.max(1, Math.ceil(secs / 60));
                    } else {
                        // HTTP-date format: try to parse as Date
                        const retryDate = new Date(retryAfter);
                        if (!isNaN(retryDate.getTime())) {
                            mins = Math.max(1, Math.ceil((retryDate - Date.now()) / 60000));
                        }
                    }
                }
                showError('Too many requests. Please wait ' + mins + ' minute' + (mins > 1 ? 's' : '') + ' and try again.');
                setPaymentLoading(false);
                return;
            }

            const result = await response.json();

            if (!response.ok || result.error) {
                showError(result.error || 'Could not start payment. Please try again.');
                setPaymentLoading(false);
                return;
            }

            // Store template choice and token for post-payment
            sessionStorage.setItem('resumeradar_cv_template', selectedTemplate);

            // Redirect to Stripe Checkout
            window.location.href = result.checkout_url;

        } catch (err) {
            console.error('Payment error:', err);
            showError('Network error. Please try again.');
            setPaymentLoading(false);
        }
    });

    // ============================================================
    // PAYMENT CANCELLED FEEDBACK
    // ============================================================
    function showPaymentCancelledMessage() {
        // Show a temporary banner at the top of the page
        const banner = document.createElement('div');
        banner.className = 'payment-cancelled-banner';
        banner.innerHTML = `
            <div class="cancelled-content">
                <span class="cancelled-icon">✕</span>
                <div>
                    <strong>Payment cancelled</strong>
                    <p>No worries — your CV is still ready. You can try again whenever you like.</p>
                </div>
                <button class="cancelled-dismiss" aria-label="Dismiss">&times;</button>
            </div>
        `;
        document.body.prepend(banner);

        // Dismiss button
        banner.querySelector('.cancelled-dismiss').addEventListener('click', function () {
            banner.remove();
        });

        // Auto-dismiss after 8 seconds
        setTimeout(function () {
            if (banner.parentNode) {
                banner.style.opacity = '0';
                setTimeout(function () { banner.remove(); }, 300);
            }
        }, 8000);

        // Clean up the URL
        const url = new URL(window.location);
        url.searchParams.delete('payment');
        window.history.replaceState({}, '', url);
    }

    // ============================================================
    // POST-PAYMENT DOWNLOAD
    // ============================================================
    async function handlePostPayment(token, sessionId) {
        const template = sessionStorage.getItem('resumeradar_cv_template') || 'classic';
        sessionStorage.removeItem('resumeradar_cv_template');

        // Show a download status
        builderForm.style.display = 'none';
        previewSection.style.display = 'block';
        previewContent.innerHTML = '<div class="download-status"><span class="spinner"></span> Preparing your PDF download...</div>';

        try {
            let response;

            // Check if CV data is stored in sessionStorage (client fallback)
            const storedCvData = sessionStorage.getItem(`resumeradar_cv_${token}`);
            if (storedCvData) {
                // POST the CV data to the server for PDF generation
                response = await fetch(`/api/build/download/${token}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        template: template,
                        cv_data: JSON.parse(storedCvData),
                    }),
                });
                // Clean up after successful download
                if (response.ok) {
                    sessionStorage.removeItem(`resumeradar_cv_${token}`);
                }
            } else {
                // Server has the data (Redis) — use GET
                const downloadUrl = `/api/build/download/${token}?session_id=${encodeURIComponent(sessionId)}&template=${encodeURIComponent(template)}`;
                response = await fetch(downloadUrl);
            }

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                previewContent.innerHTML = `<div class="download-status download-error">${err.error || 'Download failed. Please try again or contact support.'}</div>`;
                return;
            }

            // Read email-requested header before consuming the body
            const emailRequested = response.headers.get('X-Email-Requested') === 'true';

            // Trigger download
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'ResumeRadar_CV.pdf';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            // Celebration UI
            const emailBadge = emailRequested
                ? '<div class="celebration-email-msg">📧 A copy will be sent to your email</div>'
                : '';

            previewContent.innerHTML = `
                <div class="celebration-container">
                    <div class="celebration-check">✓</div>
                    <h2 class="celebration-title">Your CV is Ready!</h2>
                    <p class="celebration-subtitle">Check your downloads folder for ResumeRadar_CV.pdf</p>
                    ${emailBadge}
                    <div class="celebration-next">
                        <p class="celebration-next-title">What to do next:</p>
                        <ul>
                            <li>Submit your CV to the target job posting</li>
                            <li>Tailor a new CV for each different role</li>
                            <li>Scan another resume to check your match score</li>
                        </ul>
                    </div>
                    <div class="celebration-actions">
                        <a href="/build" class="build-another-link celebration-btn">Build Another CV</a>
                        <a href="/" class="build-another-link celebration-btn celebration-btn-secondary">Scan a Resume</a>
                    </div>
                </div>
            `;

            // Fire confetti
            createConfetti(previewContent.querySelector('.celebration-container'));

            // Clean up URL params
            window.history.replaceState({}, '', '/build');

        } catch (err) {
            console.error('Download error:', err);
            previewContent.innerHTML = '<div class="download-status download-error">Network error during download. Please try again.</div>';
        }
    }

    // ============================================================
    // CONFETTI
    // ============================================================
    function createConfetti(container) {
        const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];
        for (let i = 0; i < 40; i++) {
            const piece = document.createElement('div');
            piece.className = 'confetti-piece';
            piece.style.left = Math.random() * 100 + '%';
            piece.style.background = colors[Math.floor(Math.random() * colors.length)];
            piece.style.animationDelay = Math.random() * 0.5 + 's';
            piece.style.animationDuration = (1.5 + Math.random() * 1.5) + 's';
            container.appendChild(piece);
        }
        // Auto-cleanup after 4 seconds
        setTimeout(function () {
            container.querySelectorAll('.confetti-piece').forEach(function (p) { p.remove(); });
        }, 4000);
    }

    // ============================================================
    // UTILITIES
    // ============================================================
    function showError(msg) {
        builderError.textContent = msg;
        builderError.style.display = 'block';
        builderError.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function hideError() {
        builderError.style.display = 'none';
    }

    function setGenerateLoading(loading) {
        const textEl = generateBtn.querySelector('.gen-btn-text');
        const loadEl = generateBtn.querySelector('.gen-btn-loading');
        const loadingTextEl = generateBtn.querySelector('.gen-loading-text');
        if (loading) {
            textEl.style.display = 'none';
            loadEl.style.display = 'inline-flex';
            generateBtn.disabled = true;
            startLoadingRotation(loadingTextEl);
        } else {
            textEl.style.display = 'inline';
            loadEl.style.display = 'none';
            generateBtn.disabled = false;
            stopLoadingRotation();
        }
    }

    function setPaymentLoading(loading) {
        const textEl = paymentBtn.querySelector('.pay-btn-text');
        const loadEl = paymentBtn.querySelector('.pay-btn-loading');
        if (loading) {
            textEl.style.display = 'none';
            loadEl.style.display = 'inline-flex';
            paymentBtn.disabled = true;
        } else {
            textEl.style.display = 'inline';
            loadEl.style.display = 'none';
            paymentBtn.disabled = false;
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

})();

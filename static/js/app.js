/**
 * ATS Scanner — Frontend Application
 * Handles form interaction, API calls, and results rendering.
 */

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

            // Render results
            renderResults(data);

        } catch (err) {
            console.error('Scan error:', err);
            showError('Could not connect to the server. Please make sure the app is running and try again.');
        } finally {
            setLoading(false);
        }
    });

    // Scan Again button
    scanAgainBtn.addEventListener('click', () => {
        resultsSection.style.display = 'none';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

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

        // 6. ATS Formatting
        renderATSFormatting(data.ats_formatting);

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
            summaryText = data.ai_suggestions.summary;
        } else if (score >= 75) {
            summaryText = "Strong match! Your resume aligns well with this job description. A few targeted tweaks could push you even higher.";
        } else if (score >= 50) {
            summaryText = "Decent foundation, but there are noticeable gaps. Focus on adding the missing technical keywords and you'll see a significant jump.";
        } else {
            summaryText = "Your resume needs significant optimization for this role. Don't worry — the suggestions below will show you exactly what to add and change.";
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
            section.innerHTML = `<h3>🔑 How to Add Missing Keywords</h3>`;
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

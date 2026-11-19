/**
 * Referral loop: share buttons, job-description links and ?ref= counting.
 * No accounts and no identity: only daily totals per event reach the server,
 * and a shared job description travels in the URL fragment, which browsers
 * never send to a server. A CV is never part of any link.
 */
(function () {
    'use strict';
    const utils = window.ResumeRadarScan;
    const BASE = 'https://resumeradar.sholastechnotes.com';
    const canNativeShare = typeof navigator.share === 'function';

    function track(eventName) {
        if (typeof window._rr_trackEvent === 'function') return window._rr_trackEvent(eventName);
        try {
            navigator.sendBeacon('/api/event', new Blob([JSON.stringify({event: eventName})], {type: 'application/json'}));
        } catch (e) { /* best-effort */ }
    }

    // Count an arrival from a shared link once per browser session.
    try {
        const ref = utils.refSource(location.search);
        if (ref && !sessionStorage.getItem('resumeradar_ref')) {
            sessionStorage.setItem('resumeradar_ref', ref);
            track('ref_visit_' + ref);
        }
    } catch (e) { /* storage blocked: skip the count, never the page */ }

    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            const area = document.createElement('textarea');
            area.value = text;
            area.setAttribute('readonly', '');
            area.style.position = 'fixed';
            area.style.opacity = '0';
            document.body.appendChild(area);
            area.select();
            let ok = false;
            try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
            document.body.removeChild(area);
            return ok;
        }
    }

    function say(origin, message) {
        const scope = origin.closest('.share-card, .share-prompt, .share-page') || document;
        const status = scope.querySelector('[data-share-status]');
        if (status) status.textContent = message;
    }

    // Returns false only when the user's device refused; a cancelled share sheet is not an error.
    async function nativeShare(data) {
        try {
            await navigator.share(data);
            return true;
        } catch (e) {
            return e && e.name === 'AbortError';
        }
    }

    async function shareSite(button) {
        const channel = button.dataset.share;
        const group = button.closest('[data-share-ref]');
        const url = utils.shareUrl(BASE, group ? group.dataset.shareRef : channel);
        const text = utils.shareMessage();
        track('share_clicked');
        if (channel === 'native') {
            if (!(await nativeShare({title: 'ResumeRadar', text, url}))) say(button, 'Sharing is not available here. Use Copy link instead.');
        } else if (channel === 'whatsapp') {
            window.open('https://wa.me/?text=' + encodeURIComponent(text + '\n\n' + url), '_blank', 'noopener');
        } else if (channel === 'linkedin') {
            window.open('https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(url), '_blank', 'noopener');
        } else {
            say(button, (await copyText(url)) ? 'Link copied. Paste it to someone who is job hunting.' : 'Could not copy. The link is ' + url);
        }
    }

    async function shareJob(button) {
        const field = document.getElementById('jobDescription');
        const job = field ? field.value.trim() : '';
        if (job.split(/\s+/).filter(Boolean).length < 10) {
            say(button, 'Paste a job description into the form first.');
            return;
        }
        const url = await utils.jobLink(BASE, job);
        if (!url) {
            say(button, 'This job description is too long to fit in a link. Send your friend the job advert and the ResumeRadar link instead.');
            return;
        }
        track('job_link_created');
        const text = 'Applying for this role too? Check your CV against it for free. The link has the job description filled in.';
        if (canNativeShare && (await nativeShare({title: 'ResumeRadar', text, url}))) return;
        say(button, (await copyText(url)) ? 'Job link copied. It holds the job description only, never your CV.' : 'Could not copy the link on this device.');
    }

    async function copyBlock(button) {
        const source = document.getElementById(button.dataset.copyTarget);
        if (!source) return;
        track('share_clicked');
        const label = button.textContent;
        button.textContent = (await copyText(source.value || source.textContent)) ? 'Copied' : 'Could not copy';
        setTimeout(() => { button.textContent = label; }, 2000);
    }

    if (canNativeShare) document.querySelectorAll('[data-share="native"]').forEach(button => { button.hidden = false; });

    document.addEventListener('click', event => {
        const button = event.target.closest('[data-share], [data-share-job], [data-copy-target]');
        if (!button) return;
        if (button.dataset.share) shareSite(button);
        else if ('shareJob' in button.dataset) shareJob(button);
        else copyBlock(button);
    });

    // Opened from a friend's job link: fill in the job description, never overwrite the visitor's own text.
    async function applyJobLink() {
        const field = document.getElementById('jobDescription');
        if (!field || !location.hash.startsWith('#job=')) return;
        const job = await utils.decodeJob(location.hash);
        if (!job || field.value.trim()) return;
        field.value = job;
        field.dispatchEvent(new Event('input', {bubbles: true}));
        const notice = document.getElementById('jobLinkNotice');
        if (notice) notice.hidden = false;
        track('job_link_opened');
    }
    applyJobLink();
})();

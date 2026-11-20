/* Shared score/history rules: usable in the browser and in regression tests. */
(function (root) {
    const utils = {
        scoreText(score) {
            return Number.isFinite(score) ? `${Math.round(score)}%` : 'Not scored';
        },
        scoreDelta(current, previous) {
            if (!current || !previous || !current.jobKey || !current.scoreVersion ||
                current.jobKey !== previous.jobKey || current.scoreVersion !== previous.scoreVersion ||
                !Number.isFinite(current.score) || !Number.isFinite(previous.score)) return null;
            return current.score - previous.score;
        },
        compareScan(current, previous) {
            const delta = utils.scoreDelta(current, previous);
            if (delta === null) return null;
            const before = new Set(previous.matchedKeywords || []);
            const after = new Set(current.matchedKeywords || []);
            return {delta, added: [...after].filter(term => !before.has(term)),
                removed: [...before].filter(term => !after.has(term))};
        },
        // A short label for a job: the first non-empty line of the description
        // (job adverts open with the title), cut to a readable length.
        jobTitle(description) {
            const line = String(description || '').split(/\r?\n/).map(l => l.replace(/\s+/g, ' ').trim()).find(Boolean) || 'Job scan';
            return line.length > 60 ? line.slice(0, 57).trimEnd() + '...' : line;
        },
        /* Job description view: where each listed term sits, and how many are marked.
           Positions are element ids: jd-term-<segment> or jd-term-<segment>-<part>. */
        jobTermIndex(segments) {
            const positions = {};
            const terms = {matched: new Set(), missing: new Set()};
            const add = (keyword, id) => {
                const list = positions[keyword] = positions[keyword] || [];
                if (!list.includes(id)) list.push(id);
            };
            (segments || []).forEach((segment, index) => {
                if (!segment || !terms[segment.status]) return;
                const id = `jd-term-${index}`;
                terms[segment.status].add(segment.keyword);
                add(segment.keyword, id);
                (segment.parts || []).forEach((part, partIndex) => {
                    if (!part || !terms[part.status]) return;
                    terms[part.status].add(part.keyword);
                    add(part.keyword, `${id}-${partIndex}`);
                });
            });
            return {positions, matched: terms.matched.size, missing: terms.missing.size};
        },
        async jobKey(description) {
            const normalized = description.trim().toLowerCase().replace(/\s+/g, ' ');
            const bytes = new TextEncoder().encode(normalized);
            const hash = await crypto.subtle.digest('SHA-256', bytes);
            return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
        },
        // ---- Referral links: no accounts, nothing stored about the sharer ----
        REF_SOURCES: ['whatsapp', 'linkedin', 'copy', 'native', 'qr', 'group', 'job'],
        JOB_LINK_MAX_CHARS: 12000,
        JOB_LINK_MAX_URL: 8000,
        shareUrl(base, source) {
            return `${base}/?ref=${utils.REF_SOURCES.includes(source) ? source : 'copy'}`;
        },
        // Allowlisted ?ref= value from a query string, or null. Never echo arbitrary input.
        refSource(search) {
            const ref = new URLSearchParams(search || '').get('ref');
            return utils.REF_SOURCES.includes(ref) ? ref : null;
        },
        shareMessage() {
            return 'Job hunting? ResumeRadar is a free tool that compares your CV with a job description ' +
                'and shows which keywords are missing. No sign-up needed.';
        },
        // The job description travels in the URL fragment, which browsers never send to a server.
        async encodeJob(text) {
            const bytes = new TextEncoder().encode(String(text || '').trim().slice(0, utils.JOB_LINK_MAX_CHARS));
            if (typeof CompressionStream === 'function') {
                try { return 'z.' + toBase64Url(await pipe(bytes, new CompressionStream('deflate-raw'))); }
                catch (e) { /* fall through to the uncompressed form */ }
            }
            return 't.' + toBase64Url(bytes);
        },
        async decodeJob(hash) {
            try {
                const match = /^#?job=([zt])\.([A-Za-z0-9_-]+)$/.exec(hash || '');
                if (!match || match[2].length > utils.JOB_LINK_MAX_URL) return null;
                let bytes = fromBase64Url(match[2]);
                if (match[1] === 'z') {
                    // Four bytes per character is the UTF-8 ceiling, so this bounds a hostile link.
                    bytes = await pipe(bytes, new DecompressionStream('deflate-raw'), utils.JOB_LINK_MAX_CHARS * 4);
                }
                const text = new TextDecoder('utf-8', {fatal: true}).decode(bytes).trim();
                return text ? text.slice(0, utils.JOB_LINK_MAX_CHARS) : null;
            } catch (e) {
                return null;
            }
        },
        async jobLink(base, text) {
            if (String(text || '').trim().length > utils.JOB_LINK_MAX_CHARS) return null;
            const url = `${utils.shareUrl(base, 'job')}#job=${await utils.encodeJob(text)}`;
            return url.length <= utils.JOB_LINK_MAX_URL ? url : null;
        },
    };
    function toBase64Url(bytes) {
        let binary = '';
        for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    function fromBase64Url(value) {
        const binary = atob(value.replace(/-/g, '+').replace(/_/g, '/'));
        return Uint8Array.from(binary, c => c.charCodeAt(0));
    }
    async function pipe(bytes, transform, maxBytes) {
        const writer = transform.writable.getWriter();
        writer.write(bytes).catch(() => {});
        writer.close().catch(() => {});
        const reader = transform.readable.getReader();
        const chunks = [];
        let total = 0;
        for (;;) {
            const {done, value} = await reader.read();
            if (done) break;
            total += value.length;
            if (maxBytes && total > maxBytes) { reader.cancel().catch(() => {}); throw new Error('too large'); }
            chunks.push(value);
        }
        const out = new Uint8Array(total);
        let offset = 0;
        for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.length; }
        return out;
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = utils;
    else root.ResumeRadarScan = utils;
})(typeof window !== 'undefined' ? window : this);

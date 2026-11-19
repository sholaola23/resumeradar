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
        /* Job description view: where each listed term sits, and how many are marked. */
        jobTermIndex(segments) {
            const positions = {};
            const terms = {matched: new Set(), missing: new Set()};
            (segments || []).forEach((segment, index) => {
                if (!segment || !terms[segment.status]) return;
                terms[segment.status].add(segment.keyword);
                for (const keyword of [segment.keyword, ...(segment.also || [])]) {
                    (positions[keyword] = positions[keyword] || []).push(index);
                }
            });
            return {positions, matched: terms.matched.size, missing: terms.missing.size};
        },
        async jobKey(description) {
            const normalized = description.trim().toLowerCase().replace(/\s+/g, ' ');
            const bytes = new TextEncoder().encode(normalized);
            const hash = await crypto.subtle.digest('SHA-256', bytes);
            return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
        },
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = utils;
    else root.ResumeRadarScan = utils;
})(typeof window !== 'undefined' ? window : this);

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

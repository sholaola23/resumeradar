/**
 * "Was this useful?" card under the scan report.
 *
 * A Yes or No tap is one anonymous funnel counter (feedback_yes / feedback_no).
 * The optional comment goes to /api/feedback with the vote and the may-quote
 * tick only: no scan data, score or journey ID is sent with it.
 */
(function () {
    'use strict';

    var card = document.getElementById('feedbackCard');
    if (!card) return;

    var vote = document.getElementById('feedbackVote');
    var status = document.getElementById('feedbackStatus');
    var form = document.getElementById('feedbackForm');
    var label = document.getElementById('feedbackCommentLabel');
    var comment = document.getElementById('feedbackComment');
    var consentRow = document.getElementById('feedbackConsentRow');
    var consent = document.getElementById('feedbackConsent');
    var send = document.getElementById('feedbackSend');
    var useful = null;
    var report = 0; // goes up on each new report, so a late reply is ignored

    function say(message, isError) {
        status.textContent = message;
        status.classList.toggle('is-error', !!isError);
    }

    function reset() {
        report += 1;
        useful = null;
        vote.hidden = false;
        form.hidden = true;
        form.reset();
        send.disabled = false;
        say('');
    }

    function choose(isUseful) {
        useful = isUseful;
        if (window._rr_trackEvent) window._rr_trackEvent(isUseful ? 'feedback_yes' : 'feedback_no');
        vote.hidden = true;
        label.textContent = isUseful ? 'What helped most? (optional)' : 'What was missing or wrong? (optional)';
        consentRow.hidden = !isUseful;
        form.hidden = false;
        say('Thanks for telling us.');
        comment.focus();
    }

    document.getElementById('feedbackYes').addEventListener('click', function () { choose(true); });
    document.getElementById('feedbackNo').addEventListener('click', function () { choose(false); });

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        if (useful === null) return;
        var text = comment.value.trim();
        if (!text) {
            say('Write a comment first, or leave it there. Your answer is already counted.', true);
            comment.focus();
            return;
        }
        send.disabled = true;
        var sentFor = report;
        fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ useful: useful, comment: text, may_quote: useful && consent.checked })
        }).then(function (response) {
            if (sentFor !== report) return;
            if (!response.ok) throw new Error('feedback not saved');
            form.hidden = true;
            say('Thanks. Your comment has been sent.');
        }).catch(function () {
            if (sentFor !== report) return;
            send.disabled = false;
            say('We could not send your comment. Please try again in a moment.', true);
        });
    });

    document.addEventListener('rr:results-rendered', reset);
})();

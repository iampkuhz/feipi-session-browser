/**
 * Unified copy-to-clipboard helper.
 *
 * Usage:
 *   // Copy text, show feedback on a button element
 *   arpCopy(btn, 'text to copy');
 *
 *   // Copy text with explicit original/feedback strings
 *   arpCopy(btn, text, { original: 'Copy', feedback: 'Copied!' });
 */
(function() {
    'use strict';

    var DEFAULT_FEEDBACK = '✓';  // ✓
    var DEFAULT_DURATION  = 1200;     // ms

    /**
     * Copy `text` to clipboard and give brief visual feedback on `btn`.
     * Falls back to execCommand if the Clipboard API is unavailable.
     *
     * @param {HTMLElement} btn       Element to show feedback on.
     * @param {string}      text      Text to copy.
     * @param {Object}      [opts]    Optional: { original, feedback, duration }.
     */
    window.arpCopy = function(btn, text, opts) {
        opts = opts || {};
        var feedbackText = opts.feedback || DEFAULT_FEEDBACK;
        var originalHTML = opts.original !== undefined
            ? opts.original
            : btn.innerHTML;
        var duration     = opts.duration || DEFAULT_DURATION;

        function showFeedback() {
            btn.innerHTML = feedbackText;
            btn.classList.add('copied');
            setTimeout(function() {
                btn.innerHTML = originalHTML;
                btn.classList.remove('copied');
            }, duration);
        }

        function fail() {
            console.warn('[arpCopy] Clipboard API not available. Copy this value manually:\n' + text);
            btn.innerHTML = '!';
            btn.title = 'Copy failed — see console';
            setTimeout(function() {
                btn.innerHTML = originalHTML;
                btn.title = '';
            }, duration);
        }

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(showFeedback, fail);
        } else {
            // Legacy fallback
            try {
                var ta = document.createElement('textarea');
                ta.value = text;
                ta.setAttribute('readonly', '');
                ta.style.position = 'absolute';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.select();
                var ok = document.execCommand('copy');
                document.body.removeChild(ta);
                if (ok) { showFeedback(); } else { fail(); }
            } catch (e) {
                fail();
            }
        }
    };

    /* ─── Convenience wrappers used by existing templates ─────── */

    /** Drop-in replacement for copyProjectPath(btn, path). */
    window.copyProjectPath = function(btn, path) {
        window.arpCopy(btn, path, {
            feedback: '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 8 7 11 12 5"/></svg>',
            original: btn.innerHTML
        });
    };

    /** Copy raw session JSON data. */
    window.copyRawData = function() {
        var el = document.getElementById('raw-json');
        if (!el) return;
        window.arpCopy(event.target, el.textContent, {
            feedback: 'Copied!',
            original: 'Copy',
            duration: 1500
        });
    };

    /** Copy text from a data-clipboard-text attribute. */
    window.arpCopyAttr = function(btn) {
        var text = btn.getAttribute('data-clipboard-text');
        if (text === null) {
            console.warn('[arpCopyAttr] No data-clipboard-text attribute on', btn);
            return;
        }
        window.arpCopy(btn, text);
    };

    /* ─── Global event delegation for canonical data-actions ─────── */

    document.addEventListener('click', function(event) {
        var actionEl = event.target.closest('[data-action]');
        if (!actionEl) return;
        var action = actionEl.dataset.action;

        if (action === 'copy-project-path') {
            event.preventDefault();
            var text = actionEl.dataset.clipboardText || '';
            if (text) window.arpCopy(actionEl, text);
        } else if (action === 'toggle-part-raw') {
            event.preventDefault();
            var part = actionEl.closest('.viewer__part');
            if (!part) return;
            var rendered = part.querySelector('.viewer__part-rendered');
            var raw = part.querySelector('.viewer__part-raw');
            if (!rendered || !raw) return;
            var showingRaw = !rendered.hidden;
            rendered.hidden = showingRaw;
            raw.hidden = !showingRaw;
            actionEl.textContent = showingRaw ? 'Raw' : 'Rendered';
        } else if (action === 'viewer-fullscreen') {
            event.preventDefault();
            var viewer = actionEl.closest('.viewer');
            if (!viewer) return;
            var body = viewer.querySelector('.viewer__body, .viewer__markdown, .viewer__raw, .viewer__part-content');
            if (!body) return;
            var win = window.open('', '_blank');
            if (win) {
                win.document.write('<html><head><title>Viewer</title><style>body{margin:0;font:14px/1.5 system-ui,sans-serif;}</style></head><body>' + body.innerHTML + '</body></html>');
                win.document.close();
            }
        } else if (action === 'reset-project-filters') {
            event.preventDefault();
            var form = actionEl.closest('form');
            if (form) {
                form.querySelectorAll('input[type="text"], input[type="search"]').forEach(function(input) {
                    input.value = '';
                });
                form.querySelectorAll('select').forEach(function(sel) {
                    sel.selectedIndex = 0;
                });
            }
        } else if (action === 'close-full-payload') {
            event.preventDefault();
            if (typeof window.closeFullPayloadViewer === 'function') {
                window.closeFullPayloadViewer();
            }
        }
    });

})();

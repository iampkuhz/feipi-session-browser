/* Session Detail — JS split wrapper.
 *
 * This file is retained as a compat entry so that existing <script> tags
 * and static-contract tests that read session-detail.js still resolve.
 * The actual code lives in session-detail/*.js modules loaded from the
 * template.
 *
 * Split modules (loaded in dependency order from session.html):
 *   namespace.js, dom.js, tabs.js, filters.js, lazy_rounds.js,
 *   attribution.js, payload.js, events.js, init.js
 *
 * The empty IIFE below ensures the file has a valid JS body (required by
 * dead-JS quality checks) and does not pollute the global scope.
 */
(function () {
  // All logic has been moved to session-detail/*.js modules.
})();

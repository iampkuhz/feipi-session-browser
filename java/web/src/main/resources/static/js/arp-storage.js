/**
 * arp-storage.js — localStorage wrapper for Agent Run Profiler.
 *
 * Loaded in <head> before other scripts so window.arpStorage is
 * available to any page that needs it.
 */
(function() {
    'use strict';
    var STORAGE_PREFIX = 'arp_';
    window.arpStorage = {
        get: function(key) {
            try {
                var raw = localStorage.getItem(STORAGE_PREFIX + key);
                return raw ? JSON.parse(raw) : null;
            } catch (e) { return null; }
        },
        set: function(key, value) {
            try {
                localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
            } catch (e) { /* storage full or disabled */ }
        },
        remove: function(key) {
            try {
                localStorage.removeItem(STORAGE_PREFIX + key);
            } catch (e) {}
        }
    };
})();

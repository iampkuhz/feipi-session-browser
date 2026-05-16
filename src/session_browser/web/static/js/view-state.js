/**
 * view-state.js — Density toggle & Saved Views
 *
 * 职责：
 * 1. density 切换（compact / comfortable），通过 body class + localStorage 持久化
 * 2. 简单 saved views（存储当前 URL 参数集合）
 *
 * 用法：
 *   // 初始化：恢复上一次 density 状态
 *   ViewState.init();
 *
 *   // 切换 density
 *   ViewState.toggleDensity();
 *
 *   // 读取当前 density
 *   ViewState.getDensity(); // 'compact' | 'comfortable'
 *
 *   // Saved Views
 *   ViewState.saveView('my-view');
 *   ViewState.loadView('my-view');
 *   ViewState.deleteView('my-view');
 *   ViewState.listViews(); // [{ name, url, savedAt }]
 */
(function () {
    'use strict';

    var STORAGE_PREFIX = 'arp_';
    var DENSITY_KEY = STORAGE_PREFIX + 'density';
    var VIEWS_KEY_PREFIX = STORAGE_PREFIX + 'view_';
    var VIEWS_LIST_KEY = STORAGE_PREFIX + 'views_list';

    var DEFAULT_DENSITY = 'compact';
    var DENSITY_CLASSES = {
        compact: '',
        comfortable: 'density-comfortable'
    };

    /* ── Density ─────────────────────────────────────────────── */

    function getDensity() {
        try {
            var saved = localStorage.getItem(DENSITY_KEY);
            return saved === 'comfortable' ? 'comfortable' : DEFAULT_DENSITY;
        } catch (e) {
            return DEFAULT_DENSITY;
        }
    }

    function setDensity(mode) {
        try {
            localStorage.setItem(DENSITY_KEY, mode);
        } catch (e) { /* storage full */ }
        applyDensity(mode);
    }

    function applyDensity(mode) {
        var cls = DENSITY_CLASSES[mode] || '';
        if (cls) {
            document.body.classList.add(cls);
        } else {
            document.body.classList.remove('density-comfortable');
        }
    }

    function toggleDensity() {
        var current = getDensity();
        var next = current === 'compact' ? 'comfortable' : 'compact';
        setDensity(next);
        updateToggleUI(next);
    }

    function updateToggleUI(mode) {
        var btn = document.getElementById('density-toggle');
        if (!btn) return;
        var isComfortable = mode === 'comfortable';
        btn.classList.toggle('density-toggle--active', isComfortable);
        btn.setAttribute('aria-pressed', String(isComfortable));
        btn.title = isComfortable ? '当前：宽松 · 点击切换为紧凑' : '当前：紧凑 · 点击切换为宽松';
    }

    /* ── Saved Views ────────────────────────────────────────── */

    function saveView(name) {
        if (!name) return false;
        var view = {
            name: name,
            url: window.location.search || window.location.pathname,
            savedAt: new Date().toISOString()
        };
        try {
            localStorage.setItem(VIEWS_LIST_KEY + ':' + name, JSON.stringify(view));
            var list = listViews();
            if (!list.some(function (v) { return v.name === name; })) {
                list.push({ name: name, savedAt: view.savedAt });
                localStorage.setItem(VIEWS_LIST_KEY, JSON.stringify(list));
            }
            return true;
        } catch (e) {
            return false;
        }
    }

    function loadView(name) {
        try {
            var raw = localStorage.getItem(VIEWS_LIST_KEY + ':' + name);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }

    function deleteView(name) {
        try {
            localStorage.removeItem(VIEWS_LIST_KEY + ':' + name);
            var list = listViews().filter(function (v) { return v.name !== name; });
            localStorage.setItem(VIEWS_LIST_KEY, JSON.stringify(list));
            return true;
        } catch (e) {
            return false;
        }
    }

    function listViews() {
        try {
            var raw = localStorage.getItem(VIEWS_LIST_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    /* ── Public API ─────────────────────────────────────────── */

    window.ViewState = {
        getDensity: getDensity,
        setDensity: setDensity,
        toggleDensity: toggleDensity,
        saveView: saveView,
        loadView: loadView,
        deleteView: deleteView,
        listViews: listViews,
        init: function () {
            var mode = getDensity();
            applyDensity(mode);
            updateToggleUI(mode);
        }
    };
})();

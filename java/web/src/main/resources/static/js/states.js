// states.js — Canonical page JS for state pages (404, error)
// ================================================================
//
// Behavior: 无 — 状态页面为纯静态内容，无需 JavaScript 行为。
//
//   - 404.html: 纯静态面板（图标、标题、描述、导航链接）
//   - error.html: 纯静态面板 + 原生 <details> 折叠（浏览器原生行为）
//
// 禁止 inline script/onclick，所有模板已验证无残留。
//
// 消费方: 404.html, error.html（通过 base.html 引用）
//
// 约束:
//   - 不含任何 inline event handler
//   - 零外部依赖，纯 vanilla JS，ES5 语法
//   - 不引入 React/Vue
// ================================================================
(function () {
  'use strict';

  // 状态页面为纯静态内容，当前无需初始化逻辑。
  // 如需添加行为（例如：自动返回倒计时、错误详情切换），请在此处扩展。
})();

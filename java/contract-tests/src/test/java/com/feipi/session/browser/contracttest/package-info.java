/**
 * 验收契约测试包。
 *
 * <p>包含从 Python 实现和测试提炼的中性契约验证。 每个测试类对应一组 acceptance contract row， 绑定 fixture、expected、owning task
 * 和 test id。
 *
 * <h2>模块边界</h2>
 *
 * <ul>
 *   <li>仅依赖 {@code test-support} 和 {@code core-domain}（测试范围）。
 *   <li>不得依赖 production 实现模块（normalized-io、attribution、index 等）。
 *   <li>不得包含 production 源代码。
 * </ul>
 *
 * <h2>契约覆盖</h2>
 *
 * <p>S2 阶段建立以下契约族：
 *
 * <ul>
 *   <li>Normalized session artifact schema 约束（AC-01 至 AC-09）
 *   <li>Agent adapter snapshot 契约（AC-10 至 AC-13）
 *   <li>模块拓扑与依赖约束（AC-17 至 AC-18）
 * </ul>
 */
package com.feipi.session.browser.contracttest;

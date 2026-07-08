/**
 * 升级与回滚契约测试。
 *
 * <p>验证 {@code DatabaseUpgrader} 的升级流程满足以下契约：
 *
 * <ul>
 *   <li>旧发布 fixture 可升级（schema migration 幂等）。
 *   <li>注入失败可回滚（migration 失败时从备份恢复）。
 *   <li>不丢数据（升级后现有数据完整保留）。
 *   <li>重复升级幂等（多次升级结果一致）。
 * </ul>
 */
package com.feipi.session.browser.contracttest.upgrade;

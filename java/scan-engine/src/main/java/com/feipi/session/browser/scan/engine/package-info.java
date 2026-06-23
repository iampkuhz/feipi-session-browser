/**
 * Java 扫描引擎。
 *
 * <p>提供 full scan、incremental scan、后台分层扫描、跨进程锁和取消机制。
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.scan.engine.FullScanEngine} — 全量扫描
 *   <li>{@link com.feipi.session.browser.scan.engine.IncrementalScanEngine} — 增量扫描（支持取消和时钟注入）
 *   <li>{@link com.feipi.session.browser.scan.engine.BackgroundScanner} — 分层后台扫描调度
 *   <li>{@link com.feipi.session.browser.scan.engine.ScanLock} — 跨进程文件锁
 *   <li>{@link com.feipi.session.browser.scan.engine.ScanCancelToken} — 扫描取消令牌
 *   <li>{@link com.feipi.session.browser.scan.engine.TierConfig} — 层级窗口和间隔配置
 * </ul>
 */
package com.feipi.session.browser.scan.engine;

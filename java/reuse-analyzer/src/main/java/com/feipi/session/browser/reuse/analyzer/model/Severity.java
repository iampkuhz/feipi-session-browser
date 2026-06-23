package com.feipi.session.browser.reuse.analyzer.model;

/**
 * Finding 严重级别。
 *
 * <ul>
 *   <li>P0：阻断，不可 baseline。
 *   <li>P1：无 decision 时阻断，允许 baseline。
 *   <li>P2/P3：advisory，不阻断。
 * </ul>
 */
public enum Severity {
  P0,
  P1,
  P2,
  P3,
}

package com.feipi.session.browser.reuse.analyzer.model;

/**
 * 方法归属分类，基于方法对 owner type 的绑定强度。
 *
 * <ul>
 *   <li>OWNER_BOUND：方法访问 instance field、调用 owner private 方法、维护 owner invariant。
 *   <li>DETACHED_BEHAVIOR：方法只使用参数和 JDK API，可独立存在。
 *   <li>SHARED_CAPABILITY：方法实现通用基础能力（排序、编码、fingerprint 等）。
 *   <li>PROVIDER_SPECIFIC_CAPABILITY：方法实现特定 provider 能力，虽相似但语义不同。
 *   <li>FACTORY_OR_CONSTRUCTOR：工厂方法或构造器。
 *   <li>TRIVIAL_DELEGATION：纯委托方法（getter/setter/单行转发）。
 * </ul>
 */
public enum Ownership {
  OWNER_BOUND,
  DETACHED_BEHAVIOR,
  SHARED_CAPABILITY,
  PROVIDER_SPECIFIC_CAPABILITY,
  FACTORY_OR_CONSTRUCTOR,
  TRIVIAL_DELEGATION,
}

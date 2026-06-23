/**
 * {@code core-domain} 模块的领域模型包。
 *
 * <p>包含归一化 token 分解等不可变领域类型。 所有生产类型必须使用 {@code @DomainModel} 注解标注， 核心字段必须使用 {@code @CoreField}
 * 注解标注并提供中文 Javadoc。
 *
 * <h2>模块边界</h2>
 *
 * <ul>
 *   <li>零外部依赖：仅使用 JDK 标准库。
 *   <li>不得依赖其他 {@code java:} 子项目。
 *   <li>不得包含 I/O、网络或框架代码。
 * </ul>
 *
 * <h2>S2 契约冻结</h2>
 *
 * <p>以下类型已在 S1 冻结，S2 仅记录其消费者与生产者关系：
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.domain.NormalizedTokenBreakdown} — 写入方: {@code
 *       normalization-engine}; 消费方: {@code artifact-normalized}、{@code contract-tests}
 * </ul>
 */
package com.feipi.session.browser.domain;

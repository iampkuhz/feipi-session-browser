/**
 * {@code core-domain} 模块的领域模型包。
 *
 * <p>包含会话摘要、token 分解和项目统计等不可变领域类型。 所有生产类型必须使用 {@code @DomainModel} 注解标注， 核心字段必须使用
 * {@code @CoreField} 注解标注并提供中文 Javadoc。
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
 *   <li>{@link com.feipi.session.browser.domain.SessionSummary} &mdash; writer: index/writers;
 *       consumer: web, attribution
 *   <li>{@link com.feipi.session.browser.domain.NormalizedTokenBreakdown} &mdash; writer:
 *       domain/token_normalizer; consumer: attribution, web
 *   <li>{@link com.feipi.session.browser.domain.ProjectStats} &mdash; writer: index/queries;
 *       consumer: web/dashboard
 * </ul>
 */
package com.feipi.session.browser.domain;

/**
 * 归一化会话制品领域模型包。
 *
 * <p>包含归一化管线产出的不可变领域类型，对应 Python 端 {@code session_browser.normalized.models}
 * 模块的全部数据类。这些类型建模了归一化后的会话制品结构，包括调用、工具执行、源单元目录和顶层制品。
 *
 * <h2>模块边界</h2>
 *
 * <ul>
 *   <li>零外部依赖：仅使用 JDK 标准库。
 *   <li>不得依赖其他 {@code java:} 子项目。
 *   <li>不得包含 I/O、网络或框架代码。
 *   <li>不得引入 Jackson、Picocli、SQLite 等框架。
 * </ul>
 *
 * <h2>S2 迁移约定</h2>
 *
 * <ul>
 *   <li>所有生产类型使用 {@code @DomainModel} 注解。
 *   <li>影响业务语义的字段使用 {@code @CoreField} 注解。
 *   <li>集合类型使用不可变副本防御，大小上限为 {@link
 *       com.feipi.session.browser.domain.normalized.NormalizedConstants#MAX_COLLECTION_SIZE}。
 *   <li>区分 {@code absent}（{@code Optional} 为空）和 {@code empty}（空字符串）。
 *   <li>所有 record 紧凑构造器执行非空约束和不变量校验。
 * </ul>
 */
package com.feipi.session.browser.domain.normalized;

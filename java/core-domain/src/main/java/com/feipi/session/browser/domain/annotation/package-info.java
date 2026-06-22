/**
 * 领域模型标注包。
 *
 * <p>提供 {@code @DomainModel} 和 {@code @CoreField} 两个保留策略为 {@code CLASS} 的注解， 被架构测试在编译期消费，不需要运行时反射。
 *
 * <h2>约束</h2>
 *
 * <ul>
 *   <li>{@code @DomainModel} 仅用于 record、enum、sealed interface 或不可变类。
 *   <li>{@code @CoreField} 仅用于影响业务语义的字段或 record 组件。
 *   <li>标注类型不得依赖 {@code Lombok}、{@code Jackson}、{@code JPA}、{@code Spring} 等框架注解。
 * </ul>
 */
package com.feipi.session.browser.domain.annotation;

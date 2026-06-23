package com.feipi.session.browser.domain.annotation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标识 {@code core-domain} 模块中的正式领域模型类型。
 *
 * <p>该注解被架构测试消费，用于验证以下约束：
 *
 * <ul>
 *   <li>标注类型必须是 record、enum、sealed interface 或不可变类。
 *   <li>标注类型不得包含非不可变实例字段。
 *   <li>标注类型不得暴露公开 setter 方法。
 *   <li>标注类型不得依赖未经批准的框架注解。 当前允许的编译期注解仅为 {@code Lombok @Getter} 和 {@code @RequiredArgsConstructor}；
 *       其他框架注解（Jackson、{@code JPA}、{@code Spring} 等）仍被禁止。
 * </ul>
 *
 * <p>保留策略选择 {@code CLASS}：ArchUnit 通过字节码分析读取该注解， 不需要运行时反射保留；同时避免成为无意义的运行时元数据。
 *
 * <p>所有 {@code core-domain} 中的实际生产模型必须使用该注解。 未标注的非模型类型（工具类、常量类、注解本身）不得滥用。
 */
@Documented
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface DomainModel {}

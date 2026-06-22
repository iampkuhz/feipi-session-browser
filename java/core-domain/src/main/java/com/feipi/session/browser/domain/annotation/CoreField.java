package com.feipi.session.browser.domain.annotation;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标识领域模型中影响业务语义的核心字段。
 *
 * <p>核心字段是指影响以下维度的字段：业务标识、状态、顺序、归属、计量、 时间或外部契约。典型核心字段包括：ID、session key、agent/source
 * {@code type}、status、{@code scope}、parent/child 关系、timestamp、duration、token/{@code count}/{@code size}、path、
 * {@code locator}、hash、schema/{@code version}、持久化或序列化字段、跨模块传递的契约字段、 以及默认值或空值语义会影响行为的字段。
 *
 * <p>该注解被中文 Javadoc source-level 验证测试消费：标注字段必须有中文 Javadoc 或对应的中文 {@code @param}
 * 文档。标注但未提供中文文档的字段会导致验证失败。
 *
 * <p>保留策略选择 {@code CLASS}：source-level 测试通过编译器 API 读取源码树， 不需要运行时反射保留。
 *
 * <p>适用于普通 class 的 {@code private final} 字段和 record 组件。
 */
@Documented
@Retention(RetentionPolicy.CLASS)
@Target({ElementType.FIELD, ElementType.RECORD_COMPONENT})
public @interface CoreField {}

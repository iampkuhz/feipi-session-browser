/**
 * 归一化制品序列化与持久化包。
 *
 * <p>提供归一化会话制品（{@code NormalizedSessionArtifact}）的确定性 JSON 序列化和失败安全文件写入能力。 核心组件包括：
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.artifact.normalized.ArtifactConstants} — 模块常量定义。
 *   <li>{@link com.feipi.session.browser.artifact.normalized.ArtifactMeta} — 制品元数据不可变记录。
 *   <li>{@link com.feipi.session.browser.artifact.normalized.CanonicalJsonWriter} — 确定性 JSON 序列化器。
 *   <li>{@link com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter} — 失败安全文件写入器。
 * </ul>
 *
 * <h2>设计约束</h2>
 *
 * <ul>
 *   <li>确定性：同一输入始终产生相同的字节输出。Map key 排序、固定 UTF-8 编码、无时间戳混入数据文件。
 *   <li>失败安全：使用临时文件原子重命名模式写入，中间状态不可被识别为有效制品。
 *   <li>meta 后提交：数据文件先于 meta 文件写入，只有 meta 成功提交后制品才完整。
 * </ul>
 */
package com.feipi.session.browser.artifact.normalized;

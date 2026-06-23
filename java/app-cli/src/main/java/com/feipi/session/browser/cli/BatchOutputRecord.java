package com.feipi.session.browser.cli;

/**
 * 批量命令的 NDJSON 协议结果记录。
 *
 * <p>每处理一个候选项后向 stdout 写入一行 JSON 对象，序列化自该 record。成功时 {@code artifactPath} 指向实际 data 文件路径； 失败时
 * {@code error} 非 null，{@code status} 为 {@code "error"}。
 *
 * <p>协议字段说明：
 *
 * <ul>
 *   <li>{@code requestId}：对应输入行的请求标识，无请求关联时为空字符串
 *   <li>{@code sessionKey}：会话唯一标识键
 *   <li>{@code status}：处理状态：{@code "success"}、{@code "error"}、{@code "skipped"}
 *   <li>{@code artifactPath}：生成的归一化 data 文件绝对路径，失败时为 null
 *   <li>{@code error}：脱敏后的错误消息，成功时为 null
 *   <li>{@code contentHash}：data 文件 SHA-256 摘要，失败时为 null
 * </ul>
 *
 * @param requestId 请求标识，来自输入行的 requestId 字段或自动生成
 * @param sessionKey 会话唯一标识键
 * @param status 处理状态
 * @param artifactPath 生成的归一化 data 文件路径，失败时为 null
 * @param error 脱敏错误消息，成功时为 null
 * @param contentHash data 文件 SHA-256 摘要，失败时为 null
 */
record BatchOutputRecord(
    String requestId,
    String sessionKey,
    String status,
    String artifactPath,
    String error,
    String contentHash) {}

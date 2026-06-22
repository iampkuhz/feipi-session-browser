package com.feipi.session.browser.cli;

/**
 * 批量命令的 NDJSON 输出记录。
 *
 * <p>每处理一个候选项后向 stdout 写入一行 JSON 对象，序列化自该 record。成功时 {@code artifactPath} 非 null； 失败时 {@code error}
 * 非 null，{@code status} 为 {@code "error"}。
 *
 * @param sessionKey 会话唯一标识键
 * @param status 处理状态：{@code "success"} 或 {@code "error"}
 * @param artifactPath 生成的归一化制品文件路径，失败时为 null
 * @param error 错误消息，成功时为 null
 */
record BatchOutputRecord(String sessionKey, String status, String artifactPath, String error) {}

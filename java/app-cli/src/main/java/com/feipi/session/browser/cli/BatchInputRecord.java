package com.feipi.session.browser.cli;

/**
 * 批量命令的 NDJSON 输入记录。
 *
 * <p>从 stdin 读取的每行 JSON 对象反序列化为此 record。包含源标识和根目录路径两个必填字段。
 *
 * @param sourceId 源标识字符串，如 {@code "CLAUDE_CODE"}、{@code "CODEX"}、{@code "QODER"}
 * @param rootPath 会话数据根目录路径
 */
record BatchInputRecord(String sourceId, String rootPath) {}

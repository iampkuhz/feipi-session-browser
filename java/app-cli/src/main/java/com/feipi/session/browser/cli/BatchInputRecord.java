package com.feipi.session.browser.cli;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 批量命令的 NDJSON 输入记录。
 *
 * <p>从 stdin 读取的每行 JSON 对象反序列化为此 record。包含源标识和根目录路径两个必填字段，以及可选的请求标识。
 *
 * <p>使用 {@link JsonIgnoreProperties} 忽略未知字段，保证协议前向兼容。
 *
 * @param requestId 可选请求标识，缺失时由命令自动生成
 * @param sourceId 源标识字符串，如 {@code "CLAUDE_CODE"}、{@code "CODEX"}、{@code "QODER"}
 * @param rootPath 会话数据根目录路径
 */
@JsonIgnoreProperties(ignoreUnknown = true)
record BatchInputRecord(String requestId, String sourceId, String rootPath) {}

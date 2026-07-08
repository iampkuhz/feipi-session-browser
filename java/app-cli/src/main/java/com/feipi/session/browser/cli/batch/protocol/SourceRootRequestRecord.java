package com.feipi.session.browser.cli.batch.protocol;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 源根处理请求的 NDJSON 输入记录。
 *
 * <p>从 stdin 读取的每行 JSON 对象反序列化为此 record。包含源标识和根目录路径两个必填字段，以及可选的请求标识。
 *
 * @param requestId 可选请求标识，缺失时由 batch runner 自动生成
 * @param sourceId 源标识字符串，如 {@code "CLAUDE_CODE"}、{@code "CODEX"}、{@code "QODER"}
 * @param rootPath 会话数据根目录路径
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record SourceRootRequestRecord(String requestId, String sourceId, String rootPath) {}

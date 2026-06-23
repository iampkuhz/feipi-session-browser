package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;

/**
 * 纯函数归一化引擎。
 *
 * <p>将源适配器解析的 JSON 事件列表转换为不可变的 {@link NormalizedSessionArtifact}。 引擎不读写文件、不访问环境变量、不生成随机
 * ID。同一输入始终产生同一输出。
 *
 * <p>处理流程：
 *
 * <ol>
 *   <li>通过 {@link EventClassifier} 按事件类型分类
 *   <li>通过 {@link CallBuilder} 从助手消息构建 {@link NormalizedCall} 列表
 *   <li>通过 {@link CallBuilder} 匹配 {@code tool_use} 和 {@code tool_result} 构建 {@link
 *       NormalizedToolExecution} 列表
 *   <li>通过 {@link TokenAccountant} 提取 token 用量
 *   <li>合并输入诊断和未知事件诊断，组装最终制品
 * </ol>
 */
public final class NormalizationEngine {

  /**
   * 从 JSON 事件列表构建归一化制品。
   *
   * <p>{@code agent} 参数必须为合法的 agent 值（参见 {@link
   * com.feipi.session.browser.domain.normalized.NormalizedAgent}），例如 {@code "claude_code"}、 {@code
   * "codex"} 或 {@code "qoder"}。
   *
   * @param agent 产生事件的源适配器 agent 值（如 {@code "claude_code"}）
   * @param events 解析后的 JSON 事件列表，不得为 null
   * @param diagnostics 解析诊断列表，不得为 null
   * @param sourceFiles 源文件列表，不得为 null
   * @return 不可变的归一化会话制品
   * @throws NullPointerException 当任何列表参数为 null 时
   * @throws IllegalArgumentException 当 agent 值不合法时
   */
  public NormalizedSessionArtifact normalize(
      String agent,
      List<JsonNode> events,
      List<SourceDiagnostic> diagnostics,
      List<NormalizedSourceFile> sourceFiles) {

    Objects.requireNonNull(agent, "agent 不得为 null");
    Objects.requireNonNull(events, "events 不得为 null");
    Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
    Objects.requireNonNull(sourceFiles, "sourceFiles 不得为 null");

    // 1. 事件分类
    EventClassifier.ClassifiedEvents classified = EventClassifier.classify(events);

    // 2. 构建调用列表
    List<NormalizedCall> calls = CallBuilder.buildCalls(events, classified);

    // 3. 构建工具执行边列表
    List<NormalizedToolExecution> toolExecutions =
        CallBuilder.buildToolExecutions(events, classified, calls);

    // 4. 合并诊断：输入诊断 + 未知事件产生的诊断
    List<Map<String, Object>> allDiagnostics = new ArrayList<>();
    for (SourceDiagnostic diag : diagnostics) {
      allDiagnostics.add(toMap(diag));
    }
    for (JsonNode unknownEvent : classified.unknownEvents()) {
      String type = "unknown";
      JsonNode typeNode = unknownEvent.get("type");
      if (typeNode != null && typeNode.isTextual()) {
        type = typeNode.asText();
      }
      SourceDiagnostic unknownDiag =
          new SourceDiagnostic(
              ParseSeverity.WARNING,
              ParseIssueType.NON_OBJECT_SKIPPED,
              "Unknown event type: " + type,
              1,
              Optional.empty(),
              ParseIssueType.NON_OBJECT_SKIPPED.name(),
              "",
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty());
      allDiagnostics.add(toMap(unknownDiag));
    }

    // 5. 组装制品
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        agent,
        sourceFiles,
        Map.of(),
        calls,
        toolExecutions,
        allDiagnostics,
        Map.of(),
        Map.of());
  }

  private static Map<String, Object> toMap(SourceDiagnostic diag) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("severity", diag.severity().name());
    map.put("issueType", diag.issueType().name());
    map.put("message", diag.message());
    map.put("lineNo", diag.lineNo());
    map.put("code", diag.code());
    if (!diag.locator().isEmpty()) {
      map.put("locator", diag.locator());
    }
    diag.column().ifPresent(c -> map.put("column", c));
    diag.byteRangeStart().ifPresent(b -> map.put("byteRangeStart", b));
    diag.byteRangeEnd().ifPresent(b -> map.put("byteRangeEnd", b));
    diag.preview().ifPresent(p -> map.put("preview", p));
    return map;
  }
}

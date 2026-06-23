package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;

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

    // 5. 构建会话元数据：事件计数 + 聚合 token 用量 + 守恒计数
    Map<String, Object> session = buildSessionMap(agent, events, calls, toolExecutions);

    // 6. 构建源单元目录
    Map<String, SourceUnitCatalogEntry> sourceUnitCatalog = buildSourceUnitCatalog(sourceFiles);

    // 7. 组装制品
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        agent,
        sourceFiles,
        session,
        calls,
        toolExecutions,
        allDiagnostics,
        sourceUnitCatalog,
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

  /**
   * 构建工具与 token 守恒检查结果。
   *
   * <p>验证以下守恒属性：
   *
   * <ul>
   *   <li>声明的工具调用数 = 工具执行数（每个 tool_use 都有对应的执行记录）
   *   <li>聚合 token total 等于各调用分量之和
   * </ul>
   *
   * @param calls 已构建的调用列表
   * @param toolExecutions 已构建的工具执行列表
   * @return 不可变的守恒检查结果
   */
  static ConservationCheckResult buildConservationCheck(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {

    Set<String> declaredToolIds = new LinkedHashSet<>();
    Set<String> consumedResultIds = new LinkedHashSet<>();
    for (NormalizedCall call : calls) {
      declaredToolIds.addAll(call.response().toolCallIds());
      consumedResultIds.addAll(call.request().toolResultIds());
    }

    Set<String> executedToolIds = new LinkedHashSet<>();
    for (NormalizedToolExecution exec : toolExecutions) {
      executedToolIds.add(exec.toolCallId());
    }

    NormalizedCallUsage sessionUsage = aggregateUsage(calls);

    long expectedTotal = 0;
    for (NormalizedCall call : calls) {
      expectedTotal += call.usage().total();
    }

    return new ConservationCheckResult(
        declaredToolIds.size(),
        executedToolIds.size(),
        consumedResultIds.size(),
        sessionUsage.total() == expectedTotal);
  }

  /**
   * 从事件列表和调用数据构建会话元数据 map。
   *
   * <p>包含 agent 标识、事件总数、聚合后的 session 级 token 用量， 以及工具守恒计数。所有值均从输入确定性派生，保证相同输入产生相同输出。
   *
   * @param agent 产生事件的源适配器 agent 值
   * @param events 原始事件列表
   * @param calls 已构建的调用列表
   * @param toolExecutions 已构建的工具执行列表
   * @return 不可变的会话元数据 map
   */
  private static Map<String, Object> buildSessionMap(
      String agent,
      List<JsonNode> events,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> toolExecutions) {
    Map<String, Object> session = new LinkedHashMap<>();
    session.put("agent", agent);
    session.put("eventCount", events.size());

    NormalizedCallUsage sessionUsage = aggregateUsage(calls);
    session.put("totalTokens", sessionUsage.total());

    // 工具守恒计数
    ConservationCheckResult conservation = buildConservationCheck(calls, toolExecutions);
    session.put("declaredTools", conservation.declaredTools());
    session.put("executedTools", conservation.executedTools());
    session.put("consumedResults", conservation.consumedResults());

    return Map.copyOf(session);
  }

  /**
   * 从源文件列表构建源单元目录。
   *
   * <p>为每个源文件创建一个目录条目，key 为文件路径。条目携带最小必填字段， 保证确定性和可溯源性。
   *
   * @param sourceFiles 源文件列表
   * @return 不可变的目录 map
   */
  private static Map<String, SourceUnitCatalogEntry> buildSourceUnitCatalog(
      List<NormalizedSourceFile> sourceFiles) {
    if (sourceFiles.isEmpty()) {
      return Map.of();
    }
    Map<String, SourceUnitCatalogEntry> catalog = new LinkedHashMap<>();
    for (int i = 0; i < sourceFiles.size(); i++) {
      NormalizedSourceFile sf = sourceFiles.get(i);
      catalog.put(sf.path(), buildSourceUnitCatalogEntry(sf, i));
    }
    return Map.copyOf(catalog);
  }

  /**
   * 为单个源文件构建目录条目。
   *
   * @param sf 源文件
   * @param index 文件在列表中的序号，用作 eventOrder
   * @return 不可变的目录条目
   */
  private static SourceUnitCatalogEntry buildSourceUnitCatalogEntry(
      NormalizedSourceFile sf, int index) {
    return new SourceUnitCatalogEntry(
        sf.path(),
        sf.path(),
        sf.path(),
        sf.role(),
        "",
        "request",
        index,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.empty(),
        null,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  /**
   * 聚合调用列表中的 token 用量。
   *
   * @param calls 调用列表
   * @return 聚合后的 session 级 token 用量
   */
  private static NormalizedCallUsage aggregateUsage(List<NormalizedCall> calls) {
    List<NormalizedCallUsage> usages = new ArrayList<>(calls.size());
    for (NormalizedCall call : calls) {
      usages.add(call.usage());
    }
    return TokenAccountant.aggregate(usages);
  }

  /**
   * 工具与 token 守恒检查结果。
   *
   * <p>记录归一化制品中工具声明、执行和 token 用量的守恒状态， 供下游消费者验证归一化正确性。
   *
   * @param declaredTools 跨所有调用声明的唯一工具调用数
   * @param executedTools 工具执行记录中的唯一工具调用数
   * @param consumedResults 跨所有调用消费的唯一工具结果数
   * @param tokensConserved 聚合 token total 是否等于各调用分量之和
   */
  record ConservationCheckResult(
      int declaredTools, int executedTools, int consumedResults, boolean tokensConserved) {

    ConservationCheckResult {
      if (declaredTools < 0) {
        throw new IllegalArgumentException(
            "declaredTools must be non-negative; got " + declaredTools);
      }
      if (executedTools < 0) {
        throw new IllegalArgumentException(
            "executedTools must be non-negative; got " + executedTools);
      }
      if (consumedResults < 0) {
        throw new IllegalArgumentException(
            "consumedResults must be non-negative; got " + consumedResults);
      }
    }
  }
}

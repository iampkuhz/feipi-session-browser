package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 顶层归一化会话制品。
 *
 * <p>建模持久化在 SQLite 索引旁的归一化会话制品。索引扫描在 JSON 持久化之前创建该数据传输根对象， 查询和验证路径水合它以强制执行公开的制品合约。制品是不可变的、带 schema
 * 版本的， 并要求调用标识符唯一。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code schemaVersion} 必须等于 {@link NormalizedConstants#SCHEMA_VERSION}。
 *   <li>{@code agent} 必须为合法的 {@link NormalizedAgent} 值。
 *   <li>{@code calls} 中的 {@code callId} 必须唯一。
 *   <li>所有集合字段使用不可变副本，大小不超过上限。
 *   <li>只有归一化引擎可完成最终组装，adapter 不得绕过。
 * </ul>
 *
 * @param schemaVersion 归一化制品 schema 版本号
 * @param agent 产生制品的源适配器名称
 * @param sourceFiles 对制品有贡献的物理源文件列表
 * @param session 会话元数据，保持为公开 JSON 数据
 * @param calls 归一化 LLM 调用列表，按遍历顺序排列
 * @param toolExecutions 调用声明和消费的工具调用边列表
 * @param diagnostics 非致命解析器诊断信息列表
 * @param sourceUnitCatalog 按源单元键索引的目录条目映射
 * @param sourceUnitSequences 命名的源单元键序列映射
 */
@DomainModel
public record NormalizedSessionArtifact(
    @CoreField String schemaVersion,
    @CoreField NormalizedAgent agent,
    @CoreField List<NormalizedSourceFile> sourceFiles,
    @CoreField NormalizedSessionMetadata session,
    @CoreField List<NormalizedCall> calls,
    @CoreField List<NormalizedToolExecution> toolExecutions,
    List<NormalizedDiagnostic> diagnostics,
    Map<String, SourceUnitCatalogEntry> sourceUnitCatalog,
    Map<String, List<String>> sourceUnitSequences) {

  /**
   * 兼容旧调用点的构造器。
   *
   * @param schemaVersion schema 版本
   * @param agent agent 类型
   * @param sourceFiles 源文件列表
   * @param session 会话元数据 map
   * @param calls 调用列表
   * @param toolExecutions 工具执行列表
   * @param diagnostics 诊断 map 或 {@link NormalizedDiagnostic} 列表
   * @param sourceUnitCatalog 源单元目录
   * @param sourceUnitSequences 源单元序列
   */
  public NormalizedSessionArtifact(
      String schemaVersion,
      NormalizedAgent agent,
      List<NormalizedSourceFile> sourceFiles,
      Map<String, Object> session,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> toolExecutions,
      List<?> diagnostics,
      Map<String, SourceUnitCatalogEntry> sourceUnitCatalog,
      Map<String, List<String>> sourceUnitSequences) {
    this(
        schemaVersion,
        agent,
        sourceFiles,
        NormalizedSessionMetadata.fromMap(session),
        calls,
        toolExecutions,
        normalizedDiagnostics(diagnostics),
        sourceUnitCatalog,
        sourceUnitSequences);
  }

  /**
   * 规范化诊断列表。
   *
   * @param diagnostics 诊断 map 或结构化诊断列表
   * @return 不可变诊断列表
   */
  private static List<NormalizedDiagnostic> normalizedDiagnostics(List<?> diagnostics) {
    if (diagnostics == null) {
      return List.of();
    }
    return diagnostics.stream().map(NormalizedSessionArtifact::normalizedDiagnostic).toList();
  }

  /**
   * 规范化单条诊断。
   *
   * @param diagnostic 诊断 map 或结构化诊断对象
   * @return 结构化诊断
   */
  @SuppressWarnings("unchecked")
  private static NormalizedDiagnostic normalizedDiagnostic(Object diagnostic) {
    if (diagnostic instanceof NormalizedDiagnostic normalizedDiagnostic) {
      return normalizedDiagnostic;
    }
    if (diagnostic instanceof Map<?, ?> map) {
      return NormalizedDiagnostic.fromMap((Map<String, Object>) map);
    }
    throw new IllegalArgumentException("unsupported diagnostic element: " + diagnostic);
  }

  /**
   * 紧凑构造器，验证顶层不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 schema 版本不匹配、agent 非法或 callId 重复时
   */
  public NormalizedSessionArtifact {
    Objects.requireNonNull(schemaVersion, "schemaVersion 不得为 null");
    if (!NormalizedConstants.SCHEMA_VERSION.equals(schemaVersion)) {
      throw new IllegalArgumentException(
          "schemaVersion must be " + NormalizedConstants.SCHEMA_VERSION + "; got " + schemaVersion);
    }
    Objects.requireNonNull(agent, "agent 不得为 null");

    Objects.requireNonNull(session, "session 不得为 null");

    // sourceFiles 防御性拷贝
    List<NormalizedSourceFile> sourceFilesCopy =
        sourceFiles == null ? Collections.emptyList() : List.copyOf(sourceFiles);
    if (sourceFilesCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "sourceFiles size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    sourceFiles = sourceFilesCopy;

    // 调用列表防御性拷贝 + callId 唯一性验证
    Objects.requireNonNull(calls, "calls 不得为 null");
    List<NormalizedCall> callsCopy = List.copyOf(calls);
    if (callsCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "calls size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    Set<String> callIds = new HashSet<>();
    for (NormalizedCall call : callsCopy) {
      if (!callIds.add(call.callId())) {
        throw new IllegalArgumentException(
            "normalized callId values must be unique; duplicate: " + call.callId());
      }
    }
    calls = callsCopy;

    // toolExecutions 防御性拷贝
    List<NormalizedToolExecution> toolsCopy =
        toolExecutions == null ? Collections.emptyList() : List.copyOf(toolExecutions);
    if (toolsCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "toolExecutions size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    toolExecutions = toolsCopy;

    // 诊断信息防御性拷贝
    List<NormalizedDiagnostic> diagCopy =
        diagnostics == null ? Collections.emptyList() : List.copyOf(diagnostics);
    if (diagCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "diagnostics size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    diagnostics = diagCopy;

    // sourceUnitCatalog 防御性拷贝，大小受限
    Map<String, SourceUnitCatalogEntry> catalogCopy =
        sourceUnitCatalog == null ? Map.of() : Map.copyOf(sourceUnitCatalog);
    if (catalogCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "sourceUnitCatalog size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    sourceUnitCatalog = catalogCopy;

    // sourceUnitSequences 防御性拷贝，大小受限
    Map<String, List<String>> sequencesCopy =
        sourceUnitSequences == null ? Map.of() : Map.copyOf(sourceUnitSequences);
    if (sequencesCopy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "sourceUnitSequences size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    sourceUnitSequences = sequencesCopy;
  }
}

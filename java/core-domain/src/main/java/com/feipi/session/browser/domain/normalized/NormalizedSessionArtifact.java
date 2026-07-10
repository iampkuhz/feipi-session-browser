package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
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
    /* 归一化制品 schema 版本号。 */
    @NotBlank @CoreField String schemaVersion,

    /* 产生制品的源适配器名称。 */
    @NotNull @CoreField NormalizedAgent agent,

    /* 对制品有贡献的物理源文件列表。 */
    @NotNull @CoreField List<NormalizedSourceFile> sourceFiles,

    /* 会话元数据，保持为公开 JSON 数据。 */
    @NotNull @CoreField NormalizedSessionMetadata session,

    /* 归一化 LLM 调用列表，按遍历顺序排列。 */
    @NotNull @CoreField List<NormalizedCall> calls,

    /* 调用声明和消费的工具调用边列表。 */
    @NotNull @CoreField List<NormalizedToolExecution> toolExecutions,

    /* 非致命解析器诊断信息列表。 */
    @NotNull List<NormalizedDiagnostic> diagnostics,

    /* 按源单元键索引的目录条目映射。 */
    @NotNull Map<String, SourceUnitCatalogEntry> sourceUnitCatalog,

    /* 命名的源单元键序列映射。 */
    @NotNull Map<String, List<String>> sourceUnitSequences) {

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
   * @throws IllegalArgumentException 当 schema 版本不匹配或 callId 重复时
   */
  public NormalizedSessionArtifact {
    // schema 版本跨字段规则
    if (!NormalizedConstants.SCHEMA_VERSION.equals(schemaVersion)) {
      throw new IllegalArgumentException(
          "schemaVersion must be " + NormalizedConstants.SCHEMA_VERSION + "; got " + schemaVersion);
    }

    // sourceFiles 防御性拷贝
    sourceFiles =
        ImmutableCopies.boundedListOrEmpty(
            sourceFiles, NormalizedConstants.MAX_COLLECTION_SIZE, "sourceFiles");

    // 调用列表防御性拷贝 + callId 唯一性验证
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
    toolExecutions =
        ImmutableCopies.boundedListOrEmpty(
            toolExecutions, NormalizedConstants.MAX_COLLECTION_SIZE, "toolExecutions");

    // 诊断信息防御性拷贝
    diagnostics =
        ImmutableCopies.boundedListOrEmpty(
            diagnostics, NormalizedConstants.MAX_COLLECTION_SIZE, "diagnostics");

    // sourceUnitCatalog 防御性拷贝，大小受限
    sourceUnitCatalog =
        ImmutableCopies.boundedMapOrEmpty(
            sourceUnitCatalog, NormalizedConstants.MAX_COLLECTION_SIZE, "sourceUnitCatalog");

    // sourceUnitSequences 防御性拷贝，大小受限
    sourceUnitSequences =
        ImmutableCopies.boundedMapOrEmpty(
            sourceUnitSequences, NormalizedConstants.MAX_COLLECTION_SIZE, "sourceUnitSequences");

    try {
      ValidationSupport.validateCanonicalConstructor(
          NormalizedSessionArtifact.class,
          schemaVersion,
          agent,
          sourceFiles,
          session,
          calls,
          toolExecutions,
          diagnostics,
          sourceUnitCatalog,
          sourceUnitSequences);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 将 Jakarta 校验违规翻译为向后兼容的异常类型。
   *
   * @param e 原始校验违规异常
   */
  private static void translateValidation(ConstraintViolationException e) {
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
      if (type == NotBlank.class) {
        throw new IllegalArgumentException(field + " 不得为空");
      }
    }
    throw e;
  }
}

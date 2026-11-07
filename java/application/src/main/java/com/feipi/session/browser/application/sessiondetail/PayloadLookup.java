package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * payload 内容查找表。
 *
 * <p>从归一化制品构建 payload_id 到内容的映射。支持按可见性策略控制内容截断和敏感字段 masking。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>payload_id 格式由 {@link PayloadSource} 在创建时验证。
 *   <li>敏感字段 masking 由 {@link SensitiveFieldPolicy} 统一管理。
 *   <li>本类信任已验证的 payload_id 和制品数据。
 * </ul>
 */
public final class PayloadLookup {

  private final Map<String, PayloadEntry> entries;

  private PayloadLookup(Map<String, PayloadEntry> entries) {
    // 使用 Collections.unmodifiableMap 保留 LinkedHashMap 插入顺序，
    // 避免 Map.copyOf 在 Java 25 全测试套件中丢失顺序。
    this.entries = Collections.unmodifiableMap(new LinkedHashMap<>(entries));
  }

  /**
   * 从归一化制品构建 payload 查找表。
   *
   * <p>为每个有 sourceRef 的调用创建请求和响应条目。 标准可见性下遮盖敏感字段；两种模式均保留完整的已记录文本，不假报截断。
   *
   * @param artifact 已验证的归一化制品
   * @param visibility 可见性策略
   * @return payload 查找表
   */
  public static PayloadLookup fromArtifact(
      NormalizedSessionArtifact artifact, PayloadVisibility visibility) {
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    boolean truncated = false;
    SensitiveFieldPolicy policy = SensitiveFieldPolicy.fromVisibility(visibility);
    Map<String, PayloadEntry> map = new LinkedHashMap<>();

    Map<String, String> toolResultContents =
        PayloadCallContentExtractor.extractToolResultContents(artifact);
    Map<String, ToolInputContents.Input> toolInputs = ToolInputContents.all(artifact);

    for (NormalizedCall call : artifact.calls()) {
      boolean isSubagent = call.scope().name().toLowerCase().contains("subagent");
      String prefix = isSubagent ? "sa" : "main";

      String reqContent = PayloadCallContentExtractor.extractRequestContent(call, artifact);
      String reqPayloadId = prefix + ":req:" + call.callId();
      PayloadSourceKind requestKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST;
      var requestReading = PayloadCallContentExtractor.readingText(call, artifact, true);
      map.put(
          reqPayloadId,
          new PayloadEntry(
              reqPayloadId,
              requestKind,
              call.callId(),
              policy.applyMasking(reqContent),
              truncated,
              readingBlock(policy, requestReading.text()),
              requestReading.unconfirmedContext()));

      String respContent = PayloadCallContentExtractor.extractResponseContent(call, artifact);
      String respPayloadId = prefix + ":resp:" + call.callId();
      PayloadSourceKind responseKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
      map.put(
          respPayloadId,
          new PayloadEntry(
              respPayloadId,
              responseKind,
              call.callId(),
              policy.applyMasking(respContent),
              truncated,
              readingBlock(
                  policy, PayloadCallContentExtractor.readingText(call, artifact, false).text()),
              false));
    }

    for (var input : toolInputs.values()) {
      String id = "tool:input:" + input.id();
      map.put(
          id,
          new PayloadEntry(
              id,
              PayloadSourceKind.TOOL_INPUT,
              input.id(),
              policy.applyMasking(input.input()),
              false));
    }
    for (var exec : artifact.toolExecutions()) {
      String toolPayloadId = "tool:result:" + exec.toolCallId();
      String toolContent = toolResultContents.getOrDefault(exec.toolCallId(), "");
      map.put(
          toolPayloadId,
          new PayloadEntry(
              toolPayloadId,
              PayloadSourceKind.TOOL_RESULT,
              exec.toolCallId(),
              policy.applyMasking(toolContent),
              truncated));
      String inputId = "tool:input:" + exec.toolCallId();
      ToolInputContents.Input input = toolInputs.get(exec.toolCallId());
      map.putIfAbsent(
          inputId,
          new PayloadEntry(
              inputId,
              PayloadSourceKind.TOOL_INPUT,
              exec.toolCallId(),
              policy.applyMasking(input == null ? "" : input.input()),
              false));
    }

    for (var round :
        com.feipi.session.browser.index.api.query.RoundAssembler.buildRounds(artifact, 0)) {
      List<NormalizedCall> calls =
          artifact.calls().stream().filter(call -> round.calls().contains(call.callId())).toList();
      List<NormalizedCall> mainCalls =
          calls.stream().filter(call -> call.scope() == CallScope.MAIN).toList();
      if (!mainCalls.isEmpty()) calls = mainCalls;
      addRoundPayload(map, calls, round.roundIndex(), "req", PayloadSourceKind.LLM_REQUEST);
      addRoundPayload(map, calls, round.roundIndex(), "resp", PayloadSourceKind.LLM_RESPONSE);
    }

    return new PayloadLookup(map);
  }

  private static void addRoundPayload(
      Map<String, PayloadEntry> entries,
      List<NormalizedCall> calls,
      int roundIndex,
      String side,
      PayloadSourceKind kind) {
    List<String> contents =
        calls.stream()
            .map(
                call -> {
                  String prefix = call.scope() == CallScope.SUBAGENT ? "sa" : "main";
                  PayloadEntry entry = entries.get(prefix + ":" + side + ":" + call.callId());
                  return entry == null || entry.content().isEmpty()
                      ? ""
                      : call.callKey() + " · " + call.callId() + "\n" + entry.content();
                })
            .filter(content -> !content.isEmpty())
            .toList();
    String id = "round:" + side + ":" + roundIndex;
    List<ReadingBlock> reading =
        calls.stream()
            .flatMap(
                call -> {
                  String prefix = call.scope() == CallScope.SUBAGENT ? "sa" : "main";
                  PayloadEntry entry = entries.get(prefix + ":" + side + ":" + call.callId());
                  return entry == null
                      ? java.util.stream.Stream.<ReadingBlock>empty()
                      : entry.reading().stream()
                          .map(block -> new ReadingBlock(call.callKey(), block.text()));
                })
            .toList();
    entries.put(
        id,
        new PayloadEntry(
            id,
            kind,
            "round:" + roundIndex,
            String.join("\n\n", contents),
            false,
            reading,
            side.equals("req")
                && calls.stream()
                    .anyMatch(
                        call -> {
                          String prefix = call.scope() == CallScope.SUBAGENT ? "sa" : "main";
                          var entry = entries.get(prefix + ":req:" + call.callId());
                          return entry != null && entry.unconfirmedContext();
                        })));
  }

  static List<ReadingBlock> readingBlock(SensitiveFieldPolicy policy, String text) {
    return text.isBlank() ? List.of() : List.of(new ReadingBlock("", policy.applyMasking(text)));
  }

  /**
   * 有角色依据的阅读正文；工具和系统上下文仍在原文中。
   *
   * @param label 多个调用并列时显示的简短标识
   * @param text 按可见性规则遮盖后的对话文本
   */
  public record ReadingBlock(String label, String text) {}

  /**
   * 查找指定 payload_id 的内容。
   *
   * @param payloadId payload 标识符
   * @return payload 条目，不存在时返回 empty
   */
  public Optional<PayloadEntry> lookup(String payloadId) {
    Objects.requireNonNull(payloadId, "payloadId 不得为 null");
    return Optional.ofNullable(entries.get(payloadId));
  }

  /**
   * 查找指定调用 ID 的全部 payload 条目。
   *
   * @param callId 归一化调用 ID
   * @return 匹配的条目列表
   */
  public List<PayloadEntry> lookupByCallId(String callId) {
    Objects.requireNonNull(callId, "callId 不得为 null");
    return entries.values().stream().filter(e -> callId.equals(e.callId())).toList();
  }

  /** 查找表中的条目总数。 */
  public int size() {
    return entries.size();
  }

  /** 全部 payload_id 列表。 */
  public List<String> allPayloadIds() {
    return List.copyOf(entries.keySet());
  }

  /**
   * 单条 payload 内容条目。
   *
   * @param payloadId 全局唯一的 payload 标识符
   * @param kind payload 类型分类
   * @param callId 关联的归一化调用 ID
   * @param content payload 内容（可能已被 masking）
   * @param truncated 内容是否确实被裁剪（字段遮盖不算截断）
   * @param reading 可与原文分开展示的对话片段
   * @param unconfirmedContext 原始请求中是否含无法确认归属的独立上下文样式段落
   */
  public record PayloadEntry(
      /* 全局唯一的 payload 标识符。 */
      @NotBlank String payloadId,

      /* payload 类型分类。 */
      @NotNull PayloadSourceKind kind,

      /* 关联的归一化调用 ID。 */
      @NotBlank String callId,

      /* payload 内容（可能已被 masking）。 */
      String content,

      /* 内容是否被截断。 */
      boolean truncated,
      List<ReadingBlock> reading,
      boolean unconfirmedContext) {

    /** 构造无需单独对话正文的工具或诊断记录。 */
    public PayloadEntry(
        String payloadId,
        PayloadSourceKind kind,
        String callId,
        String content,
        boolean truncated) {
      this(payloadId, kind, callId, content, truncated, List.of(), false);
    }

    /**
     * 紧凑构造器，验证条目不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public PayloadEntry {
      ValidationSupport.validateCanonicalConstructor(
          PayloadEntry.class,
          payloadId,
          kind,
          callId,
          content,
          truncated,
          reading,
          unconfirmedContext);
      content = content == null ? "" : content;
      reading = List.copyOf(reading);
    }
  }
}

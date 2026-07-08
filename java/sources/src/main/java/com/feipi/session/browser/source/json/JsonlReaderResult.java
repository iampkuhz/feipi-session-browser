package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * JSONL 读取器的解析结果。
 *
 * <p>封装一次 JSONL 解析的完整输出：解析成功的 JSON 事件列表、 诊断信息列表、统计信息和停止原因。不可变 record。
 *
 * <p>此类是读取器级别的输出载体，不属于核心领域模型，因此不使用 {@code @DomainModel} 标注。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code events} 不得为 null，元素按文件出现顺序排列。
 *   <li>{@code diagnostics} 不得为 null，元素按行号顺序排列。
 *   <li>{@code stats} 不得为 null。
 * </ul>
 *
 * @param events 解析成功的 JSON 对象列表（仅包含 {@code isObject()} 返回真的节点）
 * @param diagnostics 解析过程中收集的诊断信息
 * @param stats 解析统计信息
 * @param stoppedByLimit 当达到 {@code maxRecords} 上限后停止解析时为 {@code true}
 */
public record JsonlReaderResult(
    List<JsonNode> events,
    List<SourceDiagnostic> diagnostics,
    JsonlStats stats,
    boolean stoppedByLimit) {

  /**
   * 紧凑构造器，验证不变量并创建不可变副本。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public JsonlReaderResult {
    Objects.requireNonNull(events, "events 不得为 null");
    Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
    Objects.requireNonNull(stats, "stats 不得为 null");
    events = Collections.unmodifiableList(events);
    diagnostics = Collections.unmodifiableList(diagnostics);
  }

  /**
   * 向后兼容构造器（默认 {@code stoppedByLimit = false}）。
   *
   * @param events 解析成功的 JSON 对象列表
   * @param diagnostics 解析过程中收集的诊断信息
   * @param stats 解析统计信息
   */
  public JsonlReaderResult(
      List<JsonNode> events, List<SourceDiagnostic> diagnostics, JsonlStats stats) {
    this(events, diagnostics, stats, false);
  }
}

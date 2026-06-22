package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * JSONL 读取器的解析结果。
 *
 * <p>封装一次 JSONL 解析的完整输出：解析成功的 JSON 事件列表、 诊断信息列表和统计信息。不可变 record。
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
 */
@DomainModel
public record JsonlReaderResult(
    @CoreField List<JsonNode> events,
    @CoreField List<SourceDiagnostic> diagnostics,
    @CoreField JsonlStats stats) {

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
}

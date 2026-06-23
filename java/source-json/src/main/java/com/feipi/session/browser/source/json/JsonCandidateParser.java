package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.BiConsumer;
import java.util.function.Function;

/**
 * JSONL 候选项解析模板。
 *
 * <p>该模板集中处理取消、文件存在性、JSONL 读取、源中性 {@link SourceRecord} 构建和 {@link SourceResult.Success} 组装；各 source
 * adapter 只提供 provider 特有的 event type 判定和诊断逻辑，避免三个 adapter 复制相同解析骨架。
 */
public final class JsonCandidateParser {

  /** 防止实例化。 */
  private JsonCandidateParser() {}

  /** 针对单条 JSON 事件补充 provider 特有诊断。 */
  @FunctionalInterface
  public interface DiagnosticCollector {

    /**
     * 收集当前事件的 provider 特有诊断。
     *
     * @param event JSON 事件节点
     * @param eventIndex 事件在源输入中的零基序号
     * @param eventType 已转换为源中性的事件类型
     * @param locator 源文件定位符
     * @param diagnostics 可追加的诊断列表
     */
    void collect(
        JsonNode event,
        int eventIndex,
        String eventType,
        String locator,
        List<SourceDiagnostic> diagnostics);
  }

  /**
   * 解析单个候选 JSONL 文件。
   *
   * @param candidate 待解析候选项
   * @param cancellation 可选取消信号；为 null 时按未取消处理
   * @param jsonlReader JSONL 读取器
   * @param eventTypeExtractor provider 特有事件类型提取器
   * @param diagnosticCollector provider 特有逐事件诊断收集器
   * @param completionDiagnostics provider 特有收尾诊断收集器
   * @return 密封解析结果
   */
  public static SourceResult parse(
      Candidate candidate,
      SourceAdapter.CancellationSignal cancellation,
      JsonlReader jsonlReader,
      Function<JsonNode, String> eventTypeExtractor,
      DiagnosticCollector diagnosticCollector,
      BiConsumer<List<SourceDiagnostic>, Integer> completionDiagnostics) {
    Objects.requireNonNull(candidate, "candidate 不得为 null");
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    Objects.requireNonNull(eventTypeExtractor, "eventTypeExtractor 不得为 null");
    Objects.requireNonNull(diagnosticCollector, "diagnosticCollector 不得为 null");
    Objects.requireNonNull(completionDiagnostics, "completionDiagnostics 不得为 null");

    if (cancellation != null && cancellation.isCancelled()) {
      return new SourceResult.Skipped(List.of(), "解析已取消");
    }

    Path filePath = Path.of(candidate.fingerprint().locator());
    if (!Files.exists(filePath)) {
      return new SourceResult.Skipped(List.of(), "文件不存在: " + filePath);
    }

    try {
      JsonlReaderResult result = jsonlReader.read(filePath);
      String locator = candidate.fingerprint().locator();
      List<SourceDiagnostic> diagnostics = new ArrayList<>(result.diagnostics());
      List<SourceRecord> records = new ArrayList<>(result.events().size());

      for (int eventIndex = 0; eventIndex < result.events().size(); eventIndex++) {
        JsonNode event = result.events().get(eventIndex);
        String eventType = eventTypeExtractor.apply(event);
        diagnosticCollector.collect(event, eventIndex, eventType, locator, diagnostics);
        records.add(JsonSourceRecordMapper.toSourceRecord(locator, eventIndex, event, eventType));
      }

      completionDiagnostics.accept(diagnostics, result.events().size());
      return new SourceResult.Success(
          diagnostics, result.events().size(), records, candidate.fingerprint(), locator);
    } catch (IOException e) {
      String detail = "文件读取失败: " + filePath + " - " + e.getMessage();
      return new SourceResult.Fatal(List.of(), detail);
    }
  }
}

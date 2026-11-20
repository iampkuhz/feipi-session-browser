package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/** 离线导出必须保留公开关系和已存储的计量精度。 */
class ContentExportEvidenceTest {
  @Test
  void capturedResultsLinkToExactInputReferencesAcrossEveryWindow() throws Exception {
    var content = localContent(45, false);
    String html = exportLocal(content);
    assertThat(html)
        .contains(
            "输入正文", "本地记录中的工具结果", "包含此结果的本地输入", "本地记录#2", "本地记录#3", "未单列输入正文", "原始请求全文", "工具结果全文");
    var reader = new SessionContentReader(content, 0);
    var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(results.occurrences()).hasSize(5);
    var firstTargets =
        reader.localResultRelations(results.occurrences().getFirst().occurrenceId(), 0, 100, null);
    assertThat(firstTargets.targets())
        .hasSize(46)
        .extracting(
            com.feipi.session.browser.application.sessiondetail.PayloadLookup.ResultTarget::callId)
        .containsOnly("c2", "c4");
    var secondTargets =
        reader.localResultRelations(results.occurrences().get(1).occurrenceId(), 0, 100, null);
    assertThat(secondTargets.targets())
        .hasSize(1)
        .extracting(
            com.feipi.session.browser.application.sessiondetail.PayloadLookup.ResultTarget::callId)
        .containsExactly("c3");
    var sections = html.split("<details><summary>Result ·");
    assertThat(sections).hasSize(6);
    String firstReference = referenceAnchor(firstTargets.targets().getFirst().referenceId());
    String secondReference = referenceAnchor(secondTargets.targets().getFirst().referenceId());
    assertThat(sections[1])
        .contains("href=\"#" + firstReference + "\"")
        .doesNotContain("href=\"#" + secondReference + "\"");
    assertThat(sections[2])
        .contains("href=\"#" + secondReference + "\"")
        .doesNotContain("href=\"#" + firstReference + "\"");
    assertThat(html).contains("SYNTHETIC-INPUT-TAIL");
    for (var result : results.occurrences()) {
      long cursor = 0;
      do {
        var page = reader.localResultRelations(result.occurrenceId(), cursor, 20, null);
        for (var target : page.targets()) {
          String anchor = referenceAnchor(target.referenceId());
          assertThat(html).contains("href=\"#" + anchor + "\"", "id=\"" + anchor + "\"");
          assertThat(Pattern.compile("id=\"" + anchor + "\"").matcher(html).results().count())
              .isEqualTo(1);
        }
        if (page.nextCursor() == null) break;
        cursor = page.nextCursor();
      } while (true);
    }
    assertThat(html)
        .contains("显式空结果", "结果正文缺失", "本地未记录包含此结果的输入", "SAME-TAIL", "EOF-TAIL")
        .doesNotContain(
            "synthetic#event",
            "result_source_unit_key",
            "覆盖范围: complete",
            "来源身份: confirmed",
            "关系身份: confirmed");
    var evidence = Path.of("../../tmp/session-execution-topic/local-results-export-v211");
    if (Files.isDirectory(evidence)) Files.writeString(evidence.resolve("synthetic.html"), html);
  }

  @Test
  void incompleteReferencesDisclosePartialCoverageWithoutInventingLinks() throws Exception {
    String html = exportLocal(localContent(1, true));
    assertThat(html)
        .contains("当前已确认的输入不代表完整集合", "结果正文缺失", "<details><summary>关系范围说明</summary>")
        .doesNotContain("覆盖范围: partial");
  }

  @Test
  void unknownAndAmbiguousIdentityNeverBecomeConfirmedZeroOrLinks() throws Exception {
    var base = localArtifact(1, false);
    for (String mutation : List.of("unknown", "ambiguous")) {
      var artifact =
          new NormalizedSessionArtifact(
              base.schemaVersion(),
              base.agent(),
              base.sourceFiles(),
              mutation.equals("unknown") ? Map.of() : base.session(),
              base.calls(),
              mutation.equals("ambiguous")
                  ? List.of(base.toolExecutions().getFirst(), base.toolExecutions().getFirst())
                  : base.toolExecutions(),
              base.diagnostics(),
              base.sourceUnitCatalog(),
              base.sourceUnitSequences());
      String html = exportLocal(NormalizedSessionContent.fromArtifact(artifact));
      String tools = html.substring(html.indexOf("<details id=\"tool-"));
      assertThat(tools)
          .contains(
              mutation.equals("ambiguous") ? "来源记录存在冲突，无法唯一确认结果身份" : "结果的来源身份尚未确认", "尚不能确认包含此结果的输入")
          .doesNotContain("href=\"#reference-", "本地未记录包含此结果的输入");
      if (mutation.equals("unknown"))
        assertThat(html).contains("尚未能单列工具结果引用").doesNotContain("当前未记录工具结果引用");
    }
  }

  @Test
  void bothVisibilitiesKeepSafeReadingRawAndResultTails() throws Exception {
    var base = localArtifact(1, false);
    var catalog = new LinkedHashMap<>(base.sourceUnitCatalog());
    var source = catalog.get(localKey(2));
    catalog.put(
        source.unitKey(),
        new SourceUnitCatalogEntry(
            source.unitKey(),
            source.originPath(),
            source.canonicalSourceLocator(),
            source.unitType(),
            source.candidate(),
            source.direction(),
            source.eventOrder(),
            source.partIndex(),
            source.byteRange(),
            source.contentHash(),
            source.timestamp(),
            source.label(),
            source.priority(),
            source.preview(),
            Optional.of(
                "<script>synthetic</script> & \"quoted\" ".repeat(1000)
                    + "password=synthetic-secret\nSAFE-TAIL"),
            source.payload(),
            source.subSource(),
            source.sourceCandidate(),
            source.diagnostics()));
    var artifact =
        new NormalizedSessionArtifact(
            base.schemaVersion(),
            base.agent(),
            base.sourceFiles(),
            base.session(),
            base.calls(),
            base.toolExecutions(),
            base.diagnostics(),
            catalog,
            base.sourceUnitSequences());
    var content = NormalizedSessionContent.fromArtifact(artifact);
    for (var visibility : PayloadVisibility.values()) {
      var bytes = new ByteArrayOutputStream();
      try (var snapshot = ContentExportSnapshot.html(content, 0, visibility, 4 * 1024 * 1024)) {
        snapshot.copyTo(bytes);
      }
      String html = bytes.toString(StandardCharsets.UTF_8);
      assertThat(html)
          .contains(
              "&lt;script&gt;synthetic&lt;/script&gt; &amp; &quot;quoted&quot;",
              "SAFE-TAIL",
              "原始请求全文",
              "工具结果全文")
          .doesNotContain("<script>", "synthetic-secret");
    }
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> ContentExportSnapshot.html(content, 0, PayloadVisibility.FULL, 1024))
        .isInstanceOf(ContentExportSnapshot.LimitExceededException.class);
  }

  @Test
  void metadataIsBuiltOnceAndExportOffsetsAvoidPerReferenceReplay() throws Exception {
    var passes = new ArrayList<Integer>();
    for (int repeats : List.of(1, 45)) {
      var base = localContent(repeats, false);
      var opens = new AtomicInteger();
      var closes = new AtomicInteger();
      var counted =
          new NormalizedSessionContent() {
            @Override
            public NormalizedContentHeader header() {
              return base.header();
            }

            @Override
            public ContentCursor openCursor() throws IOException {
              opens.incrementAndGet();
              var delegate = base.openCursor();
              return new ContentCursor() {
                @Override
                public boolean hasNext() throws IOException {
                  return delegate.hasNext();
                }

                @Override
                public NormalizedContentUnit next() throws IOException {
                  return delegate.next();
                }

                @Override
                public void close() throws IOException {
                  closes.incrementAndGet();
                  delegate.close();
                }
              };
            }
          };
      assertThat(exportLocal(counted)).contains("SAME-TAIL");
      assertThat(closes.get()).isEqualTo(opens.get());
      assertThat(opens.get()).isLessThanOrEqualTo(8);
      passes.add(opens.get());
    }
    assertThat(passes.getFirst()).isEqualTo(passes.getLast());
    System.out.println("SYNTHETIC_EXPORT_CURSOR_PASSES " + passes);
  }

  @Test
  void targetScopeComesFromCapturedSubagentCall() throws Exception {
    var base = localArtifact(1, false);
    var calls =
        base.calls().stream()
            .map(
                call ->
                    new NormalizedCall(
                        call.callId(),
                        call.callIndex(),
                        call.callKey(),
                        CallScope.SUBAGENT,
                        Optional.empty(),
                        Optional.empty(),
                        Optional.empty(),
                        "synthetic",
                        Optional.empty(),
                        call.usage(),
                        call.request(),
                        call.response(),
                        call.sourceUnitRefRanges(),
                        call.sourceUnits(),
                        Map.of(),
                        Map.of(),
                        Optional.of("synthetic-executor"),
                        Optional.empty()))
            .toList();
    var tool =
        new NormalizedToolExecution(
            "t",
            "synthetic-tool",
            CallScope.SUBAGENT,
            "c1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            750,
            List.of(),
            Optional.of("synthetic-executor"));
    var artifact =
        new NormalizedSessionArtifact(
            base.schemaVersion(),
            base.agent(),
            base.sourceFiles(),
            base.session(),
            calls,
            List.of(tool),
            base.diagnostics(),
            base.sourceUnitCatalog(),
            base.sourceUnitSequences());
    String html = exportLocal(NormalizedSessionContent.fromArtifact(artifact));
    assertThat(html)
        .contains("本地记录#2 · 子上下文", "href=\"#reference-")
        .doesNotContain("本地记录#2 · 主上下文");
  }

  private static String referenceAnchor(String id) throws Exception {
    return "reference-"
        + HexFormat.of()
            .formatHex(
                MessageDigest.getInstance("SHA-256").digest(id.getBytes(StandardCharsets.UTF_8)));
  }

  private static String exportLocal(NormalizedSessionContent content) throws Exception {
    var bytes = new ByteArrayOutputStream();
    try (var snapshot =
        ContentExportSnapshot.html(content, 0, PayloadVisibility.FULL, 4 * 1024 * 1024)) {
      snapshot.copyTo(bytes);
    }
    return bytes.toString(StandardCharsets.UTF_8);
  }

  private static NormalizedSessionContent localContent(int repeats, boolean missingRef) {
    return NormalizedSessionContent.fromArtifact(localArtifact(repeats, missingRef));
  }

  private static NormalizedSessionArtifact localArtifact(int repeats, boolean missingRef) {
    var calls =
        List.of(
            localCall(
                1,
                List.of(),
                List.of(Map.of("role", "user", "type", "text", "text", "SYNTHETIC-INPUT-TAIL"))),
            localCall(
                2,
                Collections.nCopies(repeats, localKey(1)),
                List.of(
                    Map.of(
                        "type",
                        "tool_result",
                        "role",
                        "user",
                        "tool_call_id",
                        "t",
                        "text",
                        "SAME-TAIL",
                        "result_source_unit_key",
                        localKey(1)))),
            localCall(
                3, missingRef ? List.of(localKey(2), "missing") : List.of(localKey(2)), List.of()),
            localCall(4, List.of(localKey(1)), List.of()));
    var catalog = new LinkedHashMap<String, SourceUnitCatalogEntry>();
    for (int i = 1; i <= 5; i++) {
      var entry =
          new SourceUnitCatalogEntry(
              localKey(i),
              "synthetic.jsonl",
              "synthetic#event[" + i + "]",
              "tool_result",
              "",
              SourceUnitDirection.REQUEST,
              i,
              0,
              ByteRange.empty(),
              "",
              Optional.empty(),
              Optional.of("t"),
              50,
              Optional.empty(),
              Optional.ofNullable(i == 5 ? null : i == 4 ? "" : i == 3 ? "EOF-TAIL" : "SAME-TAIL"),
              Map.of("type", "tool_result", "tool_call_id", "t"),
              Optional.empty(),
              Optional.empty(),
              List.of());
      catalog.put(entry.unitKey(), entry);
    }
    var tool =
        new NormalizedToolExecution(
            "t",
            "synthetic-tool",
            CallScope.MAIN,
            "c1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            750,
            List.of(),
            Optional.empty());
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CODEX,
        List.of(),
        Map.of("session_key", "codex:synthetic-export"),
        calls,
        List.of(tool),
        List.of(),
        catalog,
        Map.of());
  }

  private static String localKey(int index) {
    return "tool-result:" + index + ":synthetic#event[" + index + "]";
  }

  private static NormalizedCall localCall(
      int index, List<String> refs, List<Map<String, Object>> sources) {
    return new NormalizedCall(
        "c" + index,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        refs.isEmpty()
            ? List.of()
            : List.of(
                new SourceUnitRefRange(
                    Optional.empty(), 0, refs.size(), refs, Optional.of("user"))),
        sources,
        Map.of(),
        Map.of());
  }

  @Test
  void scopeParentSubagentAndToolOwnersRemainDistinctAndPayloadsHaveIdentity() throws Exception {
    var main =
        ContentExportReplayTest.call(
            0, CallScope.MAIN, List.of(), Map.of(), NormalizedCallUsage.empty());
    var child =
        ContentExportReplayTest.call(
            1, CallScope.SUBAGENT, List.of(), Map.of(), NormalizedCallUsage.empty());
    var tool =
        new NormalizedToolExecution(
            "tool-1",
            "shell",
            CallScope.SUBAGENT,
            "call-1",
            Optional.of("call-0"),
            Optional.empty(),
            Optional.empty(),
            0,
            List.of(),
            Optional.of("agent-child"));
    var content =
        new ContentExportReplayTest.CountingContent(
            List.of(
                ContentExportReplayTest.unit(0, List.of(main), List.of(), Map.of(), List.of()),
                ContentExportReplayTest.unit(1, List.of(child), List.of(), Map.of(), List.of()),
                ContentExportReplayTest.unit(2, List.of(), List.of(tool), Map.of(), List.of())),
            2,
            1,
            0,
            0);
    String html = ContentExportReplayTest.export(content);
    assertThat(html)
        .contains(
            "main:req:call-0",
            "main:resp:call-0",
            "sa:req:call-1",
            "sa:resp:call-1",
            "tool:input:tool-1",
            "tool:result:tool-1",
            "parent-tool",
            "agent-child",
            "delegate");
    // 关系字段用于区分归属语义，不能仅凭两个调用身份都出现在正文中判定保真。
    assertThat(html)
        .contains(
            "scope",
            "main",
            "subagent",
            "parentCallId",
            "parentToolCallId",
            "declaredByCallId",
            "resultConsumedByCallId",
            "subagentId");
    assertThat(html).doesNotContain("completed", "succeeded");
    assertThat(html).contains("<p>来源：<a href=\"#input-", "\">模型输入</a>", "\">模型输出</a>");
  }

  @Test
  void unresolvedToolOwnerKeepsEvidenceWithoutModelSourceLinks() throws Exception {
    var main =
        ContentExportReplayTest.call(
            0, CallScope.MAIN, List.of(), Map.of(), NormalizedCallUsage.empty());
    for (String owner : List.of("unknown", "missing-call")) {
      var tool =
          new NormalizedToolExecution(
              "orphan-tool",
              "shell",
              CallScope.SUBAGENT,
              owner,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              500,
              List.of(),
              Optional.of("agent-child"));
      var content =
          new ContentExportReplayTest.CountingContent(
              List.of(
                  ContentExportReplayTest.unit(0, List.of(main), List.of(), Map.of(), List.of()),
                  ContentExportReplayTest.unit(1, List.of(), List.of(tool), Map.of(), List.of())),
              1,
              1,
              0,
              0);
      String html = ContentExportReplayTest.export(content);
      String evidence = html.substring(html.indexOf("<details id=\"tool-"));
      assertThat(evidence)
          .contains("来源未确认", "declaredByCallId: " + owner, "500ms", "命令或参数", "执行结果")
          .doesNotContain("href=\"#input-", "href=\"#output-");
    }
  }

  @Test
  void unknownUnavailableEstimatedAndProviderReportedZeroKeepDifferentPrecision() throws Exception {
    var states = List.of("unknown", "unavailable", "estimated", "provider_reported");
    var units = new ArrayList<NormalizedContentUnit>();
    for (int i = 0; i < states.size(); i++) {
      var provenance =
          new TokenProvenance(
              states.get(i),
              states.get(i),
              states.get(i),
              states.get(i),
              i == 2 ? "synthetic-estimator" : "",
              i == 2 ? 1 : 0,
              i == 1 ? 1 : 0,
              i == 0 ? 1 : 0);
      var call =
          ContentExportReplayTest.call(
              i, CallScope.MAIN, List.of(), provenance.toMetadata(), NormalizedCallUsage.empty());
      units.add(ContentExportReplayTest.unit(i, List.of(call), List.of(), Map.of(), List.of()));
    }
    String html =
        ContentExportReplayTest.export(
            new ContentExportReplayTest.CountingContent(units, 4, 0, 0, 0));
    var summaries =
        Pattern.compile("<summary>([^<]*? · tokens.*?)</summary>", Pattern.DOTALL)
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .toList();
    assertThat(summaries).hasSize(4);
    assertThat(summaries.get(0)).contains("call-0", "N/A", "unknown").doesNotContain("tokens 0");
    assertThat(summaries.get(1))
        .contains("call-1", "N/A", "unavailable")
        .doesNotContain("tokens 0");
    assertThat(summaries.get(2)).contains("call-2", "0", "Estimated");
    assertThat(summaries.get(3)).contains("call-3", "tokens 0", "provider_reported");
    assertThat(html).contains("synthetic-estimator", "Partial");
    assertThat(html).doesNotContain("Total tokens: 0</p>");
  }

  @Test
  void mixedPrecisionWithoutCoverageFlagsNeverBecomesProviderReported() throws Exception {
    var precision =
        Map.<String, Object>of(
            "freshInputTokenPrecision",
            "mixed",
            "cacheReadTokenPrecision",
            "mixed",
            "cacheWriteTokenPrecision",
            "mixed",
            "outputTokenPrecision",
            "mixed");
    var call =
        ContentExportReplayTest.call(
            0, CallScope.MAIN, List.of(), precision, NormalizedCallUsage.empty());
    String html =
        ContentExportReplayTest.export(
            new ContentExportReplayTest.CountingContent(
                List.of(
                    ContentExportReplayTest.unit(0, List.of(call), List.of(), Map.of(), List.of())),
                1,
                0,
                0,
                0));
    var summary =
        Pattern.compile("<summary>([^<]*? · tokens.*?)</summary>", Pattern.DOTALL)
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .findFirst()
            .orElseThrow();
    assertThat(summary).contains("Partial", "mixed").doesNotContain("provider_reported");
    String total = html.substring(html.lastIndexOf("<p>Total tokens:"));
    assertThat(total).contains("Partial", "mixed").doesNotContain("provider_reported");
  }

  @Test
  void quotedCookieAndApiKeyAreMaskedForBothVisibilities() throws Exception {
    for (var visibility : PayloadVisibility.values()) {
      var call =
          new NormalizedCall(
              "security",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.of("turn"),
              "synthetic",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(
                  Map.of(
                      "role",
                      "assistant",
                      "type",
                      "text",
                      "text",
                      "{\"Cookie\":\"SID=synthetic-cookie\",\"X-API-Key\":\"synthetic-credential\"}"
                          + " readable-body")),
              Map.of(),
              Map.of());
      var content =
          new ContentExportReplayTest.CountingContent(
              List.of(
                  ContentExportReplayTest.unit(0, List.of(call), List.of(), Map.of(), List.of())),
              1,
              0,
              0,
              0);
      var bytes = new ByteArrayOutputStream();
      try (var snapshot = ContentExportSnapshot.html(content, 1, visibility, 1024 * 1024)) {
        snapshot.copyTo(bytes);
      }
      assertThat(bytes.toString(StandardCharsets.UTF_8))
          .as("quoted credentials at %s", visibility)
          .contains("readable-body", "[REDACTED]")
          .doesNotContain("synthetic-cookie", "synthetic-credential");
    }
  }

  @Test
  void collectorCloseFailureDoesNotPublishOrLeakSnapshot(
      @org.junit.jupiter.api.io.TempDir Path directory) throws Exception {
    var failure = new IOException("synthetic close failure");
    var published = new java.util.concurrent.atomic.AtomicBoolean();
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> {
              try (var snapshot =
                  ContentExportSnapshot.createClosing(
                      directory,
                      1024,
                      output -> output.write(42),
                      () -> {
                        throw failure;
                      })) {
                assertThat(snapshot.size()).isEqualTo(1);
                published.set(true);
              }
            })
        .isSameAs(failure);
    assertThat(published).isFalse();
    try (var files = Files.list(directory)) {
      assertThat(files.toList()).isEmpty();
    }
  }

  @Test
  void writeAndCloseFailureRetainOriginalAndSuppressedAndCleanSnapshot(
      @org.junit.jupiter.api.io.TempDir Path directory) throws Exception {
    var write = new IOException("synthetic write failure");
    var close = new IOException("synthetic close failure");
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () ->
                ContentExportSnapshot.createClosing(
                    directory,
                    1024,
                    output -> {
                      output.write(42);
                      throw write;
                    },
                    () -> {
                      throw close;
                    }))
        .isSameAs(write)
        .satisfies(failure -> assertThat(failure.getSuppressed()).containsExactly(close));
    try (var files = Files.list(directory)) {
      assertThat(files.toList()).isEmpty();
    }
  }
}

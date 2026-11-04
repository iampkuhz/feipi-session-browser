package com.feipi.session.browser.application.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.diagnostics.AnomalyDetector;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.ImportedSessionAnalysis;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportPort;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 独立应用用例只读取导入端口，并复用既有详情与异常检测。 */
class ImportedSessionUseCaseTest {
  @Test
  void assemblesImportedContextWithAnomaliesAndDelegatesLifecycle() throws Exception {
    var metadata =
        new ImportedSessionMetadata(
            "opaque-import",
            NormalizedAgent.CLAUDE_CODE,
            "synthetic.jsonl",
            "original",
            123,
            Instant.EPOCH);
    var row =
        new SessionRow(
            "import:opaque-import",
            "claude_code",
            "original",
            "synthetic.jsonl",
            "",
            "独立分析",
            "",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:01Z",
            0,
            0,
            0,
            "synthetic",
            "",
            "imported",
            1,
            1,
            1,
            5,
            12,
            4,
            3,
            24,
            1,
            0,
            0,
            0,
            "imports/opaque-import/upload.jsonl");
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            Map.of("userMessageCount", 1),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var analysis = new ImportedSessionAnalysis(metadata, row, artifact);
    var port = new MemoryPort(analysis);
    try (var useCase = new ImportedSessionUseCase(port)) {
      assertThat(
              useCase.create(
                  new ByteArrayInputStream(new byte[0]), "ignored", NormalizedAgent.CLAUDE_CODE))
          .isSameAs(metadata);
      assertThat(useCase.find(metadata.importId())).contains(metadata);
      assertThat(useCase.limits()).isEqualTo(ImportLimits.defaults());
      var context =
          useCase
              .getDetailContextWithAnomalies(metadata.importId(), PayloadVisibility.FULL)
              .orElseThrow();
      assertThat(context.detail().sessionRow()).isSameAs(row);
      assertThat(context.artifact()).isSameAs(artifact);
      assertThat(context.anomalies()).isEqualTo(AnomalyDetector.detect(row));
      assertThat(context.detail().artifactPath()).isEqualTo("import:opaque-import");
      assertThat(context.detail().visibility()).isEqualTo(PayloadVisibility.FULL);
      assertThat(useCase.getDetailContext("missing", PayloadVisibility.STANDARD)).isEmpty();
      assertThat(useCase.delete(metadata.importId())).isTrue();
      assertThat(useCase.getDetailContext(metadata.importId(), PayloadVisibility.FULL)).isEmpty();
    }
    assertThat(port.closed).isTrue();
  }

  /** 不连接数据库或个人查询端口的合成导入存储。 */
  private static final class MemoryPort implements SessionImportPort {
    private ImportedSessionAnalysis value;
    private boolean closed;

    private MemoryPort(ImportedSessionAnalysis value) {
      this.value = value;
    }

    @Override
    public ImportedSessionAnalysis create(
        InputStream input, String filename, NormalizedAgent source) {
      return value;
    }

    @Override
    public Optional<ImportedSessionAnalysis> find(String importId) {
      return value != null && value.metadata().importId().equals(importId)
          ? Optional.of(value)
          : Optional.empty();
    }

    @Override
    public boolean delete(String importId) {
      if (find(importId).isEmpty()) return false;
      value = null;
      return true;
    }

    @Override
    public ImportLimits limits() {
      return ImportLimits.defaults();
    }

    @Override
    public void close() {
      closed = true;
      value = null;
    }
  }
}

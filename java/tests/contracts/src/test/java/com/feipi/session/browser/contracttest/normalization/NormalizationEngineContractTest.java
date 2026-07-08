package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.normalization.NormalizationEngine;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

/** NormalizationEngine 纯函数契约测试。 */
class NormalizationEngineContractTest {

  @Test
  void emptyEventsProduceValidArtifact() {
    NormalizationEngine engine = new NormalizationEngine();
    NormalizedSessionArtifact artifact =
        engine.normalize(
            NormalizedAgent.CLAUDE_CODE,
            Collections.emptyList(),
            Collections.emptyList(),
            Collections.emptyList());
    assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(artifact.agent()).isEqualTo(NormalizedAgent.CLAUDE_CODE);
    assertThat(artifact.calls()).isEmpty();
  }

  @Test
  void deterministicOutput() {
    NormalizationEngine engine = new NormalizationEngine();
    SourceRecord record = SourceRecord.of("contract#event[0]", 0, "assistant");

    NormalizedSessionArtifact first =
        engine.normalize(
            NormalizedAgent.CODEX,
            List.of(record),
            Collections.emptyList(),
            Collections.emptyList());
    NormalizedSessionArtifact second =
        engine.normalize(
            NormalizedAgent.CODEX,
            List.of(record),
            Collections.emptyList(),
            Collections.emptyList());

    assertThat(first.calls().size()).isEqualTo(second.calls().size());
    assertThat(first.schemaVersion()).isEqualTo(second.schemaVersion());
  }

  @Test
  void publicNormalizeSignatureIsSourceNeutral() {
    Method[] methods = NormalizationEngine.class.getMethods();

    assertThat(methods)
        .filteredOn(method -> method.getName().equals("normalize"))
        .allSatisfy(method -> assertThat(method.toGenericString()).doesNotContain("JsonNode"));
  }
}

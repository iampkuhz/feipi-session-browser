package com.feipi.session.browser.contracttest.artifactnormalized;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.artifact.normalized.CanonicalJsonWriter;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.util.Collections;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** CanonicalJsonWriter 确定性序列化契约测试。 */
class CanonicalJsonWriterContractTest {

  @Test
  void deterministicSerialization() {
    NormalizedSessionArtifact artifact = createMinimalArtifact();
    CanonicalJsonWriter writer = new CanonicalJsonWriter();
    byte[] first = writer.serialize(artifact);
    byte[] second = writer.serialize(artifact);
    assertThat(first).isEqualTo(second);
  }

  @Test
  void mapKeysSorted() {
    NormalizedSessionArtifact artifact = createMinimalArtifact();
    CanonicalJsonWriter writer = new CanonicalJsonWriter();
    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
    // schemaVersion 应出现在 agent 之前（字母序）
    assertThat(json.indexOf("schemaVersion")).isLessThan(json.indexOf("\"agent\""));
  }

  private NormalizedSessionArtifact createMinimalArtifact() {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        Collections.emptyList(),
        Map.of("session_key", "test-123"),
        Collections.emptyList(),
        Collections.emptyList(),
        Collections.emptyList(),
        Collections.emptyMap(),
        Collections.emptyMap());
  }
}

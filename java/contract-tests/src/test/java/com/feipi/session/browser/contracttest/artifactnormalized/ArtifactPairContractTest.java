package com.feipi.session.browser.contracttest.artifactnormalized;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.artifact.normalized.WriteResult;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Collections;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 完整 artifact pair 的消费端 fail-closed 契约测试。 */
class ArtifactPairContractTest {

  @TempDir Path tempDir;

  private final NormalizedArtifactWriter writer =
      new NormalizedArtifactWriter(
          Clock.fixed(Instant.parse("2024-06-15T10:30:00Z"), ZoneOffset.UTC));

  @Test
  void consumerRejectsDataWithoutMetaAfterCrashWindow() throws IOException {
    WriteResult result = writer.write(tempDir, artifact("contract-crash-window"), Map.of());
    Files.delete(result.metaPath());

    assertThat(Files.exists(result.dataPath())).isTrue();
    assertThat(writer.validate(result.dataPath(), result.metaPath())).isFalse();
  }

  @Test
  void consumerRejectsInconsistentMetaPair() throws IOException {
    WriteResult result = writer.write(tempDir, artifact("contract-inconsistent-meta"), Map.of());
    String meta = Files.readString(result.metaPath(), StandardCharsets.UTF_8);
    Files.writeString(
        result.metaPath(),
        meta.replace("\"contentSize\":" + result.contentSize(), "\"contentSize\":0"),
        StandardCharsets.UTF_8);

    assertThat(writer.validate(result.dataPath(), result.metaPath())).isFalse();
  }

  @Test
  void collisionSafeNamesKeepCompletePairsDistinct() throws IOException {
    WriteResult colon = writer.write(tempDir, artifact("contract:name"), Map.of());
    WriteResult star = writer.write(tempDir, artifact("contract*name"), Map.of());

    assertThat(colon.dataPath()).isNotEqualTo(star.dataPath());
    assertThat(writer.validate(colon.dataPath(), colon.metaPath())).isTrue();
    assertThat(writer.validate(star.dataPath(), star.metaPath())).isTrue();
  }

  private static NormalizedSessionArtifact artifact(String sessionKey) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        Collections.emptyList(),
        Map.of("session_key", sessionKey),
        Collections.emptyList(),
        Collections.emptyList(),
        Collections.emptyList(),
        Collections.emptyMap(),
        Collections.emptyMap());
  }
}

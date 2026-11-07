package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;

/** 验证续页标记不能静默回到首页，也不能跨快照或筛选范围复用。 */
class SessionContentCursorTest {
  @Test
  void resumesBeyondLegacyArtifactLimitWithoutOffsetLoss() {
    String scope = "synthetic-generation-1|claude_code:synthetic|full|payloads|all";
    String token = SessionContentCursor.encode(scope, 10234L);
    assertThat(SessionContentCursor.decode(token, scope)).isEqualTo(10234L);
  }

  @Test
  void rejectsGenerationVisibilityAndSectionChanges() {
    String scope = "generation-1|synthetic|full|payloads|all";
    String token = SessionContentCursor.encode(scope, 500);
    for (String changed :
        new String[] {
          "generation-2|synthetic|full|payloads|all",
          "generation-1|synthetic|masked|payloads|all",
          "generation-1|synthetic|full|rounds|all",
          "generation-1|synthetic|full|payloads|hidden"
        }) {
      assertThatIllegalArgumentException()
          .isThrownBy(() -> SessionContentCursor.decode(token, changed));
    }
  }

  @Test
  void rejectsMalformedAndNegativeOffsetsRatherThanReturningFirstPage() {
    assertThatIllegalArgumentException().isThrownBy(() -> SessionContentCursor.encode("scope", -1));
    assertThatIllegalArgumentException()
        .isThrownBy(() -> SessionContentCursor.decode("not-a-valid-cursor", "scope"));
    assertThatIllegalArgumentException().isThrownBy(() -> SessionContentCursor.decode("", "scope"));
  }
}

package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** 过滤器契约测试。 */
class FilterTest {

  @Nested
  class AgentFilterTests {

    @Test
    void noneIsUnfiltered() {
      assertThat(AgentFilter.NONE.isUnfiltered()).isTrue();
      assertThat(AgentFilter.NONE.agent()).isEmpty();
    }

    @Test
    void ofValidAgent() {
      AgentFilter f = AgentFilter.of("claude_code");
      assertThat(f.agent()).isEqualTo("claude_code");
      assertThat(f.isUnfiltered()).isFalse();
    }

    @Test
    void ofEmptyStringIsUnfiltered() {
      AgentFilter f = AgentFilter.of("");
      assertThat(f.isUnfiltered()).isTrue();
    }

    @Test
    void ofWhitespaceAroundValueRejected() {
      assertThatThrownBy(() -> AgentFilter.of(" claude_code "))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("前导或尾随空白");
    }

    @Test
    void ofNullRejected() {
      assertThatThrownBy(() -> AgentFilter.of(null)).isInstanceOf(NullPointerException.class);
    }

    @Test
    void equalsAndHashCode() {
      assertThat(AgentFilter.of("claude_code")).isEqualTo(AgentFilter.of("claude_code"));
      assertThat(AgentFilter.of("claude_code").hashCode())
          .isEqualTo(AgentFilter.of("claude_code").hashCode());
    }

    @Test
    void toStringForUnfiltered() {
      assertThat(AgentFilter.NONE.toString()).isEqualTo("AgentFilter[*]");
    }

    @Test
    void toStringForFiltered() {
      assertThat(AgentFilter.of("codex").toString()).isEqualTo("AgentFilter[codex]");
    }
  }

  @Nested
  class ProjectFilterTests {

    @Test
    void noneIsUnfiltered() {
      assertThat(ProjectFilter.NONE.isUnfiltered()).isTrue();
    }

    @Test
    void ofValidProject() {
      ProjectFilter f = ProjectFilter.of("my-project");
      assertThat(f.projectKey()).isEqualTo("my-project");
      assertThat(f.isUnfiltered()).isFalse();
    }

    @Test
    void ofWhitespaceRejected() {
      assertThatThrownBy(() -> ProjectFilter.of(" my-project "))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void equalsAndHashCode() {
      assertThat(ProjectFilter.of("p1")).isEqualTo(ProjectFilter.of("p1"));
    }
  }

  @Nested
  class ModelFilterTests {

    @Test
    void noneIsUnfiltered() {
      assertThat(ModelFilter.NONE.isUnfiltered()).isTrue();
    }

    @Test
    void ofValidModel() {
      ModelFilter f = ModelFilter.of("claude-3-sonnet");
      assertThat(f.model()).isEqualTo("claude-3-sonnet");
      assertThat(f.isUnfiltered()).isFalse();
    }

    @Test
    void ofWhitespaceRejected() {
      assertThatThrownBy(() -> ModelFilter.of(" claude-3 "))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void equalsAndHashCode() {
      assertThat(ModelFilter.of("m1")).isEqualTo(ModelFilter.of("m1"));
    }
  }

  @Nested
  class AnomalyFilterTests {

    @Test
    void noneIsUnfiltered() {
      assertThat(AnomalyFilter.NONE.isUnfiltered()).isTrue();
      assertThat(AnomalyFilter.NONE.type()).isNull();
    }

    @Test
    void ofSpecificType() {
      AnomalyFilter f = AnomalyFilter.of(AnomalyType.TOKEN_SPIKE);
      assertThat(f.type()).isEqualTo(AnomalyType.TOKEN_SPIKE);
      assertThat(f.isUnfiltered()).isFalse();
    }

    @Test
    void ofNullIsUnfiltered() {
      AnomalyFilter f = AnomalyFilter.of(null);
      assertThat(f.isUnfiltered()).isTrue();
    }

    @Test
    void equalsAndHashCode() {
      assertThat(AnomalyFilter.of(AnomalyType.TOKEN_SPIKE))
          .isEqualTo(AnomalyFilter.of(AnomalyType.TOKEN_SPIKE));
    }
  }

  @Nested
  class TitleFilterTests {

    @Test
    void noneIsUnfiltered() {
      assertThat(TitleFilter.NONE.isUnfiltered()).isTrue();
      assertThat(TitleFilter.NONE.keyword()).isEmpty();
    }

    @Test
    void ofValidKeyword() {
      TitleFilter f = TitleFilter.of("hello");
      assertThat(f.keyword()).isEqualTo("hello");
      assertThat(f.isUnfiltered()).isFalse();
    }

    @Test
    void ofTrimsWhitespace() {
      TitleFilter f = TitleFilter.of("  hello  ");
      assertThat(f.keyword()).isEqualTo("hello");
    }

    @Test
    void ofNullIsUnfiltered() {
      TitleFilter f = TitleFilter.of(null);
      assertThat(f.isUnfiltered()).isTrue();
    }

    @Test
    void equalsAndHashCode() {
      assertThat(TitleFilter.of("k")).isEqualTo(TitleFilter.of("k"));
    }
  }

  @Nested
  class FailureStatusTests {

    @Test
    void fromStringAll() {
      assertThat(FailureStatus.fromString("all")).isEqualTo(FailureStatus.ALL);
      assertThat(FailureStatus.fromString(null)).isEqualTo(FailureStatus.ALL);
      assertThat(FailureStatus.fromString("")).isEqualTo(FailureStatus.ALL);
    }

    @Test
    void fromStringFailed() {
      assertThat(FailureStatus.fromString("failed")).isEqualTo(FailureStatus.FAILED_ONLY);
      assertThat(FailureStatus.fromString("failed_only")).isEqualTo(FailureStatus.FAILED_ONLY);
    }

    @Test
    void fromStringSuccess() {
      assertThat(FailureStatus.fromString("success")).isEqualTo(FailureStatus.SUCCESS_ONLY);
      assertThat(FailureStatus.fromString("success_only")).isEqualTo(FailureStatus.SUCCESS_ONLY);
    }

    @Test
    void fromStringCaseInsensitive() {
      assertThat(FailureStatus.fromString("FAILED")).isEqualTo(FailureStatus.FAILED_ONLY);
      assertThat(FailureStatus.fromString("Success")).isEqualTo(FailureStatus.SUCCESS_ONLY);
    }

    @Test
    void fromStringInvalid() {
      assertThatThrownBy(() -> FailureStatus.fromString("unknown"))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Nested
  class AnomalyTypeTests {

    @Test
    void fromValueValidTypes() {
      assertThat(AnomalyType.fromValue("token_spike")).isEqualTo(AnomalyType.TOKEN_SPIKE);
      assertThat(AnomalyType.fromValue("high_failure_rate"))
          .isEqualTo(AnomalyType.HIGH_FAILURE_RATE);
      assertThat(AnomalyType.fromValue("duration_outlier")).isEqualTo(AnomalyType.DURATION_OUTLIER);
      assertThat(AnomalyType.fromValue("subagent_overuse")).isEqualTo(AnomalyType.SUBAGENT_OVERUSE);
    }

    @Test
    void fromValueInvalid() {
      assertThatThrownBy(() -> AnomalyType.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }
}

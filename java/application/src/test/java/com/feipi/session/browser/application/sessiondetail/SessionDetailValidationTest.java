package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.PayloadVisibility;
import jakarta.validation.ConstraintViolationException;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link SessionDetail} Jakarta validation 边界测试。
 *
 * <p>SessionDetail 紧凑构造器直接调用 {@code ValidationSupport.validateCanonicalConstructor} 且不捕获
 * ConstraintViolationException，因此 null @NotNull 字段会直接抛出 ConstraintViolationException。
 */
@DisplayName("SessionDetail 验证测试")
class SessionDetailValidationTest {

  @Nested
  @DisplayName("@NotNull 字段为 null 抛 ConstraintViolationException")
  class NotNullConstraints {

    @Test
    @DisplayName("sessionRow=null 抛 ConstraintViolationException")
    void nullSessionRow() {
      assertThatThrownBy(
              () ->
                  new SessionDetail(
                      null, List.of(), List.of(), PayloadVisibility.STANDARD, "", "", ""))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("rounds=null 抛 ConstraintViolationException")
    void nullRounds() {
      assertThatThrownBy(
              () ->
                  new SessionDetail(null, null, List.of(), PayloadVisibility.STANDARD, "", "", ""))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("visibility=null 抛 ConstraintViolationException")
    void nullVisibility() {
      assertThatThrownBy(() -> new SessionDetail(null, List.of(), List.of(), null, "", "", ""))
          .isInstanceOf(ConstraintViolationException.class);
    }
  }

  @Nested
  @DisplayName("rowOnly 工厂方法创建合法实例")
  class RowOnlyFactory {

    @Test
    @DisplayName("rowOnly 创建有效详情")
    void rowOnlyCreatesValidDetail() {
      SessionRow sessionRow =
          new SessionRow(
              "cc:test",
              "claude_code",
              "test",
              "标题",
              "pk1",
              "Project",
              "/work",
              "2024-01-01T00:00:00Z",
              "2024-01-01T01:00:00Z",
              3600.0,
              3000.0,
              600.0,
              "claude-3",
              "main",
              "cli",
              5,
              10,
              20,
              50000,
              25000,
              15000,
              10000,
              100000,
              0,
              0,
              1704067200.0,
              1704067200.0,
              "/f1");
      SessionDetail detail = SessionDetail.rowOnly(sessionRow, PayloadVisibility.STANDARD);
      assertThat(detail.sessionRow()).isNotNull();
      assertThat(detail.rounds()).isEmpty();
      assertThat(detail.payloadSources()).isEmpty();
      assertThat(detail.hasArtifact()).isFalse();
    }
  }
}

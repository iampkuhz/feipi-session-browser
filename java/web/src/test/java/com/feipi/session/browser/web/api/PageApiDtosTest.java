package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.api.PageApiDtos.SafeErrorDetails;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 校验 API-first 页面共享 DTO 不变量。 */
@DisplayName("PageApiDtos")
class PageApiDtosTest {

  @Test
  @DisplayName("TokenSegments 强制 total 等于四段合计")
  void tokenSegmentsEnforceSum() {
    TokenSegments tokens = TokenSegments.of(100, 20, 5, 30);

    assertThat(tokens.total()).isEqualTo(155);
    assertThatThrownBy(() -> new TokenSegments(100, 20, 5, 30, 999))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("token segment sum");
  }

  @Test
  @DisplayName("PaginationDto 从 page/pageSize/total 推导分页状态")
  void paginationComputesNavigationFlags() {
    PaginationDto page = PaginationDto.of(2, 25, 60);

    assertThat(page.totalPages()).isEqualTo(3);
    assertThat(page.hasPrevious()).isTrue();
    assertThat(page.hasNext()).isTrue();
  }

  @Test
  @DisplayName("SafeErrorDetails 脱敏 token 和个人路径")
  void safeErrorDetailsRedactsSensitiveContent() {
    SafeErrorDetails details =
        new SafeErrorDetails(
            "IllegalStateException",
            "/Users/alice/private/session.jsonl",
            "rid-1",
            "2026-07-05T00:00:00Z",
            "TOKEN=abc123 failed at /Users/alice/private/session.jsonl");

    assertThat(details.requestPath()).isEqualTo("<path-redacted>");
    assertThat(details.messageSummary()).contains("TOKEN=<redacted>");
    assertThat(details.messageSummary()).contains("<path-redacted>");
    assertThat(details.messageSummary()).doesNotContain("abc123");
    assertThat(details.messageSummary()).doesNotContain("/Users/alice");
  }
}

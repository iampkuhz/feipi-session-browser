package com.feipi.session.browser.web.model;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link PaginationModel} 分页模型测试。 */
@DisplayName("PaginationModel 分页模型测试")
class PaginationModelTest {

  @Nested
  @DisplayName("of 工厂方法")
  class OfFactory {

    @Test
    @DisplayName("计算完整分页字段 - 第一页")
    void computesFirstPage() {
      PaginationModel m = PaginationModel.of(1, 25, 100);
      assertThat(m.page()).isEqualTo(1);
      assertThat(m.pageSize()).isEqualTo(25);
      assertThat(m.totalItems()).isEqualTo(100);
      assertThat(m.totalPages()).isEqualTo(4);
      assertThat(m.pageStart()).isEqualTo(1);
      assertThat(m.pageEnd()).isEqualTo(25);
      assertThat(m.hasPrev()).isFalse();
      assertThat(m.hasNext()).isTrue();
    }

    @Test
    @DisplayName("计算完整分页字段 - 中间页")
    void computesMiddlePage() {
      PaginationModel m = PaginationModel.of(2, 25, 100);
      assertThat(m.page()).isEqualTo(2);
      assertThat(m.pageStart()).isEqualTo(26);
      assertThat(m.pageEnd()).isEqualTo(50);
      assertThat(m.hasPrev()).isTrue();
      assertThat(m.hasNext()).isTrue();
    }

    @Test
    @DisplayName("计算完整分页字段 - 最后一页")
    void computesLastPage() {
      PaginationModel m = PaginationModel.of(4, 25, 100);
      assertThat(m.page()).isEqualTo(4);
      assertThat(m.pageStart()).isEqualTo(76);
      assertThat(m.pageEnd()).isEqualTo(100);
      assertThat(m.hasPrev()).isTrue();
      assertThat(m.hasNext()).isFalse();
    }

    @Test
    @DisplayName("最后一页不满时 pageEnd 等于 totalItems")
    void lastPagePartial() {
      PaginationModel m = PaginationModel.of(3, 25, 60);
      assertThat(m.totalPages()).isEqualTo(3);
      assertThat(m.pageStart()).isEqualTo(51);
      assertThat(m.pageEnd()).isEqualTo(60);
      assertThat(m.hasNext()).isFalse();
    }

    @Test
    @DisplayName("总条目为 0 时返回单页空结果")
    void zeroTotalItems() {
      PaginationModel m = PaginationModel.of(1, 25, 0);
      assertThat(m.totalPages()).isEqualTo(1);
      assertThat(m.pageStart()).isEqualTo(1);
      assertThat(m.pageEnd()).isEqualTo(0);
      assertThat(m.hasPrev()).isFalse();
      assertThat(m.hasNext()).isFalse();
    }

    @Test
    @DisplayName("页码超出范围时自动修正为最后一页")
    void pageClampedToMax() {
      PaginationModel m = PaginationModel.of(999, 25, 100);
      assertThat(m.page()).isEqualTo(4);
      assertThat(m.hasNext()).isFalse();
    }

    @Test
    @DisplayName("页码小于 1 时修正为 1")
    void pageClampedToMin() {
      PaginationModel m = PaginationModel.of(0, 25, 100);
      assertThat(m.page()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("构造器校验")
  class ConstructorValidation {

    @Test
    @DisplayName("page 小于 1 抛出异常")
    void invalidPageThrows() {
      assertThatThrownBy(() -> new PaginationModel(0, 25, 100, 4, 1, 25, false, true))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("页码");
    }

    @Test
    @DisplayName("pageSize 小于 1 抛出异常")
    void invalidPageSizeThrows() {
      assertThatThrownBy(() -> new PaginationModel(1, 0, 100, 4, 1, 25, false, true))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("页面大小");
    }
  }

  @Nested
  @DisplayName("record 语义")
  class RecordSemantics {

    @Test
    @DisplayName("相等性基于全部字段")
    void equalityByAllFields() {
      PaginationModel a = PaginationModel.of(1, 25, 100);
      PaginationModel b = PaginationModel.of(1, 25, 100);
      assertThat(a).isEqualTo(b);
    }
  }
}

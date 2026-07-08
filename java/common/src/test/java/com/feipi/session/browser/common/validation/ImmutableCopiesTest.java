package com.feipi.session.browser.common.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link ImmutableCopies} 单元测试。 */
@DisplayName("ImmutableCopies")
class ImmutableCopiesTest {

  @Test
  @DisplayName("null 集合转为空不可变列表")
  void nullListBecomesEmptyList() {
    assertThat(ImmutableCopies.listOrEmpty(null)).isEmpty();
  }

  @Test
  @DisplayName("列表拷贝后不受原集合影响")
  void listCopyIsDefensive() {
    List<String> source = new ArrayList<>();
    source.add("a");
    List<String> copy = ImmutableCopies.listOrEmpty(source);
    source.add("b");
    assertThat(copy).containsExactly("a");
  }

  @Test
  @DisplayName("bounded list 超限失败")
  void boundedListRejectsOversize() {
    assertThatThrownBy(() -> ImmutableCopies.boundedListOrEmpty(List.of("a", "b"), 1, "items"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("items");
  }

  @Test
  @DisplayName("map 拷贝支持 null to empty")
  void mapOrEmptyHandlesNull() {
    assertThat(ImmutableCopies.mapOrEmpty(null)).isEqualTo(Map.of());
  }
}

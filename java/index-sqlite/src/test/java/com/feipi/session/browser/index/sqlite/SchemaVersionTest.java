package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link SchemaVersion} 不可变版本号的单元测试。 */
@DisplayName("SchemaVersion 测试")
class SchemaVersionTest {

  @Test
  @DisplayName("有效版本号创建成功")
  void validVersionCreation() {
    SchemaVersion v1 = new SchemaVersion(1);
    assertThat(v1.version()).isEqualTo(1);
  }

  @Test
  @DisplayName("版本号 0 抛出 IllegalArgumentException")
  void zeroVersionThrows() {
    assertThatThrownBy(() -> new SchemaVersion(0))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("必须 >= 1");
  }

  @Test
  @DisplayName("负数版本号抛出 IllegalArgumentException")
  void negativeVersionThrows() {
    assertThatThrownBy(() -> new SchemaVersion(-1)).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("compareTo 按版本号升序比较")
  void compareToOrdersByNumber() {
    SchemaVersion v1 = new SchemaVersion(1);
    SchemaVersion v2 = new SchemaVersion(2);
    SchemaVersion v10 = new SchemaVersion(10);

    assertThat(v1.compareTo(v2)).isNegative();
    assertThat(v2.compareTo(v1)).isPositive();
    assertThat(v1.compareTo(v1)).isZero();
    assertThat(v1.compareTo(v10)).isNegative();
  }

  @Test
  @DisplayName("相等性：相同版本号相等")
  void equalityByVersion() {
    SchemaVersion a = new SchemaVersion(5);
    SchemaVersion b = new SchemaVersion(5);
    assertThat(a).isEqualTo(b);
    assertThat(a.hashCode()).isEqualTo(b.hashCode());
  }

  @Test
  @DisplayName("toString 格式为 V{数字}")
  void toStringFormat() {
    assertThat(new SchemaVersion(1).toString()).isEqualTo("V1");
    assertThat(new SchemaVersion(42).toString()).isEqualTo("V42");
  }
}

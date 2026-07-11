package com.feipi.session.browser.quality.gates.javaapi;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/** {@link JavaRecordSourceParser} 单元测试。 */
class JavaRecordSourceParserTest {

  private final JavaRecordSourceParser parser = new JavaRecordSourceParser();

  @Test
  void parsesSimpleRecord() {
    var source =
        """
                /**
                 * 简单 record。
                 *
                 * @param name 名称
                 * @param age  年龄
                 */
                public record SimpleRecord(String name, int age) {
                }
                """;
    var records = parser.parseSource(Path.of("SimpleRecord.java"), source);

    assertThat(records).hasSize(1);
    var record = records.get(0);
    assertThat(record.name()).isEqualTo("SimpleRecord");
    assertThat(record.line()).isEqualTo(7);
    assertThat(record.typeJavadoc()).isPresent();
    assertThat(record.typeJavadoc().get()).contains("@param name");
    assertThat(record.components()).hasSize(2);
    assertThat(record.components().get(0).name()).isEqualTo("name");
    assertThat(record.components().get(1).name()).isEqualTo("age");
  }

  @Test
  void parsesGenericRecord() {
    var source =
        """
                /**
                 * 泛型 record。
                 *
                 * @param value 值
                 * @param <T>   类型
                 */
                public record GenericRecord<T>(T value) {
                }
                """;
    var records = parser.parseSource(Path.of("GenericRecord.java"), source);

    assertThat(records).hasSize(1);
    var record = records.get(0);
    assertThat(record.name()).isEqualTo("GenericRecord");
    assertThat(record.components()).hasSize(1);
    assertThat(record.components().get(0).name()).isEqualTo("value");
  }

  @Test
  void parsesAnnotatedRecord() {
    var source =
        """
                /**
                 * 注解 record。
                 *
                 * @param id 标识
                 */
                @SuppressWarnings("all")
                public record AnnotatedRecord(long id) {
                }
                """;
    var records = parser.parseSource(Path.of("AnnotatedRecord.java"), source);

    assertThat(records).hasSize(1);
    var record = records.get(0);
    assertThat(record.name()).isEqualTo("AnnotatedRecord");
    assertThat(record.typeJavadoc()).isPresent();
  }

  @Test
  void parsesNestedRecord() {
    var source =
        """
                public class Outer {
                    /**
                     * 内部 record。
                     *
                     * @param x 横坐标
                     */
                    public record Inner(int x) {
                    }
                }
                """;
    var records = parser.parseSource(Path.of("Outer.java"), source);

    assertThat(records).hasSize(1);
    assertThat(records.get(0).name()).isEqualTo("Inner");
    assertThat(records.get(0).components()).hasSize(1);
    assertThat(records.get(0).components().get(0).name()).isEqualTo("x");
  }

  @Test
  void parsesRecordWithImplements() {
    var source =
        """
                /**
                 * 实现接口 record。
                 *
                 * @param code 状态码
                 */
                public record StatusRecord(int code) implements Comparable<StatusRecord> {
                    @Override
                    public int compareTo(StatusRecord o) { return 0; }
                }
                """;
    var records = parser.parseSource(Path.of("StatusRecord.java"), source);

    assertThat(records).hasSize(1);
    assertThat(records.get(0).name()).isEqualTo("StatusRecord");
    assertThat(records.get(0).components()).hasSize(1);
  }

  @Test
  void parsesRecordWithAnnotatedComponents() {
    var source =
        """
                /**
                 * 带注解 component。
                 *
                 * @param name 名称
                 * @param age  年龄
                 */
                public record AnnotatedComponents(
                        @Deprecated String name,
                        int age) {
                }
                """;
    var records = parser.parseSource(Path.of("AnnotatedComponents.java"), source);

    assertThat(records).hasSize(1);
    assertThat(records.get(0).components()).hasSize(2);
    assertThat(records.get(0).components().get(0).name()).isEqualTo("name");
    assertThat(records.get(0).components().get(1).name()).isEqualTo("age");
  }

  @Test
  void recordWithoutJavadoc() {
    var source =
        """
                public record NoJavadoc(String value) {
                }
                """;
    var records = parser.parseSource(Path.of("NoJavadoc.java"), source);

    assertThat(records).hasSize(1);
    assertThat(records.get(0).typeJavadoc()).isEmpty();
  }

  @Test
  void packagePrivateRecord() {
    var source =
        """
                /**
                 * 包级可见 record。
                 *
                 * @param data 数据
                 */
                record PackageRecord(String data) {
                }
                """;
    var records = parser.parseSource(Path.of("PackageRecord.java"), source);

    assertThat(records).hasSize(1);
    assertThat(records.get(0).name()).isEqualTo("PackageRecord");
    assertThat(records.get(0).typeJavadoc()).isPresent();
  }

  @Test
  void noRecordInFile() {
    var source =
        """
                public class NotARecord {
                    public String name;
                }
                """;
    var records = parser.parseSource(Path.of("NotARecord.java"), source);
    assertThat(records).isEmpty();
  }
}

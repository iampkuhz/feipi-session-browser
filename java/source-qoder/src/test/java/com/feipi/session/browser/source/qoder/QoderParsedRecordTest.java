package com.feipi.session.browser.source.qoder;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.ParsedRecord;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link QoderParsedRecord} 单元测试。
 *
 * <p>验证 locator 稳定性、eventType 和 eventIndex 正确性。
 */
@DisplayName("QoderParsedRecord 已解析记录测试")
class QoderParsedRecordTest {

  @Nested
  @DisplayName("locator")
  class LocatorTests {

    @Test
    @DisplayName("locator 格式为 {filePath}#event[{index}]")
    void locatorFormatIsFilePathWithEventIndex() {
      QoderParsedRecord record = new QoderParsedRecord("/path/to/session.jsonl", 0, "user");
      assertThat(record.locator()).isEqualTo("/path/to/session.jsonl#event[0]");
    }

    @Test
    @DisplayName("不同 eventIndex 产生不同 locator")
    void differentIndexProducesDifferentLocator() {
      QoderParsedRecord r0 = new QoderParsedRecord("/path/session.jsonl", 0, "user");
      QoderParsedRecord r1 = new QoderParsedRecord("/path/session.jsonl", 1, "user");
      assertThat(r0.locator()).isNotEqualTo(r1.locator());
    }

    @Test
    @DisplayName("相同输入产生相同 locator（确定性）")
    void sameInputProducesSameLocator() {
      QoderParsedRecord r1 = new QoderParsedRecord("/path/session.jsonl", 5, "assistant");
      QoderParsedRecord r2 = new QoderParsedRecord("/path/session.jsonl", 5, "assistant");
      assertThat(r1.locator()).isEqualTo(r2.locator());
    }

    @Test
    @DisplayName("locator 实现 ParsedRecord 接口")
    void locatorImplementsParsedRecordInterface() {
      ParsedRecord record = new QoderParsedRecord("/path/session.jsonl", 0, "user");
      assertThat(record.locator()).isNotEmpty();
    }
  }

  @Nested
  @DisplayName("eventType")
  class EventTypeTests {

    @Test
    @DisplayName("eventType 返回构造时传入的值")
    void eventTypeReturnsConstructorValue() {
      QoderParsedRecord record = new QoderParsedRecord("/path/session.jsonl", 0, "assistant");
      assertThat(record.eventType()).isEqualTo("assistant");
    }

    @Test
    @DisplayName("unknown 类型正确保留")
    void unknownTypeIsPreserved() {
      QoderParsedRecord record =
          new QoderParsedRecord("/path/session.jsonl", 0, QoderConstants.EVENT_TYPE_UNKNOWN);
      assertThat(record.eventType()).isEqualTo("unknown");
    }
  }

  @Nested
  @DisplayName("eventIndex")
  class EventIndexTests {

    @Test
    @DisplayName("eventIndex 返回构造时传入的值")
    void eventIndexReturnsConstructorValue() {
      QoderParsedRecord record = new QoderParsedRecord("/path/session.jsonl", 42, "user");
      assertThat(record.eventIndex()).isEqualTo(42);
    }

    @Test
    @DisplayName("零索引正确保留")
    void zeroIndexIsPreserved() {
      QoderParsedRecord record = new QoderParsedRecord("/path/session.jsonl", 0, "user");
      assertThat(record.eventIndex()).isZero();
    }
  }

  @Nested
  @DisplayName("参数验证")
  class ValidationTests {

    @Test
    @DisplayName("filePath 为 null 时抛出 NullPointerException")
    void nullFilePathThrowsException() {
      assertThatThrownBy(() -> new QoderParsedRecord(null, 0, "user"))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("eventType 为 null 时抛出 NullPointerException")
    void nullEventTypeThrowsException() {
      assertThatThrownBy(() -> new QoderParsedRecord("/path/session.jsonl", 0, null))
          .isInstanceOf(NullPointerException.class);
    }
  }
}

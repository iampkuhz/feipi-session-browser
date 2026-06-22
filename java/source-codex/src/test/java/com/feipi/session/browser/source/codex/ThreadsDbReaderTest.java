package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link ThreadsDbReader} 单元测试。
 *
 * <p>验证 SQLite 只读访问在各种场景下的行为：数据库不存在、 损坏数据库、null 路径。
 */
@DisplayName("ThreadsDbReader 线程数据库读取测试")
class ThreadsDbReaderTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("错误处理")
  class ErrorHandling {

    @Test
    @DisplayName("数据库不存在返回空列表")
    void nonExistingDbReturnsEmptyList() {
      Path nonExisting = tempDir.resolve("threads.sqlite3");
      List<Map<String, String>> threads = ThreadsDbReader.readThreads(nonExisting);
      assertThat(threads).isEmpty();
    }

    @Test
    @DisplayName("null 路径返回空列表")
    void nullPathReturnsEmptyList() {
      List<Map<String, String>> threads = ThreadsDbReader.readThreads(null);
      assertThat(threads).isEmpty();
    }

    @Test
    @DisplayName("损坏数据库返回空列表不抛异常")
    void corruptDbReturnsEmptyListWithoutException() throws Exception {
      // 创建一个损坏的 SQLite 数据库文件（随机内容）
      Path corruptDb = tempDir.resolve("threads.sqlite3");
      java.nio.file.Files.writeString(corruptDb, "this is not a valid sqlite database");

      List<Map<String, String>> threads = ThreadsDbReader.readThreads(corruptDb);
      assertThat(threads).isEmpty();
    }
  }
}

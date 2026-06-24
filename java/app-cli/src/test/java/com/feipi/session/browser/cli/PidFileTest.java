package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * PidFile 契约测试。
 *
 * <p>验证 PID 文件的写入、读取、解析和删除操作。 包括正常路径、空文件、格式损坏、缺失字段等边界场景。
 */
@DisplayName("PidFile 契约测试")
class PidFileTest {

  @TempDir Path tempDir;

  // ===== 写入/读取契约 =====

  @Nested
  @DisplayName("PID 文件写入/读取")
  class WriteReadContract {

    @Test
    @DisplayName("写入后可正确读取全部字段")
    void writeThenReadRoundTrip() throws Exception {
      Path indexDir = tempDir.resolve("test-index");
      Files.createDirectories(indexDir);

      PidFile.write(indexDir, 12345L, 8848, "127.0.0.1");

      PidFile.Metadata meta = PidFile.read(indexDir);
      assertThat(meta).isNotNull();
      assertThat(meta.pid()).isEqualTo(12345L);
      assertThat(meta.port()).isEqualTo(8848);
      assertThat(meta.host()).isEqualTo("127.0.0.1");
      assertThat(meta.indexDir()).isEqualTo(indexDir.toAbsolutePath().normalize());
      assertThat(meta.startedAt()).isNotEmpty();
    }

    @Test
    @DisplayName("PID 文件名固定为 server.pid")
    void fileNameIsServerPid() {
      assertThat(PidFile.path(tempDir).getFileName().toString()).isEqualTo("server.pid");
    }

    @Test
    @DisplayName("写入后文件存在于索引目录根")
    void fileExistsInIndexDir() throws Exception {
      PidFile.write(tempDir, 100L, 3000, "localhost");

      assertThat(PidFile.path(tempDir)).exists();
    }

    @Test
    @DisplayName("APP_NAME 为 feipi-session-browser")
    void appNameConstant() {
      assertThat(PidFile.APP_NAME).isEqualTo("feipi-session-browser");
    }
  }

  // ===== 读取边界契约 =====

  @Nested
  @DisplayName("PID 文件读取边界")
  class ReadBoundaryContract {

    @Test
    @DisplayName("文件不存在时 read 返回 null")
    void readReturnsNullWhenFileMissing() throws Exception {
      Path emptyDir = tempDir.resolve("no-pid");
      Files.createDirectories(emptyDir);

      assertThat(PidFile.read(emptyDir)).isNull();
    }

    @Test
    @DisplayName("空文件解析返回 null（缺少 pid 字段）")
    void emptyFileReturnsNull() throws Exception {
      Files.writeString(PidFile.path(tempDir), "");

      assertThat(PidFile.read(tempDir)).isNull();
    }

    @Test
    @DisplayName("缺少 pid 字段时返回 null")
    void missingPidFieldReturnsNull() throws Exception {
      Files.writeString(PidFile.path(tempDir), "port=8848\nhost=127.0.0.1\n");

      assertThat(PidFile.read(tempDir)).isNull();
    }

    @Test
    @DisplayName("pid 字段非数字时返回 null")
    void nonNumericPidReturnsNull() throws Exception {
      Files.writeString(PidFile.path(tempDir), "pid=abc\nport=8848\n");

      assertThat(PidFile.read(tempDir)).isNull();
    }

    @Test
    @DisplayName("缺少可选字段时使用默认值")
    void missingOptionalFieldsUseDefaults() throws Exception {
      Files.writeString(PidFile.path(tempDir), "pid=999\n");

      PidFile.Metadata meta = PidFile.read(tempDir);
      assertThat(meta).isNotNull();
      assertThat(meta.pid()).isEqualTo(999L);
      assertThat(meta.port()).isEqualTo(0);
      assertThat(meta.host()).isEqualTo("127.0.0.1");
      assertThat(meta.startedAt()).isEmpty();
    }

    @Test
    @DisplayName("包含空行和多余空格时仍可解析")
    void toleratesBlankLinesAndWhitespace() throws Exception {
      String content = "\npid = 42\n\n  \nport = 9090\nhost = 0.0.0.0\n\n";
      Files.writeString(PidFile.path(tempDir), content);

      PidFile.Metadata meta = PidFile.read(tempDir);
      assertThat(meta).isNotNull();
      assertThat(meta.pid()).isEqualTo(42L);
    }
  }

  // ===== 解析契约 =====

  @Nested
  @DisplayName("PID 文件内容解析")
  class ParseContract {

    @Test
    @DisplayName("parse 使用 fallbackIndexDir 当文件缺少 index_dir")
    void parseUsesFallbackIndexDir() {
      Path fallback = Path.of("/fallback/dir");
      PidFile.Metadata meta = PidFile.parse("pid=100\nport=3000\n", fallback);

      assertThat(meta).isNotNull();
      assertThat(meta.indexDir()).isEqualTo(fallback);
    }

    @Test
    @DisplayName("parse 优先使用文件中的 index_dir")
    void parsePrefersFileIndexDir() {
      Path fallback = Path.of("/fallback/dir");
      String content = "pid=100\nindex_dir=/custom/dir\n";
      PidFile.Metadata meta = PidFile.parse(content, fallback);

      assertThat(meta).isNotNull();
      assertThat(meta.indexDir()).isEqualTo(Path.of("/custom/dir"));
    }

    @Test
    @DisplayName("空内容返回 null")
    void emptyContentReturnsNull() {
      assertThat(PidFile.parse("", tempDir)).isNull();
    }
  }

  // ===== 删除契约 =====

  @Nested
  @DisplayName("PID 文件删除")
  class DeleteContract {

    @Test
    @DisplayName("delete 移除已存在的 PID 文件")
    void deleteRemovesExistingFile() throws Exception {
      PidFile.write(tempDir, 100L, 3000, "localhost");
      assertThat(PidFile.path(tempDir)).exists();

      PidFile.delete(tempDir);
      assertThat(PidFile.path(tempDir)).doesNotExist();
    }

    @Test
    @DisplayName("delete 对不存在的文件静默返回")
    void deleteOnMissingFileIsSilent() {
      Path emptyDir = tempDir.resolve("no-pid");
      // 不抛异常即为通过
      PidFile.delete(emptyDir);
    }

    @Test
    @DisplayName("delete 幂等：连续调用两次不抛异常")
    void deleteIsIdempotent() throws Exception {
      PidFile.write(tempDir, 100L, 3000, "localhost");

      PidFile.delete(tempDir);
      PidFile.delete(tempDir);

      assertThat(PidFile.path(tempDir)).doesNotExist();
    }
  }
}

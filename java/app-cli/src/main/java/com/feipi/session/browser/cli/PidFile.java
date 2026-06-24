package com.feipi.session.browser.cli;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * 服务器 PID 文件的读写与元数据载体。
 *
 * <p>PID 文件位于 {@code {indexDir}/server.pid}，采用 key=value 文本格式（UTF-8），每行一个键值对。 用于 stop 命令定位和验证运行中的
 * serve 进程，优先于端口探测，避免误杀无关进程。
 *
 * <p>文件格式示例：
 *
 * <pre>
 * pid=12345
 * port=8848
 * host=127.0.0.1
 * index_dir=/home/user/.local/share/feipi/session-browser/local-test-index
 * app_name=feipi-session-browser
 * started_at=2026-06-24T10:00:00Z
 * </pre>
 *
 * <p>校验放置：PID 文件的写入在 {@link ServerLifecycle#start} 成功后执行一次；读取和删除在 {@link StopCommand} 边界执行一次。
 * 下游不重复校验文件存在性。
 */
final class PidFile {

  /** PID 文件名，位于索引目录根。 */
  static final String FILE_NAME = "server.pid";

  /** 应用名称标识，用于 stop 命令验证 PID 归属。 */
  static final String APP_NAME = "feipi-session-browser";

  private PidFile() {}

  /**
   * 服务器进程元数据。
   *
   * <p>不可变记录，承载 PID 文件中的全部字段。
   *
   * @param pid 进程 ID
   * @param port 监听端口
   * @param host 监听地址
   * @param indexDir 索引目录绝对路径
   * @param startedAt 启动时间戳（ISO-8601）
   */
  record Metadata(long pid, int port, String host, Path indexDir, String startedAt) {

    Metadata {
      Objects.requireNonNull(host, "host 不得为 null");
      Objects.requireNonNull(indexDir, "indexDir 不得为 null");
    }
  }

  /**
   * 获取 PID 文件路径。
   *
   * @param indexDir 索引目录
   * @return {@code {indexDir}/server.pid}
   */
  static Path path(Path indexDir) {
    return indexDir.resolve(FILE_NAME);
  }

  /**
   * 写入 PID 文件。
   *
   * <p>原子性不保证，但写入顺序为 pid → port → host → index_dir → app_name → started_at， 读取时按行解析，容忍缺失字段。
   *
   * @param indexDir 索引目录
   * @param pid 进程 ID
   * @param port 实际监听端口
   * @param host 监听地址
   * @throws IOException 写入失败时
   */
  static void write(Path indexDir, long pid, int port, String host) throws IOException {
    Path file = path(indexDir);
    StringBuilder sb = new StringBuilder();
    sb.append("pid=").append(pid).append('\n');
    sb.append("port=").append(port).append('\n');
    sb.append("host=").append(host).append('\n');
    sb.append("index_dir=").append(indexDir.toAbsolutePath().normalize()).append('\n');
    sb.append("app_name=").append(APP_NAME).append('\n');
    sb.append("started_at=").append(Instant.now()).append('\n');
    Files.writeString(file, sb.toString(), StandardCharsets.UTF_8);
  }

  /**
   * 读取并解析 PID 文件。
   *
   * <p>文件不存在时返回 {@code null}；格式损坏时尽量解析已知字段， 缺少必要字段（pid）时返回 {@code null}。
   *
   * @param indexDir 索引目录
   * @return 解析后的元数据，文件不存在或解析失败时返回 {@code null}
   * @throws IOException 读取失败时
   */
  static Metadata read(Path indexDir) throws IOException {
    Path file = path(indexDir);
    if (!Files.exists(file)) {
      return null;
    }
    String content = Files.readString(file, StandardCharsets.UTF_8);
    return parse(content, indexDir);
  }

  /**
   * 删除 PID 文件。
   *
   * <p>文件不存在时静默返回。删除失败时静默忽略（常见于进程已被外部终止的场景）。
   *
   * @param indexDir 索引目录
   */
  static void delete(Path indexDir) {
    try {
      Files.deleteIfExists(path(indexDir));
    } catch (IOException ignored) {
      // PID 文件删除失败不影响功能，仅可能影响下次 stop 的识别
    }
  }

  /**
   * 解析 PID 文件内容。
   *
   * @param content 文件内容
   * @param fallbackIndexDir 当文件中缺少 index_dir 字段时的回退路径
   * @return 解析后的元数据，缺少 pid 字段时返回 null
   */
  static Metadata parse(String content, Path fallbackIndexDir) {
    Map<String, String> props = new LinkedHashMap<>();
    try (BufferedReader reader = new BufferedReader(new StringReader(content))) {
      String line;
      while ((line = reader.readLine()) != null) {
        line = line.trim();
        if (line.isEmpty()) {
          continue;
        }
        int eq = line.indexOf('=');
        if (eq > 0) {
          props.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
        }
      }
    } catch (IOException e) {
      return null;
    }

    String pidStr = props.get("pid");
    if (pidStr == null || pidStr.isBlank()) {
      return null;
    }

    long pid;
    try {
      pid = Long.parseLong(pidStr.trim());
    } catch (NumberFormatException e) {
      return null;
    }

    int port = parseIntOrDefault(props.get("port"), 0);
    String host = props.getOrDefault("host", "127.0.0.1");
    String indexDirStr = props.get("index_dir");
    Path indexDir =
        indexDirStr != null && !indexDirStr.isBlank()
            ? Path.of(indexDirStr.trim())
            : fallbackIndexDir;
    String startedAt = props.getOrDefault("started_at", "");

    return new Metadata(pid, port, host, indexDir, startedAt);
  }

  private static int parseIntOrDefault(String value, int defaultValue) {
    if (value == null || value.isBlank()) {
      return defaultValue;
    }
    try {
      return Integer.parseInt(value.trim());
    } catch (NumberFormatException e) {
      return defaultValue;
    }
  }
}

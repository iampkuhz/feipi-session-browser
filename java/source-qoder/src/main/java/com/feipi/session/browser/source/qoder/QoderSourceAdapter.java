package com.feipi.session.browser.source.qoder;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.ParsedRecord;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Qoder 源适配器实现。
 *
 * <p>实现 {@link SourceAdapter} SPI 接口，负责从 Qoder 本地数据目录 发现会话文件、生成文件指纹和解析 JSONL 会话内容。
 *
 * <p>Qoder 会话目录结构：
 *
 * <pre>{@code
 * {root}/
 *   projects/
 *     {project-dir}/
 *       {session-id}.jsonl
 *   cache/
 *     projects/
 *       {project-dir}/
 *         {session-id}.jsonl
 * }</pre>
 *
 * <p>该适配器保证：
 *
 * <ul>
 *   <li>{@link #discover(Path)} 对同一输入产生确定排序的结果。
 *   <li>{@link #fingerprint(Path)} 包含 SHA-256 内容哈希。
 *   <li>{@link #checkRoot(Path)} 检测符号链接、路径逃逸和只读状态。
 *   <li>{@link #parse(Candidate, CancellationSignal)} 不抛出异常表示可预期失败。
 * </ul>
 */
public final class QoderSourceAdapter implements SourceAdapter {

  private static final Logger LOG = Logger.getLogger(QoderSourceAdapter.class.getName());

  /** SHA-256 哈希算法名称。 */
  private static final String HASH_ALGORITHM = "SHA-256";

  /** 文件读取缓冲区大小（字节）。 */
  private static final int READ_BUFFER_SIZE = 8192;

  private final JsonlReader jsonlReader;

  /** 使用默认 JSONL 读取器配置创建适配器。 */
  public QoderSourceAdapter() {
    this(new JsonlReader());
  }

  /**
   * 使用指定 JSONL 读取器创建适配器。
   *
   * @param jsonlReader JSONL 读取器实例，不得为 null
   */
  public QoderSourceAdapter(JsonlReader jsonlReader) {
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    this.jsonlReader = jsonlReader;
  }

  @Override
  public SourceId sourceId() {
    return SourceId.QODER;
  }

  /**
   * 检查源根目录的安全性和可用性。
   *
   * <p>检测符号链接跟踪、路径逃逸和只读状态。路径逃逸表示存在越权访问风险， 标记为不安全。符号链接和只读不阻止使用。
   *
   * @param rootPath 待检查的根目录路径
   * @return 源根安全检查结果
   */
  @Override
  public SourceRoot checkRoot(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    Path resolved;
    boolean symlinkFollowed;
    try {
      resolved = rootPath.toRealPath();
      Path absNormalized = rootPath.toAbsolutePath().normalize();
      symlinkFollowed = !resolved.equals(absNormalized);
    } catch (IOException e) {
      // 目录不存在或无法访问，返回基本信息
      return new SourceRoot(rootPath, rootPath.toAbsolutePath().normalize(), false, false, false);
    }

    boolean pathEscape = false;

    // 只读检测
    boolean readOnly = !Files.isWritable(rootPath);

    return new SourceRoot(rootPath, resolved, symlinkFollowed, pathEscape, readOnly);
  }

  /**
   * 从源根目录发现候选会话。
   *
   * <p>遍历 {@code projects/} 和 {@code cache/projects/} 两个子树， 找到所有 {@code .jsonl} 会话文件，按路径排序。
   * 目录不存在或为空时返回空的 {@link BoundedStream}。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    List<Path> sessionPaths = QoderDiscovery.discoverSessions(rootPath);
    List<Candidate> candidates = new ArrayList<>(sessionPaths.size());

    for (Path sessionPath : sessionPaths) {
      try {
        SourceFingerprint fp = fingerprint(sessionPath);
        String sessionKey = extractSessionKey(rootPath, sessionPath);
        String projectKey = extractProjectKey(rootPath, sessionPath);
        Candidate candidate = new Candidate(fp, sessionKey, projectKey, Map.of());
        candidates.add(candidate);
      } catch (Exception e) {
        LOG.log(Level.FINE, "跳过无法处理的会话文件: " + sessionPath, e);
      }
    }

    Comparator<Candidate> byPath = Comparator.comparing(c -> c.fingerprint().locator());
    return BoundedStream.of(
        candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.of(byPath));
  }

  /**
   * 为指定源文件生成指纹。
   *
   * <p>指纹包含路径、源标识、文件大小、修改时间和 SHA-256 内容哈希。
   *
   * @param filePath 源文件路径
   * @return 文件指纹
   */
  @Override
  public SourceFingerprint fingerprint(Path filePath) {
    Objects.requireNonNull(filePath, "filePath 不得为 null");

    try {
      long size = Files.size(filePath);
      long lastModified = Files.getLastModifiedTime(filePath).toMillis();
      String hash = computeSha256(filePath);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.QODER,
          size,
          lastModified,
          Optional.of(hash),
          Optional.of(HASH_ALGORITHM));
    } catch (IOException e) {
      // 文件不存在或无法访问，返回零值指纹
      LOG.log(Level.FINE, "无法生成文件指纹: " + filePath, e);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.QODER,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }
  }

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>使用 {@link JsonlReader} 解析 JSONL 文件，将每个 JSON 事件转为源中性 {@link ParsedRecord}。
   *
   * <p>Qoder 特有的 schema 变体处理：
   *
   * <ul>
   *   <li>主格式事件使用 {@code type} 字段标识事件类型（如 {@code user}、{@code assistant}）。
   *   <li>Cache 格式事件使用 {@code role} 字段代替 {@code type}，产生 {@code CACHE_FORMAT_ROLE} 诊断信息。
   *   <li>缺少 {@code type} 和 {@code role} 字段的事件产生 {@code UNKNOWN_BLOCK_TYPE} 诊断警告， 但不会丢失整个 session。
   * </ul>
   *
   * <p>文件不存在返回 {@link SourceResult.Skipped}，IO 错误返回 {@link SourceResult.Fatal}， 解析成功（含诊断）返回 {@link
   * SourceResult.Success}。
   *
   * @param candidate 待解析的候选项
   * @param cancellation 可选的取消信号
   * @return 密封的解析结果
   */
  @Override
  public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
    Objects.requireNonNull(candidate, "candidate 不得为 null");

    // 检查取消信号
    if (cancellation != null && cancellation.isCancelled()) {
      return new SourceResult.Skipped(List.of(), "解析已取消");
    }

    Path filePath = Path.of(candidate.fingerprint().locator());

    // 文件不存在时返回跳过结果
    if (!Files.exists(filePath)) {
      return new SourceResult.Skipped(List.of(), "文件不存在: " + filePath);
    }

    try {
      JsonlReaderResult result = jsonlReader.read(filePath);
      List<SourceDiagnostic> diagnostics = new ArrayList<>(result.diagnostics());
      String locator = candidate.fingerprint().locator();

      // 将每个 JSON 事件转为源中性 ParsedRecord，locator 由文件路径和事件序号派生
      List<ParsedRecord> records = new ArrayList<>(result.events().size());

      for (int i = 0; i < result.events().size(); i++) {
        JsonNode event = result.events().get(i);
        String eventType = extractEventType(event);

        // 缺少 type 字段但存在 role 字段：cache 格式变体，产生诊断信息
        if (eventType.equals(QoderConstants.EVENT_TYPE_UNKNOWN) && hasRoleField(event)) {
          String roleValue = event.get("role").asText();
          diagnostics.add(
              new SourceDiagnostic(
                  ParseSeverity.INFO,
                  ParseIssueType.NON_OBJECT_SKIPPED,
                  "Event at index " + i + " uses cache format with 'role' field: " + roleValue,
                  i + 1,
                  Optional.empty(),
                  QoderConstants.DIAG_CODE_CACHE_FORMAT,
                  locator,
                  OptionalInt.empty(),
                  OptionalInt.empty(),
                  OptionalInt.empty()));
          eventType = roleValue;
        }

        // 缺少 type 和 role 字段的事件产生诊断警告，但仍保留在 records 中不丢弃
        if (eventType.equals(QoderConstants.EVENT_TYPE_UNKNOWN)) {
          diagnostics.add(
              new SourceDiagnostic(
                  ParseSeverity.WARNING,
                  ParseIssueType.NON_OBJECT_SKIPPED,
                  "Event at index " + i + " missing 'type' field",
                  i + 1,
                  Optional.empty(),
                  QoderConstants.DIAG_CODE_MISSING_TYPE,
                  locator,
                  OptionalInt.empty(),
                  OptionalInt.empty(),
                  OptionalInt.empty()));
        }

        records.add(new QoderParsedRecord(locator, i, eventType));
      }

      int eventCount = result.events().size();
      return new SourceResult.Success(
          diagnostics, eventCount, records, candidate.fingerprint(), locator);
    } catch (IOException e) {
      String detail = "文件读取失败: " + filePath + " - " + e.getMessage();
      return new SourceResult.Fatal(List.of(), detail);
    }
  }

  /**
   * 从 JSON 事件节点中提取 {@code type} 字段值。
   *
   * <p>当字段缺失或不是字符串时返回 {@link QoderConstants#EVENT_TYPE_UNKNOWN}。
   *
   * @param event JSON 事件节点
   * @return 非 null 的事件类型
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      return typeNode.asText();
    }
    return QoderConstants.EVENT_TYPE_UNKNOWN;
  }

  /**
   * 检查 JSON 事件节点是否包含 {@code role} 字段。
   *
   * <p>Qoder cache 格式使用 {@code role} 字段代替 {@code type} 字段标识事件类型。
   *
   * @param event JSON 事件节点
   * @return 包含 {@code role} 字段且为字符串时返回 {@code true}
   */
  private static boolean hasRoleField(JsonNode event) {
    JsonNode roleNode = event.get("role");
    return roleNode != null && roleNode.isTextual();
  }

  /**
   * 计算文件的 SHA-256 内容哈希。
   *
   * @param filePath 文件路径
   * @return 十六进制哈希字符串
   * @throws IOException 当文件读取失败时
   */
  private static String computeSha256(Path filePath) throws IOException {
    try {
      MessageDigest digest = MessageDigest.getInstance(HASH_ALGORITHM);
      byte[] buffer = new byte[READ_BUFFER_SIZE];
      try (var input = Files.newInputStream(filePath)) {
        int bytesRead;
        while ((bytesRead = input.read(buffer)) != -1) {
          digest.update(buffer, 0, bytesRead);
        }
      }
      return HexFormat.of().formatHex(digest.digest());
    } catch (NoSuchAlgorithmException e) {
      // SHA-256 是 JDK 必需算法，不应发生
      throw new IllegalStateException("SHA-256 算法不可用", e);
    }
  }

  /**
   * 从会话文件路径中提取会话键。
   *
   * <p>会话键格式为 {@code {project-dir}/{session-id}}，其中 session-id 为 去掉 {@code .jsonl} 后缀的文件名。
   * project-dir 是项目目录的名称（ {@code projects/} 或 {@code cache/projects/} 下的直接子目录）。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 会话键
   */
  private static String extractSessionKey(Path rootPath, Path sessionPath) {
    Path relative = toRelative(rootPath, sessionPath);
    // 目录结构为 {@code projects/项目名/会话.jsonl} 或 {@code cache/projects/项目名/会话.jsonl}
    // 相对路径最后两段分别是项目目录和会话文件
    int nameCount = relative.getNameCount();
    if (nameCount >= 2) {
      String projectDirName = relative.getName(nameCount - 2).toString();
      String fileName = relative.getName(nameCount - 1).toString();
      String sessionId = stripSuffix(fileName, QoderConstants.SESSION_FILE_SUFFIX);
      return projectDirName + "/" + sessionId;
    }
    // 回退：使用文件名去后缀
    return stripSuffix(sessionPath.getFileName().toString(), QoderConstants.SESSION_FILE_SUFFIX);
  }

  /**
   * 从会话文件路径中提取项目键。
   *
   * <p>项目键为项目目录名经过 URL 解码后的值。若解码失败或解码结果为 {@code "."}， 则使用原始目录名。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 项目键
   */
  private static String extractProjectKey(Path rootPath, Path sessionPath) {
    Path relative = toRelative(rootPath, sessionPath);
    int nameCount = relative.getNameCount();
    if (nameCount >= 2) {
      String dirName = relative.getName(nameCount - 2).toString();
      return urlDecodeProjectKey(dirName);
    }
    return "";
  }

  /**
   * 对项目目录名进行 URL 解码。
   *
   * <p>Qoder 使用 URL 编码的项目路径作为目录名。解码失败时回退到原始名称。 解码结果为 {@code "."} 时也使用原始目录名。
   *
   * @param dirName 原始目录名
   * @return URL 解码后的项目键
   */
  private static String urlDecodeProjectKey(String dirName) {
    try {
      String decoded = URLDecoder.decode(dirName, StandardCharsets.UTF_8);
      // 解码结果为 "." 时使用原始目录名
      if (".".equals(decoded)) {
        return dirName;
      }
      return decoded;
    } catch (IllegalArgumentException e) {
      // URL 解码失败，回退到原始目录名
      return dirName;
    }
  }

  /**
   * 将绝对路径转为相对于根目录的路径。
   *
   * @param rootPath 根目录
   * @param filePath 文件路径
   * @return 相对路径
   */
  private static Path toRelative(Path rootPath, Path filePath) {
    try {
      return rootPath
          .toAbsolutePath()
          .normalize()
          .relativize(filePath.toAbsolutePath().normalize());
    } catch (IllegalArgumentException e) {
      return filePath;
    }
  }

  /**
   * 去除字符串末尾的指定后缀内容，若不存在则返回原文本。
   *
   * @param text 原始文本
   * @param suffix 待去除的后缀
   * @return 去除后缀后的文本，或原文本
   */
  private static String stripSuffix(String text, String suffix) {
    if (text.endsWith(suffix)) {
      return text.substring(0, text.length() - suffix.length());
    }
    return text;
  }
}

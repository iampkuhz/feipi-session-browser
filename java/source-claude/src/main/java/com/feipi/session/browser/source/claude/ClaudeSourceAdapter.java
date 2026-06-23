package com.feipi.session.browser.source.claude;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.json.JsonCandidateParser;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourcePathOps;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Claude Code 源适配器实现。
 *
 * <p>实现 {@link SourceAdapter} SPI 接口，负责从 Claude Code 本地数据目录 发现会话文件、生成文件指纹和解析 JSONL 会话内容。
 *
 * <p>Claude Code 会话目录结构：
 *
 * <pre>{@code
 * {root}/
 *   projects/
 *     {project-dir}/
 *       {session-id}.jsonl
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
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code CodexSourceAdapter}、{@code QoderSourceAdapter}
 * 存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：三者分别实现 {@link SourceAdapter} SPI， 各 provider
 * 数据格式不同但适配逻辑结构一致（目录遍历、指纹计算、JSONL 解析、诊断构建）。 此重复是 SPI 适配器模式的固有特征，不宜提取公共基类以避免 provider 间耦合。
 */
public final class ClaudeSourceAdapter implements SourceAdapter {

  private static final Logger LOG = Logger.getLogger(ClaudeSourceAdapter.class.getName());

  private final JsonlReader jsonlReader;

  /** 使用默认 JSONL 读取器配置创建适配器。 */
  public ClaudeSourceAdapter() {
    this(new JsonlReader());
  }

  /**
   * 使用指定 JSONL 读取器创建适配器。
   *
   * @param jsonlReader JSONL 读取器实例，不得为 null
   */
  public ClaudeSourceAdapter(JsonlReader jsonlReader) {
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    this.jsonlReader = jsonlReader;
  }

  @Override
  public SourceId sourceId() {
    return SourceId.CLAUDE_CODE;
  }

  /**
   * 从源根目录发现候选会话。
   *
   * <p>遍历项目目录，找到所有 {@code .jsonl} 会话文件，按路径排序。 目录不存在或为空时返回空的 {@link BoundedStream}。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    List<Path> sessionPaths = ClaudeDiscovery.discoverSessions(rootPath);
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
      String hash = SourcePathOps.computeSha256(filePath);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.CLAUDE_CODE,
          size,
          lastModified,
          Optional.of(hash),
          Optional.of(SourceConstants.DEFAULT_HASH_ALGORITHM));
    } catch (IOException e) {
      // 文件不存在或无法访问，返回零值指纹
      LOG.log(Level.FINE, "无法生成文件指纹: " + filePath, e);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.CLAUDE_CODE,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }
  }

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>使用 {@link JsonlReader} 解析 JSONL 文件，将每个 JSON 事件转为源中性 {@link SourceRecord}。 缺少 {@code type}
   * 字段的事件产生 {@code UNKNOWN_BLOCK_TYPE} 诊断警告，但不会丢失整个 session。 文件不存在返回 {@link
   * SourceResult.Skipped}，IO 错误返回 {@link SourceResult.Fatal}， 解析成功（含诊断）返回 {@link
   * SourceResult.Success}。
   *
   * @param candidate 待解析的候选项
   * @param cancellation 可选的取消信号
   * @return 密封的解析结果
   */
  @Override
  public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
    return JsonCandidateParser.parse(
        candidate,
        cancellation,
        jsonlReader,
        ClaudeSourceAdapter::extractEventType,
        ClaudeSourceAdapter::collectEventDiagnostics,
        (diagnostics, eventCount) -> {});
  }

  private static void collectEventDiagnostics(
      JsonNode event,
      int eventIndex,
      String eventType,
      String locator,
      List<SourceDiagnostic> diagnostics) {
    if (!eventType.equals(ClaudeConstants.EVENT_TYPE_UNKNOWN)) {
      return;
    }
    diagnostics.add(
        new SourceDiagnostic(
            ParseSeverity.WARNING,
            ParseIssueType.NON_OBJECT_SKIPPED,
            "Event at index " + eventIndex + " missing 'type' field",
            eventIndex + 1,
            Optional.empty(),
            ClaudeConstants.DIAG_CODE_MISSING_TYPE,
            locator,
            OptionalInt.empty(),
            OptionalInt.empty(),
            OptionalInt.empty()));
  }

  /**
   * 从 JSON 事件节点中提取 {@code type} 字段值。
   *
   * <p>当字段缺失或不是字符串时返回 {@link ClaudeConstants#EVENT_TYPE_UNKNOWN}。
   *
   * @param event JSON 事件节点
   * @return 非 null 的事件类型
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      return typeNode.asText();
    }
    return ClaudeConstants.EVENT_TYPE_UNKNOWN;
  }

  /**
   * 从会话文件路径中提取会话键。
   *
   * <p>会话键格式为 {@code {project-dir}/{session-id}}，其中 session-id 为 去掉 {@code .jsonl} 后缀的文件名。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 会话键
   */
  private static String extractSessionKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    // 目录结构为 {@code projects/项目名/会话.jsonl}，相对路径至少包含三段
    int nameCount = relative.getNameCount();
    if (nameCount >= 3) {
      String project = relative.getName(nameCount - 2).toString();
      String fileName = relative.getName(nameCount - 1).toString();
      String sessionId = SourcePathOps.stripSuffix(fileName, ClaudeConstants.SESSION_FILE_SUFFIX);
      return project + "/" + sessionId;
    }
    // 回退：使用文件名去后缀
    return SourcePathOps.stripSuffix(
        sessionPath.getFileName().toString(), ClaudeConstants.SESSION_FILE_SUFFIX);
  }

  /**
   * 从会话文件路径中提取项目键。
   *
   * <p>项目键为项目目录名（{@code projects/} 下的直接子目录）。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 项目键
   */
  private static String extractProjectKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    int nameCount = relative.getNameCount();
    if (nameCount >= 3) {
      return relative.getName(nameCount - 2).toString();
    }
    return "";
  }
}

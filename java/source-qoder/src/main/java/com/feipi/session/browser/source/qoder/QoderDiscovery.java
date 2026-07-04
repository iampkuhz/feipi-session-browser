package com.feipi.session.browser.source.qoder;

import com.feipi.session.browser.source.spi.SourcePathOps;
import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Qoder 会话发现逻辑。
 *
 * <p>递归遍历 Qoder 项目目录结构，发现所有 {@code .jsonl} 会话文件。 Qoder 有两个会话目录：
 *
 * <ul>
 *   <li>{@code {root}/projects/} — 主会话目录，project_key 为 URL-decoded 相对路径
 *   <li>{@code {root}/cache/projects/} — 缓存会话目录，project_key 为第一层目录名去掉末尾 hash
 * </ul>
 *
 * <p>对每个项目目录执行递归遍历，支持发现任意深度嵌套的会话文件，
 * 例如 {@code cache/projects/<key>/conversation-history/<id>/<id>.jsonl}。
 * 发现结果按完整路径确定性排序。不跟随符号链接以避免循环。
 *
 * <p>提供 {@link #buildCanonicalIdMap} 用于将 cache 中的短 ID 映射到 projects 中的完整 UUID，
 * 与 Python 主分支 {@code _build_canonical_id_map()} 语义对齐。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class QoderDiscovery {

  private static final Logger LOG = Logger.getLogger(QoderDiscovery.class.getName());

  /** 匹配 UUID 格式：8-4-4-4-12 十六进制。 */
  private static final Pattern UUID_PATTERN =
      Pattern.compile(
          "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$");

  /** 匹配末尾 hash 后缀：{@code -[0-9a-f]{6,}}。 */
  private static final Pattern HASH_SUFFIX_PATTERN = Pattern.compile("-[0-9a-f]{6,}$");

  private QoderDiscovery() {
    // 工具类，禁止实例化
  }

  /** 会话来源：projects/ 或 cache/projects/。 */
  public enum SourceKind {
    PROJECTS,
    CACHE
  }

  /**
   * 结构化发现结果：单个会话文件的路径、项目键和来源。
   *
   * @param path 会话文件完整路径
   * @param projectKey 与 Python 主分支对齐的项目键
   * @param sessionId 会话 ID（文件名去掉 .jsonl）
   * @param sourceKind 来源目录类型
   */
  public record QoderDiscoveredSession(
      Path path, String projectKey, String sessionId, SourceKind sourceKind) {}

  /**
   * 结构化发现结果集合。
   *
   * @param sessions 所有发现的会话
   */
  public record QoderDiscoveryResult(List<QoderDiscoveredSession> sessions) {
    public QoderDiscoveryResult {
      sessions = List.copyOf(sessions);
    }
  }

  /**
   * 从根目录发现所有 Qoder 会话文件（结构化结果）。
   *
   * <p>遍历 {@code projects/} 和 {@code cache/projects/} 两个子树，
   * 为每个会话文件提取 projectKey（与 Python 主分支对齐）和 sessionId。
   * 全局按路径排序，保证确定性。
   *
   * @param rootPath 源根目录路径
   * @return 结构化发现结果
   */
  public static QoderDiscoveryResult discoverSessionsStructured(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return new QoderDiscoveryResult(List.of());
    }

    List<QoderDiscoveredSession> allSessions = new ArrayList<>();

    // 遍历主 projects/ 目录
    Path projectsDir = rootPath.resolve(QoderConstants.PROJECTS_DIR);
    if (Files.isDirectory(projectsDir)) {
      collectSessionsWithKey(
          projectsDir,
          SourceKind.PROJECTS,
          projectDir -> {
            // project_key = 相对于 projectsDir 的路径，URL decode
            String relativePath = projectsDir.relativize(projectDir).toString();
            String decoded = urlDecode(relativePath);
            if (decoded.isEmpty() || ".".equals(decoded)) {
              return projectDir.getFileName().toString();
            }
            return decoded;
          },
          allSessions);
    }

    // 遍历 cache/projects/ 目录
    Path cacheProjectsDir = rootPath.resolve(QoderConstants.CACHE_PROJECTS_DIR);
    if (Files.isDirectory(cacheProjectsDir)) {
      collectSessionsWithKey(
          cacheProjectsDir,
          SourceKind.CACHE,
          projectDir -> {
            // cache project_key = 第一层目录名，去掉末尾 hash
            return stripHashSuffix(projectDir.getFileName().toString());
          },
          allSessions);
    }

    allSessions.sort(Comparator.comparing(s -> s.path().toString()));
    return new QoderDiscoveryResult(allSessions);
  }

  /**
   * 从根目录发现所有 Qoder 会话文件（向后兼容，返回路径列表）。
   *
   * @param rootPath 源根目录路径
   * @return 按路径排序的会话文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    QoderDiscoveryResult result = discoverSessionsStructured(rootPath);
    List<Path> paths = new ArrayList<>(result.sessions().size());
    for (QoderDiscoveredSession s : result.sessions()) {
      paths.add(s.path());
    }
    return paths;
  }

  /**
   * 构建短 ID → 完整 UUID 的 canonical map。
   *
   * <p>与 Python 主分支 {@code _build_canonical_id_map()} 语义对齐：
   * <ol>
   *   <li>从 projects/ 收集所有完整 UUID 格式的 session ID
   *   <li>从 cache/projects/ 收集所有非 UUID 的短 ID
   *   <li>短 ID 唯一前缀匹配某个完整 UUID 时建立映射
   * </ol>
   *
   * @param result 结构化发现结果
   * @return 短 ID (lowercase) → 完整 UUID (lowercase) 的不可变映射
   */
  public static Map<String, String> buildCanonicalIdMap(QoderDiscoveryResult result) {
    // 从 projects/ 收集完整 UUID
    List<String> fullUuids = new ArrayList<>();
    for (QoderDiscoveredSession s : result.sessions()) {
      if (s.sourceKind() == SourceKind.PROJECTS && UUID_PATTERN.matcher(s.sessionId()).matches()) {
        fullUuids.add(s.sessionId().toLowerCase(Locale.ROOT));
      }
    }

    // 从 cache/ 收集短 ID
    List<String> shortIds = new ArrayList<>();
    for (QoderDiscoveredSession s : result.sessions()) {
      if (s.sourceKind() == SourceKind.CACHE
          && !UUID_PATTERN.matcher(s.sessionId()).matches()) {
        shortIds.add(s.sessionId().toLowerCase(Locale.ROOT));
      }
    }

    // 前缀匹配：仅唯一匹配时建立映射
    Map<String, String> canonicalMap = new LinkedHashMap<>();
    for (String shortId : shortIds) {
      List<String> matches = new ArrayList<>();
      for (String uuid : fullUuids) {
        if (uuid.startsWith(shortId)) {
          matches.add(uuid);
        }
      }
      if (matches.size() == 1) {
        canonicalMap.put(shortId, matches.get(0));
      }
    }
    return Map.copyOf(canonicalMap);
  }

  /**
   * 去掉 cache project key 末尾的 hash 后缀。
   *
   * <p>例如 {@code "my-project-462acd20"} → {@code "my-project"}。
   *
   * @param rawKey 原始 project key
   * @return 去掉 hash 后缀的 key
   */
  public static String stripHashSuffix(String rawKey) {
    return HASH_SUFFIX_PATTERN.matcher(rawKey).replaceAll("");
  }

  /**
   * 检查 session ID 是否为完整 UUID 格式。
   *
   * @param sessionId 会话 ID
   * @return 是否为 UUID
   */
  public static boolean isFullUuid(String sessionId) {
    return sessionId != null && UUID_PATTERN.matcher(sessionId).matches();
  }

  // ---- 内部实现 ----

  /**
   * 通用收集逻辑：遍历父目录下的项目子目录，为每个 session 文件生成结构化发现结果。
   *
   * <p>将 projects/ 和 cache/projects/ 共享的遍历循环提取为统一方法， 通过 {@code projectKeyFn}
   * 参数差异化 project key 的计算逻辑。
   *
   * @param parentDir 项目父目录
   * @param sourceKind 来源类型
   * @param projectKeyFn 从父目录和当前项目目录计算 project key 的函数
   * @param accumulator 结果收集器
   */
  private static void collectSessionsWithKey(
      Path parentDir,
      SourceKind sourceKind,
      Function<Path, String> projectKeyFn,
      List<QoderDiscoveredSession> accumulator) {
    List<Path> projectDirs = listSortedDirectories(parentDir);
    for (Path projectDir : projectDirs) {
      if (SourcePathOps.isHidden(projectDir)) {
        continue;
      }
      String projectKey = projectKeyFn.apply(projectDir);
      List<Path> sessionFiles = listSortedSessions(projectDir);
      for (Path sessionFile : sessionFiles) {
        String fileName = sessionFile.getFileName().toString();
        String sessionId = SourcePathOps.stripSuffix(fileName, QoderConstants.SESSION_FILE_SUFFIX);
        accumulator.add(new QoderDiscoveredSession(sessionFile, projectKey, sessionId, sourceKind));
      }
    }
  }

  /** URL decode，失败时回退原始字符串。 */
  private static String urlDecode(String encoded) {
    try {
      return URLDecoder.decode(encoded, StandardCharsets.UTF_8);
    } catch (Exception e) {
      return encoded;
    }
  }

  /**
   * 列出目录中的子目录，按名称排序。
   *
   * @param dir 父目录
   * @return 排序后的子目录列表
   */
  private static List<Path> listSortedDirectories(Path dir) {
    List<Path> dirs = new ArrayList<>();
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (Files.isDirectory(entry) && !SourcePathOps.isHidden(entry)) {
          dirs.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取目录: " + dir, e);
      return List.of();
    }
    dirs.sort(Comparator.comparing(p -> p.getFileName().toString()));
    return List.copyOf(dirs);
  }

  /**
   * 递归列出项目目录中的所有会话 JSONL 文件，按完整路径排序。
   *
   * <p>使用 {@link Files#walk} 递归遍历项目目录的任意深度子目录，
   * 发现所有 {@code .jsonl} 文件（例如 {@code conversation-history/<id>/<id>.jsonl}）。
   * 跳过隐藏目录、隐藏文件和非普通文件。不跟随符号链接以避免循环。
   *
   * @param projectDir 项目目录
   * @return 按完整路径排序的会话文件列表，截断至 {@link QoderConstants#MAX_SESSIONS_PER_PROJECT}
   */
  private static List<Path> listSortedSessions(Path projectDir) {
    List<Path> sessions = new ArrayList<>();
    try (Stream<Path> walk = Files.walk(projectDir)) {
      walk.filter(path -> !path.equals(projectDir))
          .filter(path -> {
            if (SourcePathOps.isHidden(path)) {
              return false;
            }
            if (!Files.isRegularFile(path)) {
              return false;
            }
            // 检查路径中是否存在隐藏的祖先目录
            Path relative = projectDir.relativize(path);
            for (int i = 0; i < relative.getNameCount() - 1; i++) {
              if (SourcePathOps.isHidden(projectDir.resolve(relative.subpath(0, i + 1)))) {
                return false;
              }
            }
            return path.getFileName().toString().endsWith(QoderConstants.SESSION_FILE_SUFFIX);
          })
          .forEach(sessions::add);
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法递归遍历项目目录: " + projectDir, e);
      return List.of();
    }
    sessions.sort(Comparator.comparing(Path::toString));
    // 截断到上限
    if (sessions.size() > QoderConstants.MAX_SESSIONS_PER_PROJECT) {
      sessions = sessions.subList(0, QoderConstants.MAX_SESSIONS_PER_PROJECT);
    }
    return List.copyOf(sessions);
  }
}

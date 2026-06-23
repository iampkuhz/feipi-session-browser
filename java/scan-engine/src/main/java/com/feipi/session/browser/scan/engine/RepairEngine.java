package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceAdapter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Java repair 引擎。
 *
 * <p>实现源删除、路径移动、孤儿清理和 repair 状态机，所有动作幂等。
 *
 * <p>核心操作：
 *
 * <ol>
 *   <li>加载 DB 中全部已索引会话指纹（{@link FingerprintRepository#loadAll}）。
 *   <li>对每个源条目：检查根目录可访问性 → 逐已索引会话检查源文件存在性 → 重命名检测。
 *   <li>汇总 repair 决策列表。
 *   <li>执行决策：删除 DB row/artifact、更新路径、删除孤儿 artifact。
 *   <li>返回 {@link RepairSummary} 审计摘要。
 * </ol>
 *
 * <p>区分五种状态：
 *
 * <ul>
 *   <li>{@link RepairAction#CONFIRMED_DELETE} — 源文件确认不存在，安全删除。
 *   <li>{@link RepairAction#ROOT_UNAVAILABLE} — 根目录不可访问，保留 DB row 不做删除。
 *   <li>{@link RepairAction#SOURCE_MISSING_TEMPORARY} — 源文件暂时缺失，暂不删除。
 *   <li>{@link RepairAction#RENAME_DETECTED} — 检测到重命名/移动，更新路径。
 *   <li>{@link RepairAction#NO_ACTION} — 源文件存在且路径未变化。
 * </ul>
 *
 * <p>临时 root unavailable 不批量删除，避免网络文件系统断开导致数据丢失。
 *
 * <p>校验放置：根目录安全检查在 {@link SourceAdapter#checkRoot} 边界执行一次； 文件存在性检查只在本层执行，不在下游重复。
 */
public final class RepairEngine {

  private static final Logger log = LoggerFactory.getLogger(RepairEngine.class);

  /**
   * 执行 repair：分析并执行所有 repair 决策。
   *
   * <p>等价于先调用 {@link #analyze} 再调用 {@link #execute}。
   *
   * @param writeConn SQLite 写连接
   * @param sourceEntries 源条目列表
   * @param artifactDir artifact 输出目录
   * @return repair 汇总结果
   * @throws NullPointerException 当参数为 null 时
   */
  public RepairSummary repair(
      Connection writeConn, List<ScanConfig.SourceEntry> sourceEntries, Path artifactDir) {
    Objects.requireNonNull(writeConn, "writeConn 不得为 null");
    Objects.requireNonNull(sourceEntries, "sourceEntries 不得为 null");
    Objects.requireNonNull(artifactDir, "artifactDir 不得为 null");

    List<RepairDecision> decisions = analyze(writeConn, sourceEntries);
    return execute(writeConn, decisions, artifactDir);
  }

  /**
   * 分析 repair 决策，不执行任何修改。
   *
   * <p>遍历所有已索引会话，检查源文件存在性和根目录可访问性， 生成 repair 决策列表。
   *
   * @param conn SQLite 连接
   * @param sourceEntries 源条目列表
   * @return repair 决策列表，按 session key 排序
   */
  public List<RepairDecision> analyze(Connection conn, List<ScanConfig.SourceEntry> sourceEntries) {
    Objects.requireNonNull(conn, "conn 不得为 null");
    Objects.requireNonNull(sourceEntries, "sourceEntries 不得为 null");

    // 加载全部已索引会话指纹
    Map<String, StoredSessionFingerprint> storedFingerprints;
    try {
      storedFingerprints = FingerprintRepository.loadAll(conn);
    } catch (SQLException e) {
      log.error("加载已索引指纹失败", e);
      return List.of();
    }

    // 构建 agent → 源条目映射
    Map<String, SourceEntryInfo> sourceByAgent = buildSourceMap(sourceEntries);

    // 逐已索引会话分析
    List<RepairDecision> decisions = new ArrayList<>();

    for (StoredSessionFingerprint fp : storedFingerprints.values()) {
      String agent = fp.agent();
      SourceEntryInfo entry = sourceByAgent.get(agent);

      if (entry == null) {
        // 无对应源条目（可能是已删除的 agent 类型），暂时保留
        decisions.add(RepairDecision.sourceMissingTemporary(fp));
        continue;
      }

      // 检查根目录可访问性
      if (!RenameDetector.isRootAccessible(entry.adapter, entry.rootPath)) {
        decisions.add(RepairDecision.rootUnavailable(fp));
        continue;
      }

      // 检查源文件是否存在
      String storedPath = fp.filePath();
      if (storedPath.isEmpty()) {
        // 无存储路径，跳过（可能是历史数据）
        decisions.add(RepairDecision.sourceMissingTemporary(fp));
        continue;
      }

      Path sourceFile = Path.of(storedPath);
      if (Files.exists(sourceFile)) {
        // 源文件存在
        decisions.add(RepairDecision.noAction(fp));
        continue;
      }

      // 源文件不存在，尝试重命名检测
      var renameResult =
          RenameDetector.detectRename(entry.adapter, entry.rootPath, fp.sessionKey());
      if (renameResult.isPresent()) {
        decisions.add(RepairDecision.renameDetected(fp, renameResult.get().newFilePath()));
      } else {
        // 源文件确认不存在，标记删除
        decisions.add(RepairDecision.confirmedDelete(fp, "源文件不存在: " + storedPath));
      }
    }

    // 按 session key 排序，保证确定性输出
    decisions.sort(Comparator.comparing(d -> d.fingerprint().sessionKey()));
    return List.copyOf(decisions);
  }

  /**
   * 执行 repair 决策。
   *
   * <p>按决策类型执行：删除 DB row/artifact、更新路径、删除孤儿 artifact。 单行失败不中断批量操作，错误记录到 {@link RepairSummary}。
   *
   * <p>幂等：重复执行产生相同结果，已删除的行不会再次删除。
   *
   * @param writeConn SQLite 写连接
   * @param decisions repair 决策列表
   * @param artifactDir artifact 输出目录
   * @return repair 汇总结果
   * @throws NullPointerException 当参数为 null 时
   */
  public RepairSummary execute(
      Connection writeConn, List<RepairDecision> decisions, Path artifactDir) {
    Objects.requireNonNull(writeConn, "writeConn 不得为 null");
    Objects.requireNonNull(decisions, "decisions 不得为 null");
    Objects.requireNonNull(artifactDir, "artifactDir 不得为 null");

    long startMs = System.currentTimeMillis();

    int deletedCount = 0;
    int renamedCount = 0;
    int keptCount = 0;
    int rootUnavailableCount = 0;
    int temporaryMissingCount = 0;
    List<String> errors = new ArrayList<>();

    // 收集所有存活的 session key（用于孤儿 artifact 检测）
    Set<String> survivingSessionKeys = new HashSet<>();

    for (RepairDecision decision : decisions) {
      String sessionKey = decision.fingerprint().sessionKey();

      switch (decision.action()) {
        case NO_ACTION -> {
          keptCount++;
          survivingSessionKeys.add(sessionKey);
        }
        case ROOT_UNAVAILABLE -> {
          rootUnavailableCount++;
          survivingSessionKeys.add(sessionKey);
        }
        case SOURCE_MISSING_TEMPORARY -> {
          temporaryMissingCount++;
          survivingSessionKeys.add(sessionKey);
        }
        case RENAME_DETECTED -> {
          try {
            String newPath = decision.newFilePath().orElseThrow();
            double newMtime = getNewFileMtime(newPath);
            int updated =
                SessionDeleter.updateSessionPath(writeConn, sessionKey, newPath, newMtime);
            if (updated > 0) {
              renamedCount++;
              survivingSessionKeys.add(sessionKey);
            } else {
              errors.add("更新路径失败（行不存在）: " + sessionKey);
            }
          } catch (SQLException e) {
            errors.add("更新路径 SQL 失败: " + sessionKey + ": " + e.getMessage());
          }
        }
        case CONFIRMED_DELETE -> {
          try {
            SessionDeleter.deleteSession(writeConn, sessionKey);
            deletedCount++;
            // 不加入 survivingSessionKeys
          } catch (SQLException e) {
            errors.add("删除会话 SQL 失败: " + sessionKey + ": " + e.getMessage());
            survivingSessionKeys.add(sessionKey);
          }
        }
      }
    }

    // 删除孤儿 artifact
    int artifactOrphanCount = 0;
    try {
      artifactOrphanCount =
          SessionDeleter.deleteOrphanArtifacts(artifactDir, survivingSessionKeys, errors);
    } catch (Exception e) {
      errors.add("孤儿 artifact 清理失败: " + e.getMessage());
    }

    long durationMs = System.currentTimeMillis() - startMs;

    log.info(
        "Repair 完成: deleted={}, renamed={}, kept={}, rootUnavailable={}, "
            + "temporaryMissing={}, artifactOrphans={}, errors={}, duration={}ms",
        deletedCount,
        renamedCount,
        keptCount,
        rootUnavailableCount,
        temporaryMissingCount,
        artifactOrphanCount,
        errors.size(),
        durationMs);

    return new RepairSummary(
        deletedCount,
        renamedCount,
        keptCount,
        rootUnavailableCount,
        temporaryMissingCount,
        artifactOrphanCount,
        decisions,
        errors,
        durationMs);
  }

  /**
   * 构建 agent 协议值到源条目的映射。
   *
   * <p>同一 agent 如果有多个源条目（多个根目录），使用第一个。
   */
  private static Map<String, SourceEntryInfo> buildSourceMap(
      List<ScanConfig.SourceEntry> sourceEntries) {
    Map<String, SourceEntryInfo> result = new LinkedHashMap<>();
    for (ScanConfig.SourceEntry entry : sourceEntries) {
      String agentValue = entry.adapter().sourceId().getValue();
      result.putIfAbsent(agentValue, new SourceEntryInfo(entry.adapter(), entry.rootPath()));
    }
    return result;
  }

  /**
   * 获取新文件的 mtime（epoch 秒）。
   *
   * @param filePath 文件路径
   * @return epoch 秒，获取失败时返回 0
   */
  private static double getNewFileMtime(String filePath) {
    try {
      long mtimeMs = Files.getLastModifiedTime(Path.of(filePath)).toMillis();
      return mtimeMs / 1000.0;
    } catch (Exception e) {
      return 0.0;
    }
  }

  /** 源条目信息内部记录。 */
  private record SourceEntryInfo(SourceAdapter adapter, Path rootPath) {

    SourceEntryInfo {
      Objects.requireNonNull(adapter, "adapter 不得为 null");
      Objects.requireNonNull(rootPath, "rootPath 不得为 null");
    }
  }
}

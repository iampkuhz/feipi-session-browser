package com.feipi.session.browser.artifact.normalized;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.channels.FileChannel;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 失败安全的归一化制品文件写入器。
 *
 * <p>将 {@link NormalizedSessionArtifact} 序列化为确定性 JSON 文件， 并附带 SHA-256 元数据。写入流程使用临时文件 +
 * 原子重命名模式，确保中间状态不会被识别为有效制品。
 *
 * <p>写入顺序：先写数据文件，后写 meta 文件（meta 最后提交）。 只有在 meta 文件成功写入后，制品才被视为完整。
 *
 * <p>并发安全：
 *
 * <ul>
 *   <li>同一 artifact key（session key）在同一 JVM 内互斥写入。
 *   <li>不同 artifact key 可以安全地并行写入。
 *   <li>所有字段均为不可变或线程安全的。
 * </ul>
 *
 * <p>路径安全：
 *
 * <ul>
 *   <li>artifact key 经过 {@link SafeArtifactName} 清洗，防止路径遍历。
 *   <li>写入后验证目标路径仍在 output root 内（包括 symlink 逃逸检查）。
 *   <li>source fingerprint 的 key 经过 home 路径脱敏处理。
 * </ul>
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类内部 doWrite、validate、readMeta、extractSessionKey 等方法
 * 存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：均为文件 IO 和元数据操作， 遵循相同的 path-validation + IO + error-handling
 * 模式。此重复是安全写入流程的固有特征。
 */
public final class NormalizedArtifactWriter {

  private static final DateTimeFormatter ISO_FORMATTER = DateTimeFormatter.ISO_OFFSET_DATE_TIME;

  private final CanonicalJsonWriter canonicalJsonWriter;
  private final ObjectMapper mapper;
  private final Clock clock;

  /** 每个 artifact key 一个锁，用于同 JVM 内同 key 互斥写入。 */
  private final ConcurrentHashMap<String, ReentrantLock> keyLocks = new ConcurrentHashMap<>();

  /** 创建使用系统时钟的默认写入器。 */
  public NormalizedArtifactWriter() {
    this(Clock.systemUTC());
  }

  /**
   * 创建使用指定时钟的写入器（用于测试确定性）。
   *
   * @param clock 注入时钟，不得为 null
   */
  public NormalizedArtifactWriter(Clock clock) {
    Objects.requireNonNull(clock, "clock 不得为 null");
    this.canonicalJsonWriter = new CanonicalJsonWriter();
    this.mapper = new ObjectMapper();
    this.clock = clock;
  }

  /**
   * 将归一化制品写入指定目录并返回写入结果。
   *
   * <p>写入流程：
   *
   * <ol>
   *   <li>清洗 session key，检查路径安全。
   *   <li>获取该 key 的写锁（同 key 互斥）。
   *   <li>使用 {@link CanonicalJsonWriter} 序列化 artifact 为 byte[]。
   *   <li>计算 SHA-256 hash。
   *   <li>构建 {@link ArtifactMeta}（含 exact hash/size）。
   *   <li>写入数据文件（临时文件 -> 同步 -> 原子重命名）。
   *   <li>验证路径安全（路径遍历 + symlink 逃逸）。
   *   <li>写入 meta 文件（临时文件 -> 同步 -> 原子重命名）。
   *   <li>验证路径安全。
   *   <li>释放锁。
   * </ol>
   *
   * @param outputDir 输出目录，必须已存在
   * @param artifact 要写入的归一化制品
   * @param sourceFingerprints 源路径到内容哈希的映射
   * @return 写入结果，包含路径、hash、大小和状态
   * @throws IOException 当写入过程发生 I/O 错误时
   */
  public WriteResult write(
      Path outputDir, NormalizedSessionArtifact artifact, Map<String, String> sourceFingerprints)
      throws IOException {
    Objects.requireNonNull(outputDir, "outputDir 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(sourceFingerprints, "sourceFingerprints 不得为 null");

    String sessionKey = extractSessionKey(artifact);
    String safeName = SafeArtifactName.sanitize(sessionKey);

    return withLock(sessionKey, () -> doWrite(outputDir, artifact, sourceFingerprints, safeName));
  }

  /**
   * 读取并反序列化 meta 文件。
   *
   * @param metaFile meta 文件路径
   * @return 反序列化后的 {@link ArtifactMeta}
   * @throws IOException 当读取或解析失败时
   */
  public ArtifactMeta readMeta(Path metaFile) throws IOException {
    Objects.requireNonNull(metaFile, "metaFile 不得为 null");
    byte[] bytes = Files.readAllBytes(metaFile);
    return mapper.readValue(bytes, ArtifactMeta.class);
  }

  /**
   * 验证数据文件的内容哈希与 meta 文件中记录的一致。
   *
   * <p>检查 hash 和 size 均匹配。当 meta 文件不存在时返回 {@code false}（中间状态不被视为有效）。
   *
   * @param dataFile 数据文件路径
   * @param metaFile meta 文件路径
   * @return 当 hash 和 size 均匹配时返回 {@code true}
   * @throws IOException 当读取文件失败时
   */
  public boolean validate(Path dataFile, Path metaFile) throws IOException {
    Objects.requireNonNull(dataFile, "dataFile 不得为 null");
    Objects.requireNonNull(metaFile, "metaFile 不得为 null");

    if (!Files.exists(metaFile)) {
      return false;
    }
    if (!Files.exists(dataFile)) {
      return false;
    }

    ArtifactMeta meta = readMeta(metaFile);
    byte[] dataBytes = Files.readAllBytes(dataFile);
    String actualHash = sha256Hex(dataBytes);

    return meta.contentHash().equals(actualHash) && meta.contentSize() == dataBytes.length;
  }

  /**
   * 执行实际写入操作。
   *
   * <p>先写数据文件，后写 meta 文件。每步写入后均验证路径安全。
   */
  private WriteResult doWrite(
      Path outputDir,
      NormalizedSessionArtifact artifact,
      Map<String, String> sourceFingerprints,
      String safeName)
      throws IOException {

    // 1. 序列化 artifact（确定性字节输出）
    byte[] dataBytes = canonicalJsonWriter.serialize(artifact);

    // 2. 计算 SHA-256
    String contentHash = sha256Hex(dataBytes);

    // 3. 脱敏 source fingerprint key（去除用户绝对 home path）
    Map<String, String> sanitizedFingerprints = sanitizeFingerprintKeys(sourceFingerprints);

    // 4. 构建 meta（使用注入 clock 保证确定性）
    ArtifactMeta meta = buildMeta(contentHash, dataBytes.length, sanitizedFingerprints);

    // 5. 序列化 meta（确定性字节输出）
    byte[] metaBytes = canonicalJsonWriter.serializeObject(meta);

    // 6. 构建目标路径
    Path dataFile = outputDir.resolve(safeName + ArtifactConstants.DATA_FILE_SUFFIX);
    Path metaFile = outputDir.resolve(safeName + ArtifactConstants.META_FILE_SUFFIX);

    // 7. 验证路径安全（写入前检查）
    SafeArtifactName.validateWithinRoot(outputDir, dataFile);
    SafeArtifactName.validateWithinRoot(outputDir, metaFile);

    // 8. 先写数据文件
    writeAtomic(dataFile, dataBytes);

    // 9. 写入后再验证路径安全
    SafeArtifactName.validateWithinRoot(outputDir, dataFile);

    // 10. 后写 meta 文件（meta 最后提交，确保中间状态不被视为有效）
    writeAtomic(metaFile, metaBytes);

    // 11. meta 写入后再验证路径安全
    SafeArtifactName.validateWithinRoot(outputDir, metaFile);

    return new WriteResult(
        dataFile.toAbsolutePath(),
        metaFile.toAbsolutePath(),
        contentHash,
        dataBytes.length,
        "SUCCESS");
  }

  /**
   * 从制品的 session map 中提取 session key。
   *
   * <p>如果没有 session_key 字段，则使用序列化内容的 SHA-256 hash 作为 key。
   *
   * @param artifact 归一化制品
   * @return session key 字符串
   */
  private String extractSessionKey(NormalizedSessionArtifact artifact) {
    Object key = artifact.session().get("session_key");
    if (key != null) {
      String keyStr = key.toString();
      if (!keyStr.isBlank()) {
        return keyStr;
      }
    }
    // 回退：序列化 artifact 后使用内容 hash 作为 key
    byte[] contentBytes = canonicalJsonWriter.serialize(artifact);
    return sha256Hex(contentBytes);
  }

  /**
   * 失败安全的原子文件写入。
   *
   * <p>流程：创建临时文件 -> 写入数据 -> 同步磁盘 -> 原子重命名为目标文件。 如果写入失败，清理临时文件。
   *
   * <p>当底层文件系统不支持原子 move 时，退化为普通 move。由于 meta 最后提交， 中间状态（新 data + 旧 meta）会被 {@link #validate} 的
   * hash 检查检测出来。
   *
   * @param target 目标文件路径
   * @param data 要写入的字节数据
   * @throws IOException 当写入过程发生 I/O 错误时
   */
  void writeAtomic(Path target, byte[] data) throws IOException {
    Path dir = target.getParent();
    Path tempFile = dir.resolve(ArtifactConstants.TEMP_FILE_PREFIX + UUID.randomUUID());
    try {
      // 写入临时文件
      Files.write(tempFile, data);

      // 同步文件内容到磁盘
      try (FileChannel channel = FileChannel.open(tempFile, StandardOpenOption.READ)) {
        channel.force(true);
      }

      // 原子重命名；不支持时退化为普通 move
      try {
        Files.move(
            tempFile, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
      } catch (AtomicMoveNotSupportedException e) {
        Files.move(tempFile, target, StandardCopyOption.REPLACE_EXISTING);
      }
    } catch (Exception e) {
      // 失败时清理临时文件
      Files.deleteIfExists(tempFile);
      throw e;
    }
  }

  /**
   * 脱敏 source fingerprint key，去除用户绝对 home path。
   *
   * <p>将 home 目录前缀替换为 {@code ~}，防止持久化用户的绝对路径。
   *
   * @param fingerprints 原始 fingerprint 映射
   * @return 脱敏后的 fingerprint 映射（有序，确保序列化确定性）
   */
  private Map<String, String> sanitizeFingerprintKeys(Map<String, String> fingerprints) {
    String home = getHomePath();
    Map<String, String> result = new LinkedHashMap<>();

    for (Map.Entry<String, String> entry : fingerprints.entrySet()) {
      String sanitizedKey = sanitizePathKey(entry.getKey(), home);
      result.put(sanitizedKey, entry.getValue());
    }

    return result;
  }

  /**
   * 将路径中的 home 前缀替换为 {@code ~}。
   *
   * @param pathKey 原始路径
   * @param homePath home 目录路径
   * @return 脱敏后的路径
   */
  private String sanitizePathKey(String pathKey, String homePath) {
    if (homePath != null && !homePath.isEmpty() && pathKey.startsWith(homePath)) {
      return "~" + pathKey.substring(homePath.length());
    }
    return pathKey;
  }

  /**
   * 获取用户 home 目录路径，失败时返回 null。
   *
   * @return home 目录路径或 null
   */
  private String getHomePath() {
    try {
      String home = System.getProperty("user.home");
      if (home != null && !home.isEmpty()) {
        return home;
      }
    } catch (SecurityException e) {
      // 安全限制下忽略
    }
    return null;
  }

  /**
   * 构建制品元数据。
   *
   * <p>使用注入的 clock 生成时间戳，确保同一输入在相同 clock 下产生确定性的 meta。 meta 包含 exact JSON hash 和 size，与数据文件严格对应。
   *
   * @param contentHash 数据内容 SHA-256 hash
   * @param contentSize 数据内容字节长度
   * @param fingerprints 源 fingerprint 映射
   * @return 构建完成的 ArtifactMeta
   */
  private ArtifactMeta buildMeta(
      String contentHash, long contentSize, Map<String, String> fingerprints) {
    String generatedAt = ISO_FORMATTER.format(clock.instant().atOffset(ZoneOffset.UTC));
    return new ArtifactMeta(
        NormalizedConstants.SCHEMA_VERSION,
        ArtifactConstants.GENERATOR,
        contentHash,
        contentSize,
        generatedAt,
        fingerprints);
  }

  /**
   * 获取指定 key 的写锁并执行操作。
   *
   * <p>确保同一 artifact key 在同一 JVM 内互斥写入。操作完成后自动释放并清理锁。
   *
   * @param key artifact key
   * @param operation 要执行的操作
   * @param <T> 返回值类型
   * @return 操作结果
   * @throws IOException 当操作抛出 IOException 时
   */
  private <T> T withLock(String key, LockOperation<T> operation) throws IOException {
    ReentrantLock lock = keyLocks.computeIfAbsent(key, k -> new ReentrantLock());
    lock.lock();
    try {
      return operation.execute();
    } finally {
      lock.unlock();
      // 清理无竞争的锁，避免内存泄漏
      keyLocks.remove(key, lock);
    }
  }

  /**
   * 计算字节数组的 SHA-256 十六进制摘要。
   *
   * @param data 输入字节数组
   * @return 小写十六进制 SHA-256 摘要
   */
  static String sha256Hex(byte[] data) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(data);
      return HexFormat.of().formatHex(hash);
    } catch (NoSuchAlgorithmException e) {
      throw new UncheckedIOException("SHA-256 算法不可用", new IOException(e));
    }
  }

  /**
   * 在锁内执行的可抛出 IOException 的操作。
   *
   * @param <T> 返回值类型
   */
  @FunctionalInterface
  private interface LockOperation<T> {
    T execute() throws IOException;
  }
}

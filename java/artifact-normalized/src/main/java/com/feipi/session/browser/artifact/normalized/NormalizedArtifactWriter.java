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
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * 失败安全的归一化制品文件写入器。
 *
 * <p>将 {@link NormalizedSessionArtifact} 序列化为确定性 JSON 文件， 并附带 SHA-256
 * 元数据。写入流程使用临时文件原子重命名模式，确保中间状态不会被识别为有效制品。
 *
 * <p>写入顺序：先写数据文件，后写 meta 文件（meta 最后提交）。 只有在 meta 文件成功写入后，制品才被视为完整。
 *
 * <p>该类是线程安全的，所有字段均为不可变的。
 */
public final class NormalizedArtifactWriter {

  private static final DateTimeFormatter ISO_FORMATTER = DateTimeFormatter.ISO_INSTANT;

  private final CanonicalJsonWriter canonicalJsonWriter;
  private final ObjectMapper mapper;

  /** 创建使用默认配置的写入器。 */
  public NormalizedArtifactWriter() {
    this.canonicalJsonWriter = new CanonicalJsonWriter();
    this.mapper = new ObjectMapper();
  }

  /**
   * 将归一化制品写入指定目录。
   *
   * <p>写入流程：
   *
   * <ol>
   *   <li>使用 {@link CanonicalJsonWriter} 序列化 artifact 为 byte[]。
   *   <li>计算 SHA-256 hash。
   *   <li>构建 {@link ArtifactMeta}。
   *   <li>序列化 meta 为 JSON bytes。
   *   <li>生成文件名：{@code {sessionKey}.json} 和 {@code {sessionKey}.meta.json}。
   *   <li>写入数据文件（临时写入 → 同步 → 原子重命名）。
   *   <li>写入 meta 文件（临时写入 → 同步 → 原子重命名）。
   * </ol>
   *
   * @param outputDir 输出目录，必须已存在
   * @param artifact 要写入的归一化制品
   * @param sourceFingerprints 源路径到内容哈希的映射
   * @throws IOException 当写入过程发生 I/O 错误时
   */
  public void write(
      Path outputDir, NormalizedSessionArtifact artifact, Map<String, String> sourceFingerprints)
      throws IOException {
    Objects.requireNonNull(outputDir, "outputDir 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(sourceFingerprints, "sourceFingerprints 不得为 null");

    // 1. 序列化 artifact
    byte[] dataBytes = canonicalJsonWriter.serialize(artifact);

    // 2. 计算 SHA-256
    String contentHash = sha256Hex(dataBytes);

    // 3. 构建 meta
    String generatedAt = ISO_FORMATTER.format(Instant.now().atOffset(ZoneOffset.UTC));
    ArtifactMeta meta =
        new ArtifactMeta(
            NormalizedConstants.SCHEMA_VERSION,
            ArtifactConstants.GENERATOR,
            contentHash,
            dataBytes.length,
            generatedAt,
            sourceFingerprints);

    // 4. 序列化 meta
    byte[] metaBytes = canonicalJsonWriter.serializeObject(meta);

    // 5. 生成文件名
    String sessionKey = extractSessionKey(artifact, dataBytes);
    Path dataFile = outputDir.resolve(sessionKey + ArtifactConstants.DATA_FILE_SUFFIX);
    Path metaFile = outputDir.resolve(sessionKey + ArtifactConstants.META_FILE_SUFFIX);

    // 6. 先写数据文件
    writeAtomic(dataFile, dataBytes);

    // 7. 后写 meta 文件（meta 最后提交）
    writeAtomic(metaFile, metaBytes);
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
   * @param dataFile 数据文件路径
   * @param metaFile meta 文件路径
   * @return 当哈希匹配时返回 {@code true}
   * @throws IOException 当读取文件失败时
   */
  public boolean validate(Path dataFile, Path metaFile) throws IOException {
    Objects.requireNonNull(dataFile, "dataFile 不得为 null");
    Objects.requireNonNull(metaFile, "metaFile 不得为 null");

    ArtifactMeta meta = readMeta(metaFile);
    byte[] dataBytes = Files.readAllBytes(dataFile);
    String actualHash = sha256Hex(dataBytes);

    return meta.contentHash().equals(actualHash) && meta.contentSize() == dataBytes.length;
  }

  /**
   * 从制品的 session map 中提取 session key，如果不存在则使用内容 hash。
   *
   * @param artifact 归一化制品
   * @param contentBytes 序列化后的字节数组，用于回退 hash
   * @return session key 字符串
   */
  private String extractSessionKey(NormalizedSessionArtifact artifact, byte[] contentBytes) {
    Object key = artifact.session().get("session_key");
    if (key != null) {
      return key.toString();
    }
    // 回退：使用内容 hash 作为 session key
    return sha256Hex(contentBytes);
  }

  /**
   * 失败安全的原子文件写入。
   *
   * <p>流程：创建临时文件 → 写入数据 → 同步磁盘 → 原子重命名为目标文件。 如果写入失败，清理临时文件。
   *
   * @param target 目标文件路径
   * @param data 要写入的字节数据
   * @throws IOException 当写入过程发生 I/O 错误时
   */
  private void writeAtomic(Path target, byte[] data) throws IOException {
    Path dir = target.getParent();
    Path tempFile = dir.resolve(ArtifactConstants.TEMP_FILE_PREFIX + UUID.randomUUID());
    try {
      // 写入临时文件
      Files.write(tempFile, data);

      // 同步文件内容到磁盘
      try (FileChannel channel = FileChannel.open(tempFile, StandardOpenOption.READ)) {
        channel.force(true);
      }

      // 原子重命名
      try {
        Files.move(
            tempFile, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
      } catch (AtomicMoveNotSupportedException e) {
        Files.move(tempFile, target, StandardCopyOption.REPLACE_EXISTING);
      }
    } catch (Exception e) {
      // 清理临时文件
      Files.deleteIfExists(tempFile);
      throw e;
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
}

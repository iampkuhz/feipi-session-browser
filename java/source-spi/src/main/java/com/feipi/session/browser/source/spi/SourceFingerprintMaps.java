package com.feipi.session.browser.source.spi;

import java.nio.file.Path;
import java.util.Map;
import java.util.Optional;

/** 源文件指纹 map 构造辅助方法。 */
public final class SourceFingerprintMaps {

  private SourceFingerprintMaps() {}

  /** 构建制品写入使用的绝对路径到内容 hash 映射。 */
  public static Map<String, String> forCandidate(Path filePath, Candidate candidate) {
    Optional<String> hash = candidate.fingerprint().contentHash();
    if (hash.isPresent()) {
      return Map.of(filePath.toAbsolutePath().toString(), hash.get());
    }
    return Map.of();
  }
}

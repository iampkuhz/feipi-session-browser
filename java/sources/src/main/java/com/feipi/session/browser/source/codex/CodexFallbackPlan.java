package com.feipi.session.browser.source.codex;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.function.IntFunction;

/** 后备正文仅索引长度、指纹及原事件位置；哈希命中后仍重放完整 equals。 */
final class CodexFallbackPlan {
  private final Map<Integer, Map<Fingerprint, List<Integer>>> candidates = new HashMap<>();

  /**
   * UTF16 指纹保留所有 Java String code units，不依赖 UTF8 replacement。
   *
   * @param length 正文的 UTF16 长度
   * @param sha256 正文 code units 的 SHA-256 十六进制摘要
   */
  record Fingerprint(int length, String sha256) {}

  static Fingerprint fingerprint(String body) {
    try {
      var digest = MessageDigest.getInstance("SHA-256");
      byte[] buffer = new byte[8192];
      for (int start = 0; start < body.length(); ) {
        int count = Math.min(buffer.length / 2, body.length() - start);
        for (int index = 0; index < count; index++) {
          char ch = body.charAt(start + index);
          buffer[index * 2] = (byte) (ch >>> 8);
          buffer[index * 2 + 1] = (byte) ch;
        }
        digest.update(buffer, 0, count * 2);
        start += count;
      }
      return new Fingerprint(body.length(), HexFormat.of().formatHex(digest.digest()));
    } catch (NoSuchAlgorithmException impossible) {
      throw new IllegalStateException("SHA-256 不可用", impossible);
    }
  }

  void add(int segment, int eventOrdinal, String body) {
    candidates
        .computeIfAbsent(segment, ignored -> new HashMap<>())
        .computeIfAbsent(fingerprint(body), ignored -> new ArrayList<>())
        .add(eventOrdinal);
  }

  boolean contains(int segment, String body, IntFunction<String> replay) {
    if (body.isBlank()) return false;
    for (int event :
        candidates.getOrDefault(segment, Map.of()).getOrDefault(fingerprint(body), List.of())) {
      if (body.equals(replay.apply(event))) return true;
    }
    return false;
  }
}

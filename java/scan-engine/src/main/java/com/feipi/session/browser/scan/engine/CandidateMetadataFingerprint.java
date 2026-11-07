package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.Candidate;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;

/** 保存候选输入摘要而非最终解析值，避免 parsed 优先字段导致反复重算。 */
final class CandidateMetadataFingerprint {
  private static final List<String> FIELDS =
      List.of("title", "model", "git_branch", "source", "cwd", "started_at", "ended_at");

  private CandidateMetadataFingerprint() {}

  static String from(Candidate candidate) {
    StringBuilder fingerprint = new StringBuilder("v1;");
    for (String field : FIELDS) append(fingerprint, field, candidate.metadata().get(field));
    append(fingerprint, "project_key", candidate.projectKey());
    return fingerprint.toString();
  }

  static boolean changed(Candidate candidate, String previous) {
    // 旧索引没有输入基线，不能用 parsed 最终值反推；logic 版本重建会补齐。
    if (previous.isEmpty()) return false;
    for (String entry : from(candidate).substring(3).split(";")) {
      if (!entry.isEmpty() && !(";" + previous).contains(";" + entry + ";")) return true;
    }
    return false;
  }

  private static void append(StringBuilder target, String key, String value) {
    if (value == null || value.isBlank()) return;
    try {
      byte[] hash =
          MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
      target.append(key).append('=').append(HexFormat.of().formatHex(hash)).append(';');
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }
}

package com.feipi.session.browser.web.api;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

/** 将分页偏移绑定到不可变发布代号与当前筛选条件，防止续页串用。 */
final class SessionContentCursor {
  private SessionContentCursor() {}

  /**
   * 编码当前请求范围的续页位置，保留下一匹配成员的精确偏移。
   *
   * @param scope 不可变内容快照及当前筛选条件
   * @param offset 下一匹配成员在当前结果集中的偏移
   * @return 绑定请求范围的不透明续页标记
   */
  static String encode(String scope, long offset) {
    if (offset < 0) {
      throw new IllegalArgumentException("cursor offset must be nonnegative");
    }
    String value = "1:" + offset + ":" + fingerprint(scope);
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.getBytes(StandardCharsets.UTF_8));
  }

  /**
   * 解码续页位置；标记损坏或跨快照、跨筛选条件复用时明确拒绝。
   *
   * @param token 绑定请求范围的不透明续页标记
   * @param scope 不可变内容快照及当前筛选条件
   * @return 匹配成员在当前结果集中的偏移
   */
  static long decode(String token, String scope) {
    try {
      String value = new String(Base64.getUrlDecoder().decode(token), StandardCharsets.UTF_8);
      String[] parts = value.split(":", -1);
      if (parts.length != 3 || !"1".equals(parts[0]) || !fingerprint(scope).equals(parts[2])) {
        throw new IllegalArgumentException(
            "cursor does not match this content snapshot and filter");
      }
      long offset = Long.parseLong(parts[1]);
      if (offset < 0) {
        throw new IllegalArgumentException("cursor offset must be nonnegative");
      }
      return offset;
    } catch (IllegalArgumentException exception) {
      throw new IllegalArgumentException("invalid content cursor", exception);
    }
  }

  private static String fingerprint(String scope) {
    try {
      byte[] hash =
          MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8));
      return Base64.getUrlEncoder().withoutPadding().encodeToString(hash);
    } catch (NoSuchAlgorithmException exception) {
      throw new IllegalStateException("SHA-256 unavailable", exception);
    }
  }
}

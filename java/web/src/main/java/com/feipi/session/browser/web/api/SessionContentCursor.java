package com.feipi.session.browser.web.api;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** 将分页偏移绑定到不可变发布代号与当前筛选条件，防止续页串用。 */
final class SessionContentCursor {
  private static final byte[] SIGNING_KEY = signingKey();

  private SessionContentCursor() {}

  /** 签发仅本服务生命周期有效的范围句柄；密钥不是内容缓存或身份 registry。 */
  static String seal(String scope, String generation, List<String> values) {
    try {
      var bytes = new java.io.ByteArrayOutputStream();
      try (var output = new java.io.DataOutputStream(bytes)) {
        output.writeUTF(fingerprint(scope));
        output.writeUTF(fingerprint(generation));
        output.writeInt(values.size());
        for (String value : values) output.writeUTF(value);
      }
      byte[] body = bytes.toByteArray();
      return Base64.getUrlEncoder().withoutPadding().encodeToString(body)
          + "."
          + Base64.getUrlEncoder().withoutPadding().encodeToString(signature(body));
    } catch (java.io.IOException exception) {
      throw new IllegalStateException("unable to encode content handle", exception);
    }
  }

  /** 验签后分别核验范围与冻结代；无签名 fingerprint 不作为授权。 */
  static List<String> open(String token, String scope, String generation) {
    try {
      if (token.length() > 8192) throw new IllegalArgumentException("oversized handle");
      String[] parts = token.split("\\.", -1);
      if (parts.length != 2) throw new IllegalArgumentException("invalid handle");
      byte[] body = Base64.getUrlDecoder().decode(parts[0]);
      if (!MessageDigest.isEqual(signature(body), Base64.getUrlDecoder().decode(parts[1])))
        throw new IllegalArgumentException("invalid signature");
      try (var input = new java.io.DataInputStream(new java.io.ByteArrayInputStream(body))) {
        if (!fingerprint(scope).equals(input.readUTF()))
          throw new IllegalArgumentException("handle scope mismatch");
        if (!fingerprint(generation).equals(input.readUTF())) throw new StaleHandleException();
        int count = input.readInt();
        if (count < 1 || count > 8) throw new IllegalArgumentException("invalid handle values");
        var result = new java.util.ArrayList<String>();
        for (int i = 0; i < count; i++) result.add(input.readUTF());
        if (input.available() != 0) throw new IllegalArgumentException("invalid handle suffix");
        return List.copyOf(result);
      }
    } catch (java.io.IOException exception) {
      throw new IllegalArgumentException("invalid content handle", exception);
    }
  }

  private static byte[] signingKey() {
    byte[] key = new byte[32];
    new SecureRandom().nextBytes(key);
    return key;
  }

  private static byte[] signature(byte[] body) {
    try {
      Mac mac = Mac.getInstance("HmacSHA256");
      mac.init(new SecretKeySpec(SIGNING_KEY, "HmacSHA256"));
      return mac.doFinal(body);
    } catch (java.security.GeneralSecurityException exception) {
      throw new IllegalStateException("HMAC unavailable", exception);
    }
  }

  /** 已签名句柄来自其它冻结代，应返回 409 而非关系为空。 */
  static final class StaleHandleException extends RuntimeException {
    private static final long serialVersionUID = 1L;
  }

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

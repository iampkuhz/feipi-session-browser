package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.util.LinkedHashSet;

/** 按调用累加用量标量；覆盖状态按观测到的代理实例合并，不按调用次数重复计数。 */
final class SessionContentUsage {
  private TokenSegments segments;

  void add(NormalizedCall call) {
    var incoming = TokenProvenance.fromMetadata(call.usageSource());
    var previous = segments;
    var precision = previous == null ? incoming : merge(previous.provenance(), incoming);
    var usage = call.usage();
    segments =
        TokenSegments.of(
            usage.fresh() + (previous == null ? 0 : previous.fresh()),
            usage.cacheRead() + (previous == null ? 0 : previous.cacheRead()),
            usage.cacheWrite() + (previous == null ? 0 : previous.cacheWrite()),
            usage.output() + (previous == null ? 0 : previous.output()),
            precision);
  }

  TokenSegments segments() {
    return segments == null ? TokenSegments.of(0, 0, 0, 0, TokenProvenance.unknown(0)) : segments;
  }

  private static TokenProvenance merge(TokenProvenance left, TokenProvenance right) {
    var methods = new LinkedHashSet<String>();
    for (String method : (left.estimationMethod() + "," + right.estimationMethod()).split(",")) {
      if (!method.isBlank()) methods.add(method);
    }
    return new TokenProvenance(
        precision(left.freshInput(), right.freshInput()),
        precision(left.cacheRead(), right.cacheRead()),
        precision(left.cacheWrite(), right.cacheWrite()),
        precision(left.output(), right.output()),
        String.join(",", methods),
        Math.max(left.estimatedSessionCount(), right.estimatedSessionCount()),
        Math.max(left.unavailableSessionCount(), right.unavailableSessionCount()),
        Math.max(left.unknownSessionCount(), right.unknownSessionCount()));
  }

  private static String precision(String left, String right) {
    return left.equals(right) ? left : "mixed";
  }
}

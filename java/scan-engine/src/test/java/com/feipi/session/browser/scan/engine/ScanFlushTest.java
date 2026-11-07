package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.api.write.IndexWriterPort;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ScanFlushTest {
  @Test
  void flushReportsProgressWithoutPublishingAndFailureRetainsSourceAndPhase() {
    for (String phase : List.of("flush", "flush_final")) {
      List<String> events = new ArrayList<>();
      List<ScanIssue> issues = new ArrayList<>();
      ScanProgress progress =
          new ScanProgress() {
            public void onPhaseStart(String name) {
              events.add("start:" + name);
            }

            public void onPhaseEnd(String name, long duration) {
              assertThat(duration).isNotNegative();
              events.add("end:" + name);
            }

            public void onSourceStart(String source, int count) {}

            public void onCandidateProcessed(String source, int count, int total) {}

            public void onSourceEnd(String source, int count) {}
          };
      assertThat(ScanFlush.flush(writer(events, false), progress, phase, "codex", issues)).isTrue();
      assertThat(events).containsExactly("start:" + phase, "flushPendingWrites", "end:" + phase);
      assertThat(issues).isEmpty();
      events.clear();
      assertThat(ScanFlush.flush(writer(events, true), progress, phase, "codex", issues)).isFalse();
      assertThat(events).containsExactly("start:" + phase, "flushPendingWrites");
      assertThat(issues).hasSize(1);
      assertThat(issues.getFirst().sourceValue()).isEqualTo("codex");
      assertThat(issues.getFirst().phase()).isEqualTo(ScanIssue.ScanPhase.INDEX_WRITE);
      assertThat(issues.getFirst().message()).isEqualTo("synthetic flush failure");
    }
  }

  private static IndexWriterPort writer(List<String> events, boolean fail) {
    return (IndexWriterPort)
        Proxy.newProxyInstance(
            IndexWriterPort.class.getClassLoader(),
            new Class<?>[] {IndexWriterPort.class},
            (proxy, method, arguments) -> {
              events.add(method.getName());
              if (fail) throw new IllegalStateException("synthetic flush failure");
              return null;
            });
  }
}

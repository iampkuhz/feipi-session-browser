package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import org.junit.jupiter.api.Test;

class ToolInputPreviewTest {
  @Test
  void previewsPathsQueriesAndCommandsFromTheFullInput() {
    assertThat(preview("Read", "{\"file_path\":\"/synthetic/a.md\"}")).isEqualTo("/synthetic/a.md");
    assertThat(preview("Grep", "{\"pattern\":\"needle\",\"path\":\"src\"}"))
        .isEqualTo("needle · src");
    assertThat(preview("Bash", "{\"command\":\"echo one\\necho two\"}"))
        .isEqualTo("echo one echo two");
    assertThat(preview("Bash", "echo " + "x".repeat(200))).hasSize(180).endsWith("…");
    assertThat(ToolInputPreview.from(null)).isEmpty();
  }

  @Test
  void classifiesOnlyTheRecordedTopLevelExecutionSurface() {
    assertThat(ToolInputPreview.executionKind("exec", "const r = await tools.exec_command(...)"))
        .isEqualTo("javascript");
    assertThat(ToolInputPreview.executionKind("functions__exec_command", "printf x"))
        .isEqualTo("shell");
    assertThat(ToolInputPreview.executionKind("Bash", "/usr/bin/python3 -c 'print(1)'"))
        .isEqualTo("python");
    assertThat(ToolInputPreview.executionKind("Read", "/synthetic/example.py")).isEqualTo("tool");
    assertThat(ToolInputPreview.executionKind("exec", "")).isEqualTo("tool");
  }

  private static String preview(String name, String input) {
    return ToolInputPreview.from(new ToolInputContents.Input("synthetic-tool", name, input));
  }
}

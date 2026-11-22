package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SessionSkillReferenceTest {
  @TempDir Path temp;

  @Test
  void matchesExactNamesAndRejectsTraversalAndAmbiguity() throws IOException {
    Path base = temp.toRealPath();
    Path first = Files.createDirectory(base.resolve("first"));
    Path second = Files.createDirectory(base.resolve("second"));
    Path definition = skill(first, "synthetic");
    assertThat(SessionSkillReference.find(List.of(first, second), "synthetic"))
        .contains(definition);
    assertThat(SessionSkillReference.find(List.of(first), "Synthetic")).isEmpty();
    assertThat(SessionSkillReference.find(List.of(first), "synthetic/SKILL.md")).isEmpty();
    assertThat(SessionSkillReference.find(List.of(first), "../synthetic")).isEmpty();
    skill(second, "synthetic");
    assertThat(SessionSkillReference.find(List.of(first, second), "synthetic")).isEmpty();
  }

  @Test
  void rejectsSymlinkedFileDirectoryAndRoot() throws IOException {
    Path base = temp.toRealPath();
    Path outside = Files.createDirectory(base.resolve("outside"));
    Path definition = skill(outside, "synthetic");
    Path root = Files.createDirectory(base.resolve("root"));
    Path linkedRoot = Files.createSymbolicLink(base.resolve("linked"), outside);
    assertThat(SessionSkillReference.find(List.of(linkedRoot), "synthetic")).isEmpty();
    Files.createSymbolicLink(root.resolve("synthetic"), definition.getParent());
    assertThat(SessionSkillReference.find(List.of(root), "synthetic")).isEmpty();
    Path fileLink = Files.createDirectory(root.resolve("file-link")).resolve("SKILL.md");
    Files.createSymbolicLink(fileLink, definition);
    assertThat(SessionSkillReference.find(List.of(root), "file-link")).isEmpty();
  }

  @Test
  void requiresLoopbackPeerAndExactBrowserOrigin() {
    assertThat(allowed("127.0.0.1", "127.0.0.1", "http://127.0.0.1:8080", "same-origin")).isTrue();
    assertThat(allowed("::1", "[::1]", "http://[::1]:8080", "same-origin")).isTrue();
    assertThat(allowed("192.0.2.1", "127.0.0.1", "http://127.0.0.1:8080", "same-origin")).isFalse();
    assertThat(allowed("127.0.0.1", "example.test", "http://example.test:8080", "same-origin"))
        .isFalse();
    assertThat(allowed("127.0.0.1", "127.0.0.1", "http://127.0.0.1:8081", "same-origin")).isFalse();
    assertThat(allowed("127.0.0.1", "127.0.0.1", null, "same-origin")).isFalse();
    assertThat(allowed("127.0.0.1", "127.0.0.1", "http://127.0.0.1:8080", "same-site")).isFalse();
  }

  @Test
  void rejectsCrossOriginAndDoesNotReturnPathsOrCacheLookupResponses() {
    var app = Javalin.create(config -> config.routes.post("/skill", SessionSkillReference::reveal));
    JavalinTest.test(
        app,
        (server, client) -> {
          String origin = "http://127.0.0.1:" + server.port();
          try (var http = HttpClient.newHttpClient()) {
            var rejected = request(http, origin, "http://example.test");
            assertThat(rejected.statusCode()).isEqualTo(403);
            assertThat(rejected.body()).isEmpty();
            var invalidName = request(http, origin, origin);
            assertThat(invalidName.statusCode()).isEqualTo(404);
            assertThat(invalidName.body()).isEmpty();
            assertThat(invalidName.headers().firstValue("Cache-Control")).contains("no-store");
          }
        });
  }

  private static HttpResponse<String> request(HttpClient http, String server, String origin)
      throws IOException, InterruptedException {
    var request =
        HttpRequest.newBuilder(URI.create(server + "/skill"))
            .header("Origin", origin)
            .header("Sec-Fetch-Site", "same-origin")
            .header("X-Feipi-Skill-Reference", "reveal")
            .POST(HttpRequest.BodyPublishers.ofString("../synthetic"))
            .build();
    return http.send(request, HttpResponse.BodyHandlers.ofString());
  }

  private static boolean allowed(String peer, String host, String origin, String site) {
    return SessionSkillReference.localRequest(peer, host, "http", 8080, origin, site, "reveal");
  }

  private static Path skill(Path root, String name) throws IOException {
    Path directory = Files.createDirectory(root.resolve(name));
    return Files.writeString(directory.resolve("SKILL.md"), "# Synthetic skill\n");
  }
}

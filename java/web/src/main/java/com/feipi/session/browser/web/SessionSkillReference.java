package com.feipi.session.browser.web;

import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/** 本机技能引用：Finder 定位，不读取、解析或返回私有 Markdown。 */
final class SessionSkillReference {
  private static final String FILE = "SKILL.md";
  private static final Pattern NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9_.-]{0,100}");
  private static final Set<String> LOCAL_HOSTS = Set.of("localhost", "127.0.0.1", "[::1]");

  private SessionSkillReference() {}

  static void reveal(Context ctx) {
    ctx.header("Cache-Control", "no-store");
    if (!localRequest(ctx)) {
      ctx.status(HttpStatus.FORBIDDEN);
      return;
    }

    Path home = Path.of(System.getProperty("user.home"), ".codex", "skills");
    List<Path> roots =
        List.of(Path.of("skills", "authoring").toAbsolutePath(), home, home.resolve(".system"));
    var file = find(roots, ctx.body());
    if (file.isEmpty()) {
      ctx.status(HttpStatus.NOT_FOUND);
      return;
    }
    try {
      new ProcessBuilder("/usr/bin/open", "-R", file.get().toString())
          .redirectOutput(ProcessBuilder.Redirect.DISCARD)
          .redirectError(ProcessBuilder.Redirect.DISCARD)
          .start();
      ctx.status(HttpStatus.ACCEPTED);
    } catch (IOException e) {
      ctx.status(HttpStatus.SERVICE_UNAVAILABLE);
    }
  }

  private static boolean localRequest(Context ctx) {
    return localRequest(
        ctx.req().getRemoteAddr(),
        ctx.req().getServerName(),
        ctx.req().getScheme(),
        ctx.req().getServerPort(),
        ctx.header("Origin"),
        ctx.header("Sec-Fetch-Site"),
        ctx.header("X-Feipi-Skill-Reference"));
  }

  static boolean localRequest(
      String peer,
      String host,
      String scheme,
      int port,
      String origin,
      String site,
      String intent) {
    if (host == null
        || !LOCAL_HOSTS.contains(host)
        || !"http".equals(scheme) && !"https".equals(scheme)
        || !"same-origin".equals(site)
        || !"reveal".equals(intent)) {
      return false;
    }
    try {
      String authority =
          port == 80 && "http".equals(scheme) || port == 443 && "https".equals(scheme)
              ? host
              : host + ":" + port;
      return (scheme + "://" + authority).equals(origin)
          && InetAddress.ofLiteral(peer).isLoopbackAddress();
    } catch (IllegalArgumentException e) {
      return false;
    }
  }

  static Optional<Path> find(List<Path> roots, String name) {
    if (name == null || !NAME.matcher(name).matches()) {
      return Optional.empty();
    }
    List<Path> files =
        roots.stream().map(root -> find(root, name)).flatMap(Optional::stream).distinct().toList();
    return files.size() == 1 ? Optional.of(files.getFirst()) : Optional.empty();
  }

  private static Optional<Path> find(Path root, String name) {
    Path file = root.resolve(name).resolve(FILE);
    for (Path part = file; part != null; part = part.getParent()) {
      if (Files.isSymbolicLink(part)) {
        return Optional.empty();
      }
    }
    try {
      if (exactChild(root, name)
          && exactChild(file.getParent(), FILE)
          && Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
        return Optional.of(file);
      }
    } catch (IOException e) {
      // 不区分没有匹配项与不可读的定义，避免泄露本机文件状态。
    }
    return Optional.empty();
  }

  private static boolean exactChild(Path directory, String name) throws IOException {
    try (var entries =
        Files.newDirectoryStream(
            directory, candidate -> candidate.getFileName().toString().equals(name))) {
      return entries.iterator().hasNext();
    }
  }
}

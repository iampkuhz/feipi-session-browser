package com.feipi.session.browser.quality.gates.rules.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Set;

/** 在同一文件系统内准备并成对发布两个 artifact。 */
final class ArtifactPairPublisher {

  private ArtifactPairPublisher() {}

  /** 完整准备并校验两个 UTF-8 artifact 后，以目录切换发布。 */
  static void publish(
      Path outputDirectory,
      String firstName,
      String firstContent,
      String secondName,
      String secondContent)
      throws IOException {
    publish(
        outputDirectory,
        firstName,
        firstContent,
        secondName,
        secondContent,
        (path, content) -> Files.write(path, content),
        ArtifactPairPublisher::moveAtomically);
  }

  /** 注入准备和移动边界，供失败恢复 contract 测试使用。 */
  static void publish(
      Path outputDirectory,
      String firstName,
      String firstContent,
      String secondName,
      String secondContent,
      StagedWriter writer,
      AtomicMover mover)
      throws IOException {
    validateFileName(firstName);
    validateFileName(secondName);
    if (firstName.equals(secondName)) {
      throw new IOException("artifact names must be distinct");
    }

    var target = outputDirectory.toAbsolutePath().normalize();
    var parent = target.getParent();
    if (parent == null) {
      throw new IOException("artifact directory has no parent: " + outputDirectory);
    }
    Files.createDirectories(parent);
    rejectUnsafeTarget(target);

    Path staging = Files.createTempDirectory(parent, "." + target.getFileName() + ".stage-");
    Path backupContainer = null;
    Path previous = null;
    var previousMoved = false;
    var rollbackFailed = false;
    try {
      writeAndVerify(staging.resolve(firstName), firstContent, writer);
      writeAndVerify(staging.resolve(secondName), secondContent, writer);
      verifyPreparedPair(staging, firstName, secondName);

      if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
        backupContainer =
            Files.createTempDirectory(parent, "." + target.getFileName() + ".backup-");
        previous = backupContainer.resolve("previous");
        mover.move(target, previous);
        previousMoved = true;
      }

      try {
        mover.move(staging, target);
        staging = null;
      } catch (IOException publishFailure) {
        if (previousMoved) {
          try {
            mover.move(previous, target);
            previousMoved = false;
          } catch (IOException rollbackFailure) {
            rollbackFailed = true;
            publishFailure.addSuppressed(rollbackFailure);
          }
        }
        throw publishFailure;
      }
    } finally {
      deleteTree(staging);
      // 回滚失败时保留 recovery 目录，避免为了清理临时文件而删除上一代有效产物。
      if (!rollbackFailed) {
        deleteTree(backupContainer);
      }
    }
  }

  private static void validateFileName(String name) throws IOException {
    var path = Path.of(name);
    if (path.isAbsolute() || path.getNameCount() != 1 || name.equals(".") || name.equals("..")) {
      throw new IOException("artifact name must be one file name: " + name);
    }
  }

  private static void rejectUnsafeTarget(Path target) throws IOException {
    if (Files.isSymbolicLink(target)) {
      throw new IOException("artifact directory must not be a symbolic link: " + target);
    }
    if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)
        && !Files.isDirectory(target, LinkOption.NOFOLLOW_LINKS)) {
      throw new IOException("artifact directory must be a directory: " + target);
    }
  }

  private static void writeAndVerify(Path path, String content, StagedWriter writer)
      throws IOException {
    var expected = content.getBytes(StandardCharsets.UTF_8);
    writer.write(path, expected);
    if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
        || Files.isSymbolicLink(path)
        || !Arrays.equals(Files.readAllBytes(path), expected)) {
      throw new IOException("artifact staging verification failed: " + path.getFileName());
    }
  }

  private static void verifyPreparedPair(Path staging, String firstName, String secondName)
      throws IOException {
    try (var entries = Files.list(staging)) {
      var names =
          entries
              .map(path -> path.getFileName().toString())
              .collect(java.util.stream.Collectors.toSet());
      if (!names.equals(Set.of(firstName, secondName))) {
        throw new IOException("artifact staging directory must contain exactly one pair");
      }
    }
  }

  private static void moveAtomically(Path source, Path target) throws IOException {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
  }

  private static void deleteTree(Path root) throws IOException {
    if (root == null || !Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
      return;
    }
    try (var paths = Files.walk(root)) {
      for (var path : paths.sorted(Comparator.reverseOrder()).toList()) {
        Files.deleteIfExists(path);
      }
    }
  }

  /** 写入 staging 文件的可注入边界。 */
  @FunctionalInterface
  interface StagedWriter {
    void write(Path path, byte[] content) throws IOException;
  }

  /** 同一文件系统内的原子目录移动边界。 */
  @FunctionalInterface
  interface AtomicMover {
    void move(Path source, Path target) throws IOException;
  }
}

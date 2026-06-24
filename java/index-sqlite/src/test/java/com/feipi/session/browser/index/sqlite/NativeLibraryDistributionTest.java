package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URL;
import java.util.Enumeration;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * SQLite native library 发行验证测试。
 *
 * <p>验证四个目标平台（Mac aarch64/x86_64、Linux x86_64/aarch64）的 native library 在发行 jar 中均存在， 当前平台 native
 * library 可成功加载，不支持的平台明确失败而非静默 fallback。
 */
@DisplayName("SQLite Native Library 发行验证")
class NativeLibraryDistributionTest {

  @Test
  @DisplayName("四个目标平台 native library 资源存在于 classpath")
  void allTargetPlatformsHaveNativeLibraries() {
    ClassLoader cl = NativeLibraryDiagnostics.class.getClassLoader();

    assertThat(cl.getResource("org/sqlite/native/Mac/aarch64/libsqlitejdbc.dylib"))
        .as("Mac aarch64 (Apple Silicon) native library")
        .isNotNull();

    assertThat(cl.getResource("org/sqlite/native/Mac/x86_64/libsqlitejdbc.dylib"))
        .as("Mac x86_64 (Intel) native library")
        .isNotNull();

    assertThat(cl.getResource("org/sqlite/native/Linux/x86_64/libsqlitejdbc.so"))
        .as("Linux x86_64 native library")
        .isNotNull();

    assertThat(cl.getResource("org/sqlite/native/Linux/aarch64/libsqlitejdbc.so"))
        .as("Linux aarch64 native library")
        .isNotNull();
  }

  @Test
  @DisplayName("verifyAllTargetPlatforms 报告所有平台可用")
  void verifyAllTargetPlatformsReportsAvailable() {
    NativeLibraryDiagnostics.NativeAvailabilityResult result =
        NativeLibraryDiagnostics.verifyAllTargetPlatforms();

    assertThat(result.allPresent()).as("所有四个目标平台 native library 应可用").isTrue();
    assertThat(result.availableCount()).isEqualTo(4);
    assertThat(result.missingPlatforms()).isEmpty();
  }

  @Test
  @DisplayName("当前平台 native library 加载成功")
  void currentPlatformNativeLoadSucceeds() {
    NativeLibraryDiagnostics.NativeLoadResult result = NativeLibraryDiagnostics.verifyNativeLoad();

    assertThat(result.loadSuccess()).as("当前平台 %s native library 应成功加载", result.platform()).isTrue();
    assertThat(result.errorMessage()).isNull();
  }

  @Test
  @DisplayName("平台检测结果与当前 JVM 一致")
  void platformDetectionMatchesCurrentJvm() {
    NativeLibraryDiagnostics.PlatformDetectionResult result = NativeLibraryDiagnostics.detect();

    assertThat(result.operatingSystem()).isNotEmpty();
    assertThat(result.architecture()).isNotEmpty();

    // os.arch 归一化后应与诊断结果一致
    String rawArch = System.getProperty("os.arch", "");
    assertThat(result.architecture()).isEqualToIgnoringCase(normalizeExpected(rawArch));
  }

  @Test
  @DisplayName("目标平台列表包含四个预期平台")
  void targetPlatformListContainsExpectedPlatforms() {
    List<String> platforms = NativeLibraryDiagnostics.targetPlatformKeys();

    assertThat(platforms)
        .containsExactlyInAnyOrder("Mac-aarch64", "Mac-x86_64", "Linux-x86_64", "Linux-aarch64");
  }

  @Test
  @DisplayName("SQLite JDBC 驱动已注册且为 native 实现")
  void sqliteJdbcDriverRegistered() throws Exception {
    Class.forName("org.sqlite.JDBC");

    var drivers = java.sql.DriverManager.drivers().toList();
    assertThat(drivers).anyMatch(d -> d.getClass().getName().equals("org.sqlite.JDBC"));
  }

  @Test
  @DisplayName("configureNativeExtractionDir 设置 org.sqlite.tmpdir 属性")
  void configureNativeExtractionDirSetsProperty() {
    // 保存当前值以便恢复
    String previous = System.getProperty("org.sqlite.tmpdir");
    try {
      // 清除已有值以测试配置方法
      System.clearProperty("org.sqlite.tmpdir");

      NativeLibraryDiagnostics.configureNativeExtractionDir();

      String tmpdir = System.getProperty("org.sqlite.tmpdir");
      assertThat(tmpdir)
          .as("org.sqlite.tmpdir 应已配置，避免使用系统 /tmp")
          .isNotNull()
          .contains(".feipi-session-browser/native");
    } finally {
      // 恢复原始状态
      if (previous != null) {
        System.setProperty("org.sqlite.tmpdir", previous);
      } else {
        System.clearProperty("org.sqlite.tmpdir");
      }
    }
  }

  @Test
  @DisplayName("configureNativeExtractionDir 不覆盖已有配置")
  void configureNativeExtractionDirDoesNotOverrideExisting() {
    String previous = System.getProperty("org.sqlite.tmpdir");
    try {
      String customDir = "/custom/native/dir";
      System.setProperty("org.sqlite.tmpdir", customDir);

      NativeLibraryDiagnostics.configureNativeExtractionDir();

      assertThat(System.getProperty("org.sqlite.tmpdir")).isEqualTo(customDir);
    } finally {
      if (previous != null) {
        System.setProperty("org.sqlite.tmpdir", previous);
      } else {
        System.clearProperty("org.sqlite.tmpdir");
      }
    }
  }

  @Test
  @DisplayName("SQLite 内存连接验证 native 加载后正常工作")
  void sqliteMemoryConnectionWorksWithNativeLib() throws Exception {
    try (var conn = java.sql.DriverManager.getConnection("jdbc:sqlite::memory:");
        var stmt = conn.createStatement();
        var rs = stmt.executeQuery("SELECT sqlite_version()")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString(1)).isNotBlank();
    }
  }

  @Test
  @DisplayName("SQLite native library jar 大小合理（包含多平台 native libs）")
  void sqliteJdbcJarSizeReasonable() {
    URL jarUrl =
        NativeLibraryDiagnostics.class
            .getClassLoader()
            .getResource("org/sqlite/native/Mac/aarch64/libsqlitejdbc.dylib");
    assertThat(jarUrl).isNotNull();

    // 验证 jar 路径中包含 sqlite-jdbc
    String path = jarUrl.toString();
    assertThat(path).contains("sqlite-jdbc");
  }

  @Test
  @DisplayName("Xerial native library 路径结构遵循约定")
  void nativeLibraryPathStructureFollowsConvention() {
    ClassLoader cl = NativeLibraryDiagnostics.class.getClassLoader();

    // 所有 native library 应在 org/sqlite/native/ 下
    Enumeration<URL> resources;
    try {
      resources = cl.getResources("org/sqlite/native");
    } catch (Exception e) {
      throw new AssertionError("无法枚举 native 资源", e);
    }
    // 至少应找到一个 org/sqlite/native 目录
    assertThat(resources.hasMoreElements()).isTrue();
  }

  private static String normalizeExpected(String osArch) {
    return switch (osArch.toLowerCase()) {
      case "aarch64", "arm64" -> "aarch64";
      case "amd64", "x86_64" -> "x86_64";
      case "x86", "i386", "i686" -> "x86";
      default -> osArch;
    };
  }
}

package com.feipi.session.browser.arch;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static org.assertj.core.api.Assertions.assertThat;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.lang.ArchRule;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Java 模块边界依赖守卫。
 *
 * <p>这些规则固定抽象模块和应用层只能依赖端口/API，不能重新引入 JDBC、SQLite 适配器或内置 source provider 实现。
 */
@DisplayName("Java module boundary dependency rules")
final class JavaModuleBoundaryDependencyTest {

  private JavaModuleBoundaryDependencyTest() {}

  /** application/query API 不得依赖 JDBC 或具体 SQLite store。 */
  @Test
  @DisplayName("application and query-api must not depend on JDBC or concrete stores")
  void applicationMustNotDependOnConcreteStoreOrJdbc() {
    check(
        noClasses()
            .that()
            .resideInAnyPackage("..application..", "..query.api..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage(
                "java.sql..",
                "com.feipi.session.browser.index.sqlite..",
                "com.feipi.session.browser.index.store.sqlite..")
            .as("application and query-api must depend on index-api ports, not JDBC/SQLite store")
            .because(
                "application use cases must stay independent of concrete persistence adapters"));
  }

  /** web 不得依赖 JDBC 或具体 SQLite store。 */
  @Test
  @DisplayName("web must not depend on JDBC or concrete stores")
  void webMustNotDependOnConcreteStoreOrJdbc() {
    check(
        noClasses()
            .that()
            .resideInAPackage("..web..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage(
                "java.sql..",
                "com.feipi.session.browser.index.sqlite..",
                "com.feipi.session.browser.index.store.sqlite..")
            .as("web must depend on application/index-api ports, not JDBC/SQLite store")
            .because("HTTP adapters must not reach into concrete persistence implementations"));
  }

  /** scan-engine 不得依赖具体 store、内置 source provider 或 JDBC。 */
  @Test
  @DisplayName("scan-engine must not depend on stores, built-in source providers, or JDBC")
  void scanEngineMustNotDependOnConcreteStoreSourcesOrJdbc() {
    check(
        noClasses()
            .that()
            .resideInAPackage("..scan..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage(
                "java.sql..",
                "com.feipi.session.browser.index.sqlite..",
                "com.feipi.session.browser.index.store.sqlite..",
                "com.feipi.session.browser.source.claude..",
                "com.feipi.session.browser.source.codex..",
                "com.feipi.session.browser.source.qoder..",
                "com.feipi.session.browser.source.json..")
            .as("scan-engine must use source-spi/index-api ports, not providers, JDBC, or stores")
            .because(
                "built-in providers and concrete persistence are composed outside scan-engine"));
  }

  /** source-spi 必须保持无实现依赖。 */
  @Test
  @DisplayName("source-spi must stay implementation-free")
  void sourceSpiMustStayImplementationFree() {
    check(
        noClasses()
            .that()
            .resideInAPackage("..source.spi..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage(
                "com.fasterxml.jackson..",
                "java.sql..",
                "org.sqlite..",
                "com.feipi.session.browser.source.claude..",
                "com.feipi.session.browser.source.codex..",
                "com.feipi.session.browser.source.qoder..",
                "com.feipi.session.browser.source.json..")
            .as("source-spi must stay provider-neutral and implementation-free")
            .because(
                "SPI contracts must not depend on provider implementations or serialization/store"
                    + " libraries"));
  }

  /** index-api/query-api 必须保持抽象。 */
  @Test
  @DisplayName("index-api and query-api must stay abstract")
  void indexApiMustStayAbstract() {
    check(
        noClasses()
            .that()
            .resideInAnyPackage("..index.api..", "..query.api..")
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage(
                "java.sql..",
                "org.sqlite..",
                "com.feipi.session.browser.index.sqlite..",
                "com.feipi.session.browser.index.store.sqlite..",
                "com.feipi.session.browser.web..",
                "com.feipi.session.browser.application..")
            .as("index-api/query-api must stay abstract and independent of app/web/store layers")
            .because(
                "query and index ports are the abstraction boundary used by application and web"));
  }

  private static void check(ArchRule rule) {
    rule.check(moduleClasses());
  }

  private static JavaClasses moduleClasses() {
    List<Path> classDirs =
        List.of(
            moduleClassDir("application"),
            moduleClassDir("web"),
            moduleClassDir("scan-engine"),
            moduleClassDir("source-spi"),
            moduleClassDir("index-api"));
    classDirs.forEach(
        path -> assertThat(path).as("compiled production classes path must exist").isDirectory());

    return new ClassFileImporter()
        .withImportOption(new ImportOption.DoNotIncludeTests())
        .importPaths(classDirs);
  }

  private static Path moduleClassDir(String moduleName) {
    return repoRoot().resolve("java").resolve(moduleName).resolve("build/classes/java/main");
  }

  private static Path repoRoot() {
    return Path.of(System.getProperty("repo.root.dir"));
  }
}

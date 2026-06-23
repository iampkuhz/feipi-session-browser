package com.feipi.session.browser.reuse.analyzer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import spoon.Launcher;
import spoon.reflect.declaration.CtType;
import spoon.support.compiler.VirtualFile;

/** PeerGroupResolver 测试。 验证 peer group 基于共享的 interface/abstract base， 而非类名后缀。 */
class PeerGroupResolverTest {

  @Test
  void resolvePeerGroupSharedInterfaceGroupsTypesTogether() {
    String source =
        """
                package test;
                interface MyService {
                    void execute();
                }
                class ServiceA implements MyService {
                    public void execute() {}
                }
                class ServiceB implements MyService {
                    public void execute() {}
                }
                """;
    List<CtType<?>> types = buildTypes(source);

    Map<String, List<String>> groups = PeerGroupResolver.buildPeerGroups(types);
    // ServiceA 和 ServiceB 实现 MyService → 应在同一 peer group
    assertThat(groups).isNotEmpty();
    boolean foundGroup =
        groups.values().stream()
            .anyMatch(group -> group.containsAll(List.of("test.ServiceA", "test.ServiceB")));
    assertThat(foundGroup).isTrue();
  }

  @Test
  void resolvePeerGroupNoSharedInterfaceNoGroup() {
    String source =
        """
                package test;
                class StandaloneA {
                    public void doA() {}
                }
                class StandaloneB {
                    public void doB() {}
                }
                """;
    List<CtType<?>> types = buildTypes(source);

    Map<String, List<String>> groups = PeerGroupResolver.buildPeerGroups(types);
    // 无共享 interface → 无 peer group
    assertThat(groups).isEmpty();
  }

  @Test
  void resolvePeerGroupNotBasedOnNameSuffix() {
    // 两个类名以 "Adapter" 结尾，但不实现相同 interface
    String source =
        """
                package test;
                class FooAdapter {
                    public void adapt() {}
                }
                class BarAdapter {
                    public void adapt() {}
                }
                """;
    List<CtType<?>> types = buildTypes(source);

    Map<String, List<String>> groups = PeerGroupResolver.buildPeerGroups(types);
    // 仅凭名称后缀不构成 peer group
    assertThat(groups).isEmpty();
  }

  @Test
  void resolvePeerGroupJdkInterfaceNotCounted() {
    // 实现 java.io.Serializable（JDK interface）不应形成 peer group
    String source =
        """
                package test;
                import java.io.Serializable;
                class Alpha implements Serializable {
                    private static final long serialVersionUID = 1L;
                }
                class Beta implements Serializable {
                    private static final long serialVersionUID = 1L;
                }
                """;
    List<CtType<?>> types = buildTypes(source);

    Map<String, List<String>> groups = PeerGroupResolver.buildPeerGroups(types);
    // JDK interface 不计入 peer group
    assertThat(groups).isEmpty();
  }

  @Test
  void resolvePeerGroupSharedAbstractBase() {
    String source =
        """
                package test;
                abstract class BaseProcessor {
                    abstract void process();
                }
                class ProcessorA extends BaseProcessor {
                    void process() {}
                }
                class ProcessorB extends BaseProcessor {
                    void process() {}
                }
                """;
    List<CtType<?>> types = buildTypes(source);

    Map<String, List<String>> groups = PeerGroupResolver.buildPeerGroups(types);
    // ProcessorA 和 ProcessorB 继承相同 abstract base → peer group
    assertThat(groups).isNotEmpty();
    boolean foundGroup =
        groups.values().stream()
            .anyMatch(g -> g.containsAll(List.of("test.ProcessorA", "test.ProcessorB")));
    assertThat(foundGroup).isTrue();
  }

  private List<CtType<?>> buildTypes(String source) {
    Launcher launcher = new Launcher();
    launcher.getEnvironment().setComplianceLevel(21);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.getEnvironment().setShouldCompile(false);
    launcher.addInputResource(new VirtualFile(source, "Test.java"));
    launcher.buildModel();
    return launcher.getModel().getAllTypes().stream().toList();
  }
}

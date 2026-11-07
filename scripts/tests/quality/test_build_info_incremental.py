"""构建时间不作为易变默认输入，显式元数据与真实版本身份仍参与失效。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_build_metadata_does_not_put_the_clock_in_gradle_inputs() -> None:
    build = (ROOT / 'java/app-cli/build.gradle.kts').read_text()
    task = build.split('val generateBuildInfo = tasks.register("generateBuildInfo") {', 1)[1]
    task = task.split('\nsourceSets.main.configure', 1)[0]
    before_action, action = task.split('doLast {', 1)
    assert 'Instant.now()' not in before_action
    assert 'explicitBuildTimestamp ?: Instant.now().toString()' in action
    assert 'inputs.property("buildTimestamp", buildTimestampProvider).optional(true)' in task
    assert 'inputs.property("gitCommit", gitCommitProvider)' in task
    assert 'inputs.file(versionFile)' in task
    assert 'providers.environmentVariable("BUILD_TIMESTAMP")' in task
    assert 'providers.environmentVariable("BUILD_GIT_COMMIT")' in task
    assert 'propsDir.resolve("build-info.properties").writeText(' in action

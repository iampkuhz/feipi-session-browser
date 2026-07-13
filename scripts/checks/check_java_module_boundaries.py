"""负责对误用的旧 Python 边界入口快速失败；不负责检查 Java 模块；由旧路径调用时触发。"""

raise SystemExit('请运行 Gradle check；JavaModuleBoundaryDependencyTest 是唯一实现。')

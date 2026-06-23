# SI-070: 删除、重命名、孤儿与 Repair 状态机

## 状态
IMPLEMENTED

## 目标
迁移 source 删除、路径移动、session key 变化、artifact/DB 孤儿修复，所有动作幂等。

## 设计决策

### 1. 五种 repair 动作

- `CONFIRMED_DELETE`: 源文件确认不存在，安全删除 DB row 和相关 artifact
- `ROOT_UNAVAILABLE`: 根目录不可访问，保留 DB row 不做删除
- `SOURCE_MISSING_TEMPORARY`: 源文件暂时缺失，暂不删除
- `RENAME_DETECTED`: 检测到重命名/移动，更新路径
- `NO_ACTION`: 源文件存在且路径未变化

### 2. 删除顺序
先 `session_artifacts` 行，后 `sessions` 行，保证外键约束一致性。

### 3. 重命名检测策略
从 session key 提取 session_id，在源根目录下递归搜索文件名包含该 session_id 的文件。

### 4. 孤儿 artifact 检测
扫描 artifact 目录下所有 `*.json` 文件（排除 meta 和临时文件），检查是否有对应 DB row。

### 5. 校验放置
- 根目录安全检查在 `SourceAdapter.checkRoot` 边界执行一次
- 文件存在性检查只在 `RenameDetector` 执行
- 不在下游重复检查

## 实际修改文件

- `java/scan-engine/src/main/java/.../scan/engine/RepairAction.java` (新建)
- `java/scan-engine/src/main/java/.../scan/engine/RepairDecision.java` (新建)
- `java/scan-engine/src/main/java/.../scan/engine/RepairSummary.java` (新建)
- `java/scan-engine/src/main/java/.../scan/engine/RepairEngine.java` (新建)
- `java/scan-engine/src/main/java/.../scan/engine/SessionDeleter.java` (新建)
- `java/scan-engine/src/main/java/.../scan/engine/RenameDetector.java` (新建)
- `java/scan-engine/src/test/java/.../scan/engine/RepairEngineTest.java` (新建)
- `java/scan-engine/src/test/java/.../scan/engine/SessionDeleterTest.java` (新建)
- `java/scan-engine/src/test/java/.../scan/engine/RenameDetectorTest.java` (新建)

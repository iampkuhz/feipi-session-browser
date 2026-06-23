# SI-070 Proposal: 删除、重命名、孤儿与 Repair 状态机

## 变更概述
在 Java scan-engine 模块中实现 session 删除、重命名检测、孤儿清理和 repair 操作。

## 动机
Python 版增量扫描包含对源删除、路径移动和孤儿 artifact 的处理逻辑。Java 迁移需要在 scan-engine 中提供等价的 repair 状态机，确保增量扫描后数据库和 artifact 目录的一致性。

## 核心能力

### 1. 源删除检测
- 区分 root unavailable（暂不删除）和 confirmed delete（安全删除）
- 临时权限问题不触发批量删除

### 2. 重命名检测
- 从 session key 提取 session_id
- 在源根目录下搜索包含相同 session_id 的文件
- 更新 DB 中的 file_path

### 3. 孤儿 artifact 清理
- 扫描 artifact 目录，找出无对应 DB row 的文件
- 安全删除孤儿 artifact 文件

### 4. 幂等性保证
- 重复 repair 产生相同结果
- 单行失败不中断批量操作
- 所有 destructive action 有审计摘要

## 影响范围
- 新增 scan-engine 内部类（package-private）
- 不修改现有 scan 流程
- 不修改 public API

## 风险
- 重命名检测可能匹配错误的文件（session_id 碰撞）
- 孤儿 artifact 清理依赖 safe name 反向映射

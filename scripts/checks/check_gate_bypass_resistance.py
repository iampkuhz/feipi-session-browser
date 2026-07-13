"""负责对误用的旧 leaf 入口快速失败；不负责实现 Gate 绕过检查；由旧路径调用时触发。"""

raise SystemExit("请使用共享 check CLI: repository.gate-bypass")

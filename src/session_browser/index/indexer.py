"""SQLite 索引公共 API（只读路径）。

本模块暴露查询和连接 API。实现分布在：
- schema.py: 连接配置、schema 辅助
- queries.py: 会话、项目、仪表板查询
- writers.py: 行到领域对象的转换（只读）

Python scan 写路径已退休，由 Java scan 接管。
"""

from __future__ import annotations

# 说明：--- 查询 -------------------------------------------------------------------
from session_browser.index.queries import (
    count_projects,
    count_sessions,
    get_dashboard_stats,
    get_project_stats,
    get_prompt_activity_trend,
    get_session,
    get_sessions_list_aggregate,
    get_trend_data,
    list_agents,
    list_projects,
    list_sessions,
)

# 说明：--- Schema 与连接 ---------------------------------------------------------
from session_browser.index.schema import (
    _get_connection,
)

# 说明：--- 行转换（只读） ---------------------------------------------------------
from session_browser.index.writers import (
    _row_to_summary,
)

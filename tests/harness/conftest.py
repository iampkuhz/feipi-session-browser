# harness 测试的 pytest fixtures — 继承根 conftest.py

import pytest


@pytest.fixture(autouse=True)
def _isolate_feipi_env(monkeypatch):
    """清除质量门运行环境继承的 FEIPI_* 变量，防止测试间状态泄漏。"""
    for var in ('FEIPI_SESSION_ID', 'FEIPI_AGENT_CLIENT', 'FEIPI_AGENT_ID'):
        monkeypatch.delenv(var, raising=False)

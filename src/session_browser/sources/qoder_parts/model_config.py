"""Qoder session 的模型配置解析逻辑。

Loads custom model names, selector labels, auth model names, and resolves
model config IDs to human-readable labels from Qoder's Electron/VSCode-style
application support directory.
"""

from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
import os

from session_browser.config import QODER_DATA_DIR


def _qoder_app_support_dir() -> Path:
    """返回 Qoder's Electron/VSCode-style application support directory."""
    return Path(os.environ.get(
        "QODER_APP_SUPPORT_DIR",
        str(Path.home() / "Library" / "Application Support" / "Qoder"),
    ))


@lru_cache(maxsize=4)
def _load_qoder_custom_model_names(app_support_dir: Path | None = None) -> dict[str, str]:
    """加载 custom model id -> display name，来源于 Qoder global state.

    Qoder stores BYOK API keys separately under secret:// keys in the same DB.
    This function only reads the non-secret aicoding.customModels value.
    """
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    db_path = app_support_dir / "User" / "globalStorage" / "state.vscdb"
    if not db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("aicoding.customModels",),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return {}

    if not row or not row[0]:
        return {}

    try:
        models = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return {}

    result: dict[str, str] = {}
    if not isinstance(models, list):
        return result

    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "")
        if not model_id:
            continue
        name = str(item.get("alias") or item.get("model") or model_id)
        result[model_id] = name
        result[f"custom:{model_id}"] = name
    return result


@lru_cache(maxsize=4)
def _load_qoder_model_selector_names(app_support_dir: Path | None = None) -> dict[str, str]:
    """加载 built-in Qoder model selector labels such as qmodel -> Qwen3.6-Plus."""
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    cache_path = app_support_dir / "User" / "dynamic-text-cache.json"
    if not cache_path.exists():
        return {}

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    labels: dict[str, str] = {}

    def walk(value) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    isinstance(key, str)
                    and key.startswith("modelSelector.item.")
                    and "." not in key.removeprefix("modelSelector.item.")
                    and isinstance(item, str)
                ):
                    labels[key.removeprefix("modelSelector.item.")] = item
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return labels


@lru_cache(maxsize=1)
def _load_qoder_auth_model_names() -> dict[str, str]:
    """加载 model key -> display name，来源于 Qoder's model cache file."""
    cache_path = QODER_DATA_DIR / ".auth" / "models"
    if not cache_path.exists():
        return {}

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    labels: dict[str, str] = {}
    if not isinstance(data, dict):
        return labels

    for models in data.values():
        if not isinstance(models, list):
            continue
        for item in models:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            display_name = str(item.get("display_name") or "")
            if key and display_name:
                labels[key] = display_name
    return labels


def _resolve_qoder_model_config_name(
    model_config: str,
    custom_names: dict[str, str] | None = None,
    selector_names: dict[str, str] | None = None,
    auth_names: dict[str, str] | None = None,
) -> str:
    """Resolve 一个 Qoder model config id to 一个 human-readable model label."""
    model_config = (model_config or "").strip()
    if not model_config:
        return ""

    if custom_names is None:
        custom_names = _load_qoder_custom_model_names()
    if selector_names is None:
        selector_names = _load_qoder_model_selector_names()
    if auth_names is None:
        auth_names = _load_qoder_auth_model_names()

    if model_config in custom_names:
        return custom_names[model_config]

    if model_config.startswith("custom:"):
        custom_id = model_config.split(":", 1)[1]
        return custom_names.get(custom_id, model_config)

    if model_config in selector_names:
        return selector_names[model_config]
    if model_config in auth_names:
        return auth_names[model_config]

    # Qoder has scoped ids such as quest-auto 和 experts-ultimate.
    if "-" in model_config:
        suffix = model_config.rsplit("-", 1)[1]
        if suffix in selector_names:
            return selector_names[suffix]
        if suffix in auth_names:
            return auth_names[suffix]

    return model_config


@lru_cache(maxsize=4)
def _load_qoder_current_assistant_model(app_support_dir: Path | None = None) -> str:
    """加载 Qoder's current assistant model selector，来源于 global state.

    Some Qoder project sessions are created by the client without writing a
    per-session model into JSONL or agent.log. The selector state records the
    currently chosen assistant model without exposing BYOK secret values.
    """
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    db_path = app_support_dir / "User" / "globalStorage" / "state.vscdb"
    if not db_path.exists():
        return ""

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key = ?",
            ("chat.modelConfig.assistant",),
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return ""

    if not row or not row[0]:
        return ""

    return _resolve_qoder_model_config_name(
        str(row[0]),
        custom_names=_load_qoder_custom_model_names(app_support_dir),
        selector_names=_load_qoder_model_selector_names(app_support_dir),
        auth_names=_load_qoder_auth_model_names(),
    )


@lru_cache(maxsize=4)
def _build_qoder_session_model_map(app_support_dir: Path | None = None) -> dict[str, str]:
    """构建 session_id -> model label，来源于 Qoder GUI agent logs."""
    app_support_dir = app_support_dir or _qoder_app_support_dir()
    logs_dir = app_support_dir / "logs"
    if not logs_dir.exists():
        return {}

    custom_names = _load_qoder_custom_model_names(app_support_dir)
    selector_names = _load_qoder_model_selector_names(app_support_dir)
    auth_names = _load_qoder_auth_model_names()

    session_models: dict[str, str] = {}
    patterns = [
        re.compile(r"activeModelConfig=(?P<model>[^,\s]+).*sessionId=(?P<sid>[^,\s]+)"),
        re.compile(
            r"getCurrentModelConfig: sessionId=(?P<sid>[^,\s]+), "
            r"returning (?:from \w+: )?(?P<model>[^,\s]+)"
        ),
    ]

    for log_path in logs_dir.glob("**/agent.log"):
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            if "ModelConfigService" not in line and "ModelSelector" not in line:
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                session_id = match.group("sid").strip()
                model_config = match.group("model").strip()
                if not session_id or session_id == "none":
                    continue
                model = _resolve_qoder_model_config_name(
                    model_config,
                    custom_names=custom_names,
                    selector_names=selector_names,
                    auth_names=auth_names,
                )
                if model:
                    session_models[session_id] = model
                    if session_id.startswith("blank_session_"):
                        session_models[session_id.removeprefix("blank_session_")] = model
                break

    prefix_models: dict[str, set[str]] = {}
    uuid_pattern = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    for session_id, model in session_models.items():
        if uuid_pattern.match(session_id):
            prefix_models.setdefault(session_id[:8].lower(), set()).add(model)
    for prefix, models in prefix_models.items():
        if prefix not in session_models and len(models) == 1:
            session_models[prefix] = next(iter(models))

    return session_models


def _infer_qoder_model_for_session(session_id: str) -> str:
    """推断 一个 Qoder model，来源于 persisted GUI logs/config，用于 一个 session."""
    if not session_id:
        return ""
    app_support_dir = _qoder_app_support_dir()
    session_model = _build_qoder_session_model_map(app_support_dir).get(session_id, "")
    if session_model:
        return session_model
    if not re.match(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        session_id,
    ):
        return ""
    return _load_qoder_current_assistant_model(app_support_dir)

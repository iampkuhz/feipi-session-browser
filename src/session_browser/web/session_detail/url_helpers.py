"""URL builder helpers for /sessions query state.

Extracted from routes.py. Preserves query params across filter/sort/page
changes to build consistent pagination and filter URLs.
"""

from __future__ import annotations

import urllib.parse

_SESSIONS_URL_PARAM_ORDER = [
    "q", "agent", "model", "project",
    "sort", "dir", "page", "page_size",
]


def build_sessions_url(
    *,
    current: dict[str, str] | None = None,
    updates: dict[str, str | None] | None = None,
    reset_page: bool = False,
) -> str:
    """Build a /sessions URL preserving query state.

    Args:
        current: Existing query params (e.g. from template context).
        updates: Keys to add/override. Value ``None`` removes the key.
        reset_page: When filters/sort change, reset page to 1.
    """
    current = current or {}
    updates = updates or {}

    merged = dict(current)

    # Apply updates (None means delete)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = str(value)

    if reset_page:
        merged.pop("page", None)

    # Filter out empty values
    params = [(k, v) for k, v in merged.items() if v and v.strip()]

    # Stable ordering
    ordered = []
    for key in _SESSIONS_URL_PARAM_ORDER:
        if key in {k for k, _ in params}:
            ordered.append((key, merged[key]))
    # Append any keys not in the standard order
    seen = {k for k, _ in ordered}
    for k, v in params:
        if k not in seen:
            ordered.append((k, v))

    qs = urllib.parse.urlencode(ordered)
    return "/sessions" + ("?" + qs if qs else "")


def _build_view_actions(
    filters: dict[str, str],
    sort_key: str,
    sort_dir: str,
    page: int,
    page_size: int | str,
    has_prev: bool,
    has_next: bool,
) -> dict:
    """Build action URLs for template rendering."""
    current = {k: v for k, v in filters.items() if v}
    if sort_key:
        current["sort"] = sort_key
    if sort_dir:
        current["dir"] = sort_dir
    if page > 1:
        current["page"] = str(page)
    if page_size and page_size != 20:
        current["page_size"] = str(page_size)

    # Sort URLs: toggle dir on active column, set new column otherwise
    sort_keys = ["tokens", "rounds", "tools", "subagents", "duration", "updated"]
    sort_urls = {}
    for sk in sort_keys:
        new_dir = "asc" if (sk == sort_key and sort_dir == "asc") else "desc"
        sort_urls[sk] = build_sessions_url(
            current=current,
            updates={"sort": sk, "dir": new_dir},
            reset_page=True,
        )

    # Pagination URLs
    prev_url = ""
    next_url = ""
    if has_prev:
        prev_url = build_sessions_url(
            current=current,
            updates={"page": str(page - 1)},
        )
    if has_next:
        next_url = build_sessions_url(
            current=current,
            updates={"page": str(page + 1)},
        )

    # Page size URLs
    page_size_urls = {}
    for ps in ("20", "50", "100", "500", "all"):
        page_size_urls[ps] = build_sessions_url(
            current=current,
            updates={"page_size": ps},
            reset_page=True,
        )

    # Filter chip removal URLs
    remove_urls = {}
    for fk in ("q", "agent", "model", "project"):
        if filters.get(fk):
            remove_urls[fk] = build_sessions_url(
                current=current,
                updates={fk: None},
                reset_page=True,
            )

    # Clear All: remove all filters, keep sort
    clear_all_url = build_sessions_url(
        current={},
        updates={"sort": sort_key} if sort_key else None,
    )

    # Clear Session ID only
    clear_session_id_url = build_sessions_url(
        current=current,
        updates={"q": None},
        reset_page=True,
    )

    return {
        "clear_session_id_url": clear_session_id_url,
        "clear_all_url": clear_all_url,
        "sort_urls": sort_urls,
        "remove_filter_urls": remove_urls,
        "prev_url": prev_url,
        "next_url": next_url,
        "page_size_urls": page_size_urls,
    }

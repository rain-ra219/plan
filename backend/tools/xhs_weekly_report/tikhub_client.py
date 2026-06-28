from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_SEARCH_PATH = "/api/v1/xiaohongshu/app_v2/search_notes"
DEFAULT_COMMENTS_PATH = "/api/v1/xiaohongshu/app_v2/get_note_comments"
DEFAULT_COMMENT_CURSOR = ""
DEFAULT_COMMENT_INDEX = "0"
DEFAULT_COMMENT_PAGE_AREA = "UNFOLDED"
DEFAULT_COMMENT_SORT_STRATEGY = "like_count"
DEFAULT_USER_AGENT = "axios/1.7.9"


def tikhub_get(config: dict[str, str], path: str, query: dict[str, str]) -> dict[str, Any]:
    base_url = (config.get("tikhubBaseUrl") or "https://api.tikhub.io").rstrip("/")
    path = config_path({"path": path}, "path", DEFAULT_COMMENTS_PATH)
    url = build_url(base_url, path, query)
    request = urllib.request.Request(url, headers=tikhub_headers(config))
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TikHub HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TikHub network error: {exc.reason}") from exc


def tikhub_headers(config: dict[str, str]) -> dict[str, str]:
    token = normalize_bearer_token(config.get("tikhubToken", ""))
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": str(config.get("userAgent") or DEFAULT_USER_AGENT),
    }


def normalize_bearer_token(value: str) -> str:
    token = str(value or "").strip()
    if token.lower().startswith("bearer "):
        return token[7:].strip()
    return token


def search_response_items(result: dict[str, Any]) -> list[Any]:
    candidates = [
        get_nested(result, ("data", "data", "items")),
        get_nested(result, ("data", "items")),
        get_nested(result, ("data", "data")),
        result.get("items"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def comments_response_items(result: dict[str, Any]) -> list[Any]:
    candidates = [
        get_nested(result, ("data", "data", "comments")),
        get_nested(result, ("data", "comments")),
        get_nested(result, ("comments",)),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def get_nested(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def note_payload(note_item: dict[str, Any]) -> dict[str, Any]:
    note = note_item.get("note")
    if isinstance(note, dict):
        return note
    return note_item


def get_note_id(note_item: dict[str, Any]) -> str:
    note = note_payload(note_item)
    return str(note.get("id") or note.get("note_id") or "")


def note_comment_count(note_item: dict[str, Any]) -> int:
    note = note_payload(note_item)
    for key in ("comment_count", "comments_count", "comment_num", "comments"):
        value = note.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def comments_query_from_note_id(note_id: str, config: dict[str, str] | None = None) -> dict[str, str]:
    query = comment_query_defaults(config)
    query["note_id"] = note_id
    return query


def comments_query_from_link(link: str, config: dict[str, str] | None = None) -> dict[str, str]:
    query = comment_query_defaults(config)
    note_id = extract_note_id(link)
    if note_id:
        query["note_id"] = note_id
    else:
        query["share_text"] = str(link or "").strip()
    return query


def comment_query_defaults(config: dict[str, str] | None = None) -> dict[str, str]:
    config = config or {}
    return {
        "cursor": str(config.get("cursor") or DEFAULT_COMMENT_CURSOR),
        "index": str(config.get("index") or DEFAULT_COMMENT_INDEX),
        "pageArea": str(config.get("pageArea") or DEFAULT_COMMENT_PAGE_AREA),
        "sort_strategy": str(config.get("sort_strategy") or config.get("sortStrategy") or DEFAULT_COMMENT_SORT_STRATEGY),
    }


def config_path(config: dict[str, str], key: str, default: str) -> str:
    path = str(config.get(key) or default).strip() or default
    if path.startswith(("http://", "https://")):
        return path
    return path if path.startswith("/") else f"/{path}"


def build_url(base_url: str, path_or_url: str, query: dict[str, str]) -> str:
    endpoint = path_or_url if path_or_url.startswith(("http://", "https://")) else f"{base_url}{path_or_url}"
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{urllib.parse.urlencode(query)}"


def extract_note_id(link: str) -> str:
    clean = str(link or "").strip()
    patterns = [
        r"xiaohongshu\.com/explore/([A-Za-z0-9]+)",
        r"xiaohongshu\.com/discovery/item/([A-Za-z0-9]+)",
        r"[?&]note_id=([A-Za-z0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean)
        if match:
            return match.group(1)
    return ""


def extract_comments(raw_comments: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_comments, list):
        return []
    comments: list[dict[str, Any]] = []
    for comment in raw_comments:
        if not isinstance(comment, dict):
            continue
        add_comment(comments, comment, "主评论")
        for sub in comment.get("sub_comments") or []:
            if isinstance(sub, dict):
                add_comment(comments, sub, "回复")
    return sorted(comments, key=lambda item: int(item.get("like_count") or 0), reverse=True)


def add_comment(items: list[dict[str, Any]], item: dict[str, Any], kind: str) -> None:
    content = str(item.get("content") or "").strip()
    if not content:
        return
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    items.append(
        {
            "author": user.get("nickname") or "佚名",
            "content": content,
            "like_count": int(item.get("like_count") or 0),
            "location": item.get("ip_location") or "未知",
            "type": kind,
        }
    )

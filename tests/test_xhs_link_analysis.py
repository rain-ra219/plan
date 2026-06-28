from __future__ import annotations

from tools.feishu_intake.listener import field_text
from tools.xhs_weekly_report.tikhub_client import (
    build_url,
    comments_query_from_link,
    config_path,
    extract_note_id,
    normalize_bearer_token,
    tikhub_headers,
)


def test_extract_note_id_from_xiaohongshu_explore_url() -> None:
    link = "https://www.xiaohongshu.com/explore/6a087419000000000303c308?xsec_token=abc"
    assert extract_note_id(link) == "6a087419000000000303c308"


def test_comments_query_uses_share_text_when_note_id_is_missing() -> None:
    query = comments_query_from_link("http://xhslink.com/a/abc123")
    assert query["share_text"] == "http://xhslink.com/a/abc123"
    assert query["sort_strategy"] == "like_count"


def test_comments_query_uses_configured_tikhub_comment_params() -> None:
    query = comments_query_from_link(
        "http://xhslink.com/a/abc123",
        {
            "cursor": "next",
            "index": "2",
            "pageArea": "FOLDED",
            "sort_strategy": "latest_v2",
        },
    )

    assert query["cursor"] == "next"
    assert query["index"] == "2"
    assert query["pageArea"] == "FOLDED"
    assert query["sort_strategy"] == "latest_v2"


def test_tikhub_endpoint_config_accepts_full_url_or_path() -> None:
    full_url = "https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes"

    assert config_path({"searchPath": full_url}, "searchPath", "/fallback") == full_url
    assert build_url("https://api.tikhub.io", full_url, {"keyword": "洗头"}) == (
        "https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes?keyword=%E6%B4%97%E5%A4%B4"
    )
    assert build_url("https://api.tikhub.io", "/api/v1/xiaohongshu/app_v2/search_notes", {"keyword": "洗头"}) == (
        "https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes?keyword=%E6%B4%97%E5%A4%B4"
    )


def test_tikhub_headers_normalize_bearer_token_and_use_api_client_user_agent() -> None:
    headers = tikhub_headers({"tikhubToken": "Bearer abc123"})

    assert normalize_bearer_token("Bearer abc123") == "abc123"
    assert headers["Authorization"] == "Bearer abc123"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert headers["User-Agent"].startswith("axios/")


def test_field_text_reads_feishu_url_and_rich_text_shapes() -> None:
    assert field_text({"link": "https://example.com/a", "text": "打开"}) == "https://example.com/a"
    assert field_text([{"text": "https://example.com/a"}]) == "https://example.com/a"
    assert field_text({"url": "https://example.com/b"}) == "https://example.com/b"

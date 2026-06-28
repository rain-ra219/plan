from __future__ import annotations

from tools.xhs_weekly_report.feishu_output import resolve_weekly_output_tables
from tools.xhs_weekly_report.tikhub_client import (
    comments_response_items,
    extract_comments,
    note_comment_count,
    search_response_items,
)
from tools.xhs_weekly_report.workflow import normalize_ai_mode, parse_model_json


def test_extract_comments_includes_main_and_sub_comments_sorted_by_likes() -> None:
    comments = extract_comments(
        [
            {
                "content": "主评论 A",
                "like_count": 2,
                "user": {"nickname": "用户A"},
                "sub_comments": [
                    {"content": "回复 A1", "like_count": 9, "user": {"nickname": "用户B"}},
                ],
            },
            {
                "content": "主评论 B",
                "like_count": 5,
                "user": {"nickname": "用户C"},
            },
        ]
    )

    assert [item["content"] for item in comments] == ["回复 A1", "主评论 B", "主评论 A"]
    assert comments[0]["type"] == "回复"
    assert comments[2]["type"] == "主评论"


def test_parse_model_json_accepts_fenced_json() -> None:
    parsed = parse_model_json(
        """
        ```json
        {"可参考性": "高", "痛点摘要": "头皮痒"}
        ```
        """
    )

    assert parsed["可参考性"] == "高"
    assert parsed["痛点摘要"] == "头皮痒"


def test_tikhub_response_helpers_accept_common_shapes() -> None:
    note = {"note": {"id": "note_1", "comment_count": 18}}
    assert search_response_items({"data": {"data": {"items": [note]}}}) == [note]
    assert search_response_items({"data": {"items": [note]}}) == [note]
    assert note_comment_count(note) == 18

    comment = {"content": "好用", "like_count": 3}
    assert comments_response_items({"data": {"data": {"comments": [comment]}}}) == [comment]
    assert comments_response_items({"data": {"comments": [comment]}}) == [comment]


def test_normalize_ai_mode_matches_tikhub_integer_query() -> None:
    assert normalize_ai_mode("false") == "0"
    assert normalize_ai_mode("0") == "0"
    assert normalize_ai_mode("") == "0"
    assert normalize_ai_mode("true") == "1"
    assert normalize_ai_mode("是") == "1"


def test_resolve_weekly_output_tables_prefers_feishu_table_registry(temp_db) -> None:
    with temp_db.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO feishu_bases (id, name, app_token, description, enabled, created_at, updated_at)
            VALUES ('base_xhs', 'XHS', 'app_token_xhs', '', 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO feishu_tables (id, base_id, name, table_id, purpose, field_mapping_json, created_at, updated_at)
            VALUES ('tbl_detail', 'base_xhs', 'ai表格', 'tbl_detail_id', 'xhs_detail', '{}', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO feishu_tables (id, base_id, name, table_id, purpose, field_mapping_json, created_at, updated_at)
            VALUES ('tbl_report', 'base_xhs', '每周更新总结报告', 'tbl_report_id', 'xhs_report', '{}', '2026-01-01T00:00:00', '2026-01-01T00:00:00')
            """
        )

        config = resolve_weekly_output_tables(conn, {})

    assert config["detailAppToken"] == "app_token_xhs"
    assert config["detailTableId"] == "tbl_detail_id"
    assert config["reportAppToken"] == "app_token_xhs"
    assert config["reportTableId"] == "tbl_report_id"

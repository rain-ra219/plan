from __future__ import annotations

from tools.product_main_image.workflow import (
    WORKFLOW_ID,
    build_detail_generation_prompt,
    build_main_image_prompt,
    build_prompt_compose_request,
)


def test_main_image_prompt_is_user_prompt_only():
    task = {
        "product_name": "p-20260626078",
        "product_category": "internal-category-value",
        "product_image": "data:image/png;base64,PRODUCT",
        "reference_image": '["data:image/png;base64,REFERENCE"]',
        "prompt": "Create a poster with headline, selling points, price, and campaign section.",
    }

    prompt = build_main_image_prompt(task, WORKFLOW_ID)

    assert prompt == task["prompt"]
    assert "p-20260626078" not in prompt
    assert "internal-category-value" not in prompt
    assert "Generate a clean commercial product main image" not in prompt
    assert "Avoid text overlays" not in prompt


def test_detail_prompt_compose_request_uses_descriptions_without_record_id():
    task = {
        "product_name": "p-20260626078",
        "product_category": "poster",
        "prompt": "Follow the reference poster layout and replace the product with my bottle.",
    }

    request = build_prompt_compose_request(
        task,
        product_description="Silver stainless steel insulated bottle with cylindrical shape.",
        reference_style="Xiaohongshu poster layout, large headline, benefit icons, price badge.",
    )

    assert "Silver stainless steel insulated bottle" in request
    assert "Xiaohongshu poster layout" in request
    assert task["prompt"] in request
    assert "p-20260626078" not in request
    assert "product_name" not in request
    assert "product_category" not in request


def test_detail_generation_prompt_prefers_composed_prompt():
    task = {"prompt": "Original user prompt"}

    prompt = build_detail_generation_prompt(
        task,
        product_description="Product description",
        reference_style="Reference style",
        composed_prompt="Final composed prompt from model.",
    )

    assert prompt == "Final composed prompt from model."


def test_detail_generation_prompt_falls_back_to_joined_context():
    task = {"prompt": "User prompt"}

    prompt = build_detail_generation_prompt(
        task,
        product_description="Product description",
        reference_style="Reference style",
        composed_prompt="",
    )

    assert "Product description" in prompt
    assert "Reference style" in prompt
    assert "User prompt" in prompt

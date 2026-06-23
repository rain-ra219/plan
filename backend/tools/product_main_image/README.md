# Product Main Image

One-click workflow for creating a product main image task.

Current MVP behavior:

1. Create or read a row in `product_tasks`.
2. Build a product image prompt from product name, category, and user prompt.
3. Call `image.generate`.
4. Store the generated file in local generated assets.
5. Record `workflow_runs`, `task_logs`, and `generated_assets`.

If the image API is not configured, the workflow creates a clearly marked local
placeholder image and returns `partial_success` so the full platform loop can be
tested without spending API credits.

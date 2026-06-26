# Product Main Image

One-click workflow for creating a product main image task.

The same implementation also backs the `product-main-detail` Feishu listener
workflow. That workflow reads a product image, optional reference images, an
optional main-image prompt, and writes the main image result back to Feishu.
Detail-page images and copy generation are reserved for later nodes.

Current MVP behavior:

1. Create or read a row in `product_tasks`.
2. For `product-main-detail`, call `image.describe` on the product image.
3. For `product-main-detail`, call `image.describe` on reference images to
   extract style, composition, color, scene, and lighting.
4. Compose the final generation prompt through `prompt.compose`.
5. Call `image.generate`. The detail workflow passes the product image and final
   prompt to generation; reference images influence the prompt rather than being
   blindly mixed into the final image API call.
6. Store the generated file in local generated assets.
7. Record `workflow_runs`, `task_logs`, and `generated_assets`.

If the model API or image API is not configured, the workflow records degraded
steps and returns `partial_success` where appropriate. The image API fallback
creates a clearly marked local placeholder image so the full platform loop can
be tested without spending API credits.

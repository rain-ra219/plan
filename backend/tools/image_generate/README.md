# Image Generate

Provides the `image.generate` capability for product image workflows.

The first implementation supports OpenAI-compatible image generation APIs. When
the image module has no API configuration, it creates a clearly marked local SVG
placeholder so the workflow, logs, and asset storage can still be tested.

`generate_image` also accepts optional `reference_images` data URIs. With one
reference image it sends `image` as a string; with multiple reference images it
sends `image` as an array for providers that support multi-image reference
generation.

Required production config lives on the `image-generator` module:

```text
apiKey
baseUrl
model
authMode
providerMode
```

`authMode` is optional. Use `raw` for the existing `ai.t8star.cn` workflow,
`bearer` for OpenAI-style `Authorization: Bearer ...`, or leave it empty to let
the tool choose a default from the URL.

`providerMode` is optional. Use `images` for `/v1/images/generations`, `chat`
for `/v1/chat/completions`, or leave it empty to auto-detect from `baseUrl`.

Removing this tool disables generated image output, but product task records and
other workflows should continue to work.

# Model Provider

Provides reusable model capabilities for workflows:

- `image.describe`
- `text.generate`
- `prompt.compose`

The first runtime uses an OpenAI-compatible `chat/completions` endpoint. It is
intended for providers such as SiliconFlow and vision-capable Qwen models.

Recommended config for the current MVP:

```text
baseUrl=https://api.siliconflow.cn/v1/chat/completions
model=Qwen/Qwen3.6-27B
authMode=bearer
providerMode=chat
```

Keep API keys in the platform config center. Do not commit keys to git.

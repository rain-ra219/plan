# 项目亮点

## 1. 不是单工具，而是平台

项目没有只做“CSV 同步飞书”这个单点功能，而是把它放进一个 AI 自动化控制台里。

平台本体负责：

- 模块管理
- 配置管理
- 工作流运行
- 状态看板
- 日志追溯
- 失败降级

业务功能作为模块接入。

## 2. capability 抽象

流程不直接依赖飞书，而是依赖能力：

```text
table.write
lead.normalize
customer.merge
file.upload
message.send
```

这样可以做到：

- 当前 `table.write` 由飞书模块提供。
- 飞书停用时，本地数据库仍可保留数据。
- 未来可以替换成 CRM、Airtable、Notion 或 PostgreSQL。
- 工作流异常时，`message.send` 可以由 webhook 通知模块提供。

## 3. 真实业务闭环

当前 MVP 已完成：

```text
上传 CSV -> 线索清洗 -> 客户归并 -> 飞书同步 -> 上传历史 -> 任务日志
```

这不是纯界面演示，而是能跑通数据处理和飞书集成的闭环。

## 4. 线索和客户模型清晰

业务规则明确：

- 一条客户咨询是一条线索。
- 同一客户归并为一个客户记录。
- 客户可以有多条线索。
- 客户表只汇总，不合并丢失具体问题。

这适合真实销售/运营场景。

## 5. 飞书同步去重更新

系统通过 `external_record_mappings` 保存：

```text
本地记录 ID -> 飞书 record_id
```

第一次同步时新增飞书记录，重复上传时更新已有飞书记录，避免重复写入。

## 6. partial_success 失败降级

外部系统失败时，流程不会直接崩溃。

例如：

- 飞书模块停用
- 飞书配置缺失
- 飞书 API 报错

这些情况会记录为 `partial_success`，本地数据仍然保留，任务日志会记录失败原因。

## 7. 全链路任务日志

每一步能力调用都会记录：

- 任务 ID
- 工作流 ID
- 调用模块
- 调用能力
- 输入摘要
- 输出摘要
- 开始时间
- 结束时间
- 耗时
- 状态
- 错误信息
- 重试次数

这让项目具备后台系统的可追溯性。

## 8. 独立消息通知模块

消息通知模块提供 `message.send` 能力。工作流出现 `partial_success` 或 `failed` 时，可以调用 webhook 通知外部系统。

这个模块和飞书同步互不影响：

- 飞书失败不会影响本地数据处理。
- 通知失败不会影响主工作流结果。
- 通知发送结果会进入 `task_logs`。

## 9. Docker 一键运行

项目支持 Docker Compose 和 Windows 双击脚本：

```text
start-formal.bat
stop-formal.bat
```

面试或交付时，可以快速启动正式版：

```text
http://127.0.0.1:3000
```

## 10. 可扩展方向清楚

下一阶段可以自然扩展：

- 商品主图生成模块：`image.generate`
- 文案生成模块：`text.generate`
- 商品详情页生成模块：`page.generate`
- 消息通知模块：`message.send`
- CRM/ERP 对接模块：`table.write` / `table.update`
- 任务队列：Celery + Redis
- 数据库：SQLite -> PostgreSQL
- 模块通信：HTTP / MCP Client

## 求职表达重点

这个项目适合突出：

- 我能把业务脚本平台化。
- 我理解后台系统需要配置、日志、状态和降级。
- 我能做前后端闭环和 Docker 交付。
- 我能把 AI/自动化能力抽象成可插拔模块，而不是堆一次性脚本。

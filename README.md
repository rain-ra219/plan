# AI 自动化后台平台 MVP

这是一个“AI 自动化控制台 / MCP 能力管理后台”的第一版骨架。网站本体负责模块管理、配置、工作流运行、日志和数据查看；业务能力通过模块和能力映射接入。

## 当前 MVP 闭环

CSV 上传 -> 线索清洗 -> 客户归并 -> 同步飞书线索明细表 -> 同步飞书客户表 -> 上传历史/任务日志追溯 -> 数据中心查看线索和客户。

飞书模块已经作为 `table.write` 能力提供方接入。未配置密钥或模块停用时，工作流会把飞书写入步骤记录为 `skipped`，线索和客户仍会写入本地 SQLite。飞书同步成功后，系统会记录“本地记录 ID -> 飞书 record_id”的映射；同一条线索或客户再次上传时会更新飞书记录，而不是重复新增。

工作流状态分为：

- `success`：本地处理和外部同步都成功。
- `partial_success`：本地处理成功，但飞书同步失败或被跳过，数据仍保留在本地。
- `failed`：CSV 解析、清洗、归并等核心步骤失败。

## 项目结构

```text
backend/
  app/
    main.py            FastAPI API 入口
    database.py        SQLite 建表、种子数据、通用查询
    lead_workflow.py   CSV 线索清洗、客户归并、能力调用日志
  requirements.txt
frontend/
  app/
    page.tsx           后台控制台主界面
    globals.css        控制台样式
  package.json
```

## 本地运行

## Docker 运行

Windows 双击启动：

```text
start-formal.bat   启动正式版，访问 http://127.0.0.1:3000
stop-formal.bat    停止正式版
start-demo.bat     启动演示版，访问 http://127.0.0.1:8000
stop-demo.bat      停止演示版
```

正式前后端双容器：

```powershell
cd F:\plan
docker compose up --build
```

访问：

```text
http://127.0.0.1:3000
```

后端 API：

```text
http://127.0.0.1:8000/api/health
```

如果构建环境无法下载 npm/pip 依赖，可以先跑无外部依赖的单容器演示版：

```powershell
cd F:\plan
docker compose -f compose.demo.yaml up --build
```

访问：

```text
http://127.0.0.1:8000
```

数据会保存在 Docker volumes 中：`backend_data`、`backend_uploads`，演示版对应 `demo_data`、`demo_uploads`。

如果 Docker 提示无法连接 daemon：

```text
permission denied while trying to connect to the docker API
```

先确认 Docker Desktop 已启动，再在普通 PowerShell 中运行命令。若仍然报权限问题，用管理员 PowerShell 把当前用户加入 `docker-users` 组，然后退出 Windows 账号重新登录：

```powershell
net localgroup docker-users "$env:USERNAME" /add
```

## 非 Docker 运行

如果当前环境不能联网安装依赖，可以先使用无外部依赖的 MVP 演示入口：

```powershell
cd F:\plan
python backend\dev_server.py
```

访问：

```text
http://127.0.0.1:8000
```

完整 FastAPI + Next.js 运行方式如下。

后端：

```powershell
cd F:\plan
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd F:\plan\frontend
npm.cmd install
npm.cmd run dev
```

访问：

```text
http://127.0.0.1:3000
```

## CSV 字段兼容

导入器会自动识别常见中英文字段名：

- 来源平台：`来源平台`、`source_platform`、`platform`
- 询盘时间：`询盘时间`、`inquiry_time`、`time`
- 客户名称：`客户名称`、`customer_name`、`客户`
- 地区：`地区`、`region`、`国家`
- 联系方式：`联系方式`、`contact`、`手机`、`邮箱`
- 商品标题：`商品标题`、`product_title`、`商品名称`
- 原始咨询内容：`原始咨询内容`、`raw_content`、`咨询内容`、`message`

## 核心表

已创建 MVP 需要的主表：`modules`、`capabilities`、`module_configs`、`workflows`、`workflow_runs`、`task_logs`、`files`、`leads`、`customers`、`external_record_mappings`、`product_tasks`、`generated_assets`。

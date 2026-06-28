# TikHub 工具

这个工具包含两条流程：

```text
TikHub 周报：
关键词 / 笔记数量 / 日期范围
  -> TikHub 搜索小红书笔记
  -> TikHub 抓取评论
  -> 模型逐篇分析
  -> 写入 ai表格
  -> 模型汇总 Markdown 周报
  -> 写入每周更新总结报告

单条小红书链接分析：
飞书数据表填写小红书链接和任务状态
  -> 飞书监听器扫描
  -> task_queue
  -> TikHub 抓取该链接评论
  -> 模型分析
  -> 写入输出表
  -> 回写原数据表状态
```

TikHub 只负责搜索和抓取评论，不负责分析。分析和总结由“模型”模块完成。

## 配置中心

配置中心选择 `TikHub`，只填写 TikHub 请求相关参数：

```text
tikhubToken             TikHub Bearer token
tikhubBaseUrl           可选，默认 https://api.tikhub.io
searchPath              可选，默认 /api/v1/xiaohongshu/app_v2/search_notes
commentsPath            可选，默认 /api/v1/xiaohongshu/app_v2/get_note_comments
source                  可选，默认 explore_feed
aiMode                  可选，默认 false
cursor                  可选，默认空
index                   可选，默认 0
pageArea                可选，默认 UNFOLDED
sort_strategy           可选，默认 like_count
maxCommentsPerNote      可选，默认 100
```

`searchPath` 和 `commentsPath` 支持两种写法：

```text
写法一：只填 path
tikhubBaseUrl = https://api.tikhub.io
searchPath = /api/v1/xiaohongshu/app_v2/search_notes
commentsPath = /api/v1/xiaohongshu/app_v2/get_note_comments

写法二：直接填完整 URL
searchPath = https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes
commentsPath = https://api.tikhub.io/api/v1/xiaohongshu/app_v2/get_note_comments
```

周报输出表不放在 TikHub 配置里。请在“飞书表格配置”里登记：

```text
ai表格：purpose 建议填 xhs_detail 或 xhs_weekly_detail
每周更新总结报告：purpose 建议填 xhs_report 或 xhs_weekly_report
```

提示词不放在配置中心。进入后台左侧 `TikHub` 页面，在“提示词配置”里编辑并保存。

## 表字段

`ai表格` 和单条链接 `输出表` 建议字段：

```text
原帖链接
可参考性
痛点摘要
功效期望
成分态度
竞品情报
价格信号
研发建议
备注
```

`每周更新总结报告` 最小字段：

```text
标题
报告正文
```

const STATUS_LABELS: Record<string, string> = {
  healthy: "健康",
  needs_config: "待配置",
  disabled: "已停用",
  success: "成功",
  partial_success: "部分成功",
  failed: "失败",
  skipped: "已跳过",
  pending: "待处理",
  not_run: "未执行",
  ready: "就绪",
  waiting: "等待",
  running: "运行中",
  scanning: "扫描中",
  stopped: "已停止"
};

const WORKFLOW_TITLES: Record<string, string> = {
  "lead-import-to-feishu": "CSV 线索清洗与飞书同步",
  "product-main-image": "图片生成",
  "product-main-detail": "主图详情页生成"
};

export function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

export function shortId(value: string) {
  return value.length > 14 ? `${value.slice(0, 10)}...` : value;
}

export function shortToken(value?: string) {
  if (!value) return "-";
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

export function formatTime(value?: string) {
  if (!value) return "-";
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  })
    .format(date)
    .replace(/\//g, "-");
}

export function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function workflowTitle(workflowId: string) {
  return WORKFLOW_TITLES[workflowId] ?? workflowId;
}

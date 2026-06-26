type UploadHistory = {
  workflow_run_id: string;
  status: string;
  started_at: string;
  submitted_by?: string;
  note?: string;
  submission_channel?: string;
  filename: string;
  file_id?: string;
  size_bytes: number;
  rows: number;
  lead_count: number;
  customer_count: number;
  tables: Array<{
    module_id: string;
    target: string;
    rows: number;
    status: string;
    error_message?: string;
    created?: number;
    updated?: number;
  }>;
  error_message?: string;
};

export function UploadHistoryView({ items }: { items: UploadHistory[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>上传历史</h2>
        <span>{items.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>文件</th>
              <th>运行ID</th>
              <th>状态</th>
              <th>提交人</th>
              <th>上传时间</th>
              <th>备注</th>
              <th>文件大小</th>
              <th>处理行数</th>
              <th>线索</th>
              <th>客户</th>
              <th>同步表</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.workflow_run_id}>
                <td>
                  <strong>{item.filename || "-"}</strong>
                  <span className="muted block">{item.file_id || "-"}</span>
                </td>
                <td>{shortId(item.workflow_run_id)}</td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
                <td>{item.submitted_by || "-"}</td>
                <td>{formatTime(item.started_at)}</td>
                <td className="summary-cell">{item.note || item.submission_channel || "-"}</td>
                <td>{formatBytes(item.size_bytes)}</td>
                <td>{item.rows}</td>
                <td>{item.lead_count}</td>
                <td>{item.customer_count}</td>
                <td>
                  <div className="history-table-list">
                    {item.tables.length ? (
                      item.tables.map((table) => (
                        <div className="history-table-item" key={`${item.workflow_run_id}-${table.target}`}>
                          <span>{table.target || table.module_id}</span>
                          <StatusBadge status={table.status} />
                          <em>{formatSyncCount(table)}</em>
                        </div>
                      ))
                    ) : (
                      <span className="muted">-</span>
                    )}
                  </div>
                </td>
                <td className="summary-cell">
                  {item.error_message || item.tables.find((table) => table.error_message)?.error_message || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status || "unknown";
  return <span className={`status ${normalized.replace(/_/g, "-")}`}>{statusLabel(normalized)}</span>;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    success: "成功",
    partial_success: "部分成功",
    failed: "失败",
    skipped: "已跳过",
    pending: "待处理",
    running: "运行中"
  };
  return labels[status] ?? status;
}

function shortId(value: string) {
  return value.length > 14 ? `${value.slice(0, 10)}...` : value;
}

function formatTime(value?: string) {
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

function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatSyncCount(table: { rows: number; created?: number; updated?: number }) {
  if (typeof table.created === "number" || typeof table.updated === "number") {
    return `新 ${table.created ?? 0} / 更 ${table.updated ?? 0}`;
  }
  return `${table.rows} 条`;
}

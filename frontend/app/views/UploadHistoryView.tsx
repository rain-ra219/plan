import { StatusBadge } from "../components/StatusBadge";
import { formatBytes, formatTime, shortId } from "../lib/format";
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

function formatSyncCount(table: { rows: number; created?: number; updated?: number }) {
  if (typeof table.created === "number" || typeof table.updated === "number") {
    return `新 ${table.created ?? 0} / 更 ${table.updated ?? 0}`;
  }
  return `${table.rows} 条`;
}

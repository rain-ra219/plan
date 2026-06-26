type TaskLog = {
  id: number;
  task_id: string;
  workflow_run_id: string;
  module_id: string;
  capability: string;
  duration_ms: number;
  status: string;
  error_message?: string;
  retry_count: number;
};

export function LogsView({ logs }: { logs: TaskLog[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>任务日志</h2>
        <span>{logs.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>任务ID</th>
              <th>运行ID</th>
              <th>模块</th>
              <th>能力</th>
              <th>状态</th>
              <th>耗时</th>
              <th>重试</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{shortId(log.task_id)}</td>
                <td>{shortId(log.workflow_run_id)}</td>
                <td>{log.module_id}</td>
                <td>{log.capability}</td>
                <td>
                  <StatusBadge status={log.status} />
                </td>
                <td>{log.duration_ms} ms</td>
                <td>{log.retry_count}</td>
                <td className="summary-cell">{log.error_message || "-"}</td>
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

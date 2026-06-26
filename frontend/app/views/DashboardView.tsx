import { Activity } from "lucide-react";

type Module = {
  id: string;
  name: string;
  enabled: boolean;
  status: string;
};

type Dashboard = {
  todayTasks: number;
  todaySuccess: number;
  todayPartialSuccess: number;
  todayFailed: number;
  avgDurationMs: number;
  abnormalModules: Array<Record<string, unknown>>;
  recentRuns: Array<{
    id: string;
    status: string;
    duration_ms?: number;
  }>;
};

export function DashboardView({ dashboard, modules }: { dashboard: Dashboard | null; modules: Module[] }) {
  const metrics = [
    { label: "今日任务数", value: dashboard?.todayTasks ?? 0 },
    { label: "成功数", value: dashboard?.todaySuccess ?? 0 },
    { label: "部分成功", value: dashboard?.todayPartialSuccess ?? 0 },
    { label: "失败数", value: dashboard?.todayFailed ?? 0 },
    { label: "平均耗时", value: `${dashboard?.avgDurationMs ?? 0} ms` }
  ];
  const abnormalModules = modules.filter((item) => !item.enabled || item.status !== "healthy");

  return (
    <div className="stack">
      <section className="metric-grid">
        {metrics.map((metric) => (
          <article className="metric-card" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </section>
      <section className="split-grid">
        <div className="panel">
          <div className="panel-head">
            <h2>异常模块</h2>
            <span>{dashboard?.abnormalModules.length ?? 0}</span>
          </div>
          <div className="list-block">
            {abnormalModules.length ? (
              abnormalModules.map((item) => (
                <div className="list-row" key={item.id}>
                  <span>{item.name}</span>
                  <StatusBadge status={item.status} />
                </div>
              ))
            ) : (
              <EmptyLine text="暂无异常模块" />
            )}
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <h2>最近任务</h2>
            <Activity size={17} />
          </div>
          <CompactTable
            columns={["运行ID", "状态", "耗时"]}
            rows={(dashboard?.recentRuns ?? []).map((run) => [shortId(run.id), run.status, `${run.duration_ms ?? 0} ms`])}
          />
        </div>
      </section>
    </div>
  );
}

function CompactTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  if (!rows.length) return <EmptyLine text="暂无记录" />;
  return (
    <div className="compact-table">
      <div className="compact-head">
        {columns.map((column) => (
          <span key={column}>{column}</span>
        ))}
      </div>
      {rows.map((row, index) => (
        <div className="compact-row" key={`${row.join("-")}-${index}`}>
          {row.map((cell, cellIndex) => (
            <span key={`${cell}-${cellIndex}`}>{cell}</span>
          ))}
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status || "unknown";
  return <span className={`status ${normalized.replace(/_/g, "-")}`}>{statusLabel(normalized)}</span>;
}

function EmptyLine({ text }: { text: string }) {
  return <div className="empty-line">{text}</div>;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    healthy: "健康",
    needs_config: "待配置",
    disabled: "已停用",
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

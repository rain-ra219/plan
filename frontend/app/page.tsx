"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Database,
  History,
  LayoutDashboard,
  Loader2,
  Play,
  Plug,
  Power,
  PowerOff,
  RefreshCw,
  Server,
  Settings,
  Trash2,
  Upload,
  Workflow
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

type ViewId = "dashboard" | "modules" | "mcp" | "configs" | "upload" | "intake" | "history" | "runs" | "logs" | "data";

type Module = {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  status: string;
  last_error?: string | null;
  capabilities: string[];
  manifest: { configSchema?: Record<string, string> };
};

type Capability = {
  id: number;
  name: string;
  description: string;
  provider_module_id: string;
  fallback_module_id?: string | null;
  enabled: boolean;
};

type ToolManifest = {
  id: string;
  name: string;
  version: string;
  type: string;
  enabled: boolean;
  description?: string;
  provides: string[];
  uses: string[];
  path: string;
  registryStatus: string;
  registryProblems: string[];
};

type McpServer = {
  id: string;
  name: string;
  transport: string;
  endpoint_url: string;
  enabled: boolean;
  status: string;
  last_error?: string | null;
  last_connected_at?: string | null;
  tools: Array<{
    name: string;
    description?: string;
    inputSchema?: Record<string, unknown>;
  }>;
  created_at: string;
  updated_at: string;
};

type McpMapping = {
  id: number;
  server_id: string;
  tool_name: string;
  capability: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

type McpCallLog = {
  id: number;
  server_id: string;
  tool_name: string;
  capability?: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  status: string;
  error_message?: string | null;
};

type Dashboard = {
  todayTasks: number;
  todaySuccess: number;
  todayPartialSuccess: number;
  todayFailed: number;
  avgDurationMs: number;
  abnormalModules: Array<Record<string, unknown>>;
  recentRuns: WorkflowRun[];
  recentLogs: TaskLog[];
};

type WorkflowRun = {
  id: string;
  workflow_id: string;
  status: string;
  input_summary?: string;
  output_summary?: string;
  started_at: string;
  ended_at?: string;
  duration_ms?: number;
  error_message?: string;
};

type TaskLog = {
  id: number;
  task_id: string;
  workflow_id: string;
  workflow_run_id: string;
  module_id: string;
  capability: string;
  input_summary?: string;
  output_summary?: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  status: string;
  error_message?: string;
  retry_count: number;
};

type UploadHistory = {
  workflow_run_id: string;
  workflow_id: string;
  status: string;
  started_at: string;
  ended_at?: string;
  duration_ms?: number;
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
    capability: string;
    target: string;
    rows: number;
    status: string;
    duration_ms: number;
    error_message?: string;
    created?: number;
    updated?: number;
    unmapped_created?: number;
  }>;
  error_message?: string;
};

type IntakeListener = {
  id: string;
  enabled: boolean;
  interval_seconds: number;
  status: string;
  last_scan_at?: string;
  next_scan_at?: string;
  last_error?: string;
};

type IntakeRun = {
  id: string;
  listener_id: string;
  trigger_type: string;
  status: string;
  scanned_count: number;
  processed_count: number;
  success_count: number;
  partial_count: number;
  failed_count: number;
  skipped_count: number;
  error_message?: string;
  started_at: string;
  ended_at?: string;
  duration_ms?: number;
  records: Array<{
    remote_record_id: string;
    filename?: string;
    submitted_by?: string;
    note?: string;
    workflow_run_id?: string;
    status: string;
    error_message?: string;
    created_at: string;
  }>;
};

type Lead = {
  id: string;
  source_platform?: string;
  inquiry_time?: string;
  customer_name?: string;
  contact_person?: string;
  region?: string;
  contact?: string;
  product_title?: string;
  quantity?: string;
  missing_info?: string;
  intent_level?: string;
  suggested_reply?: string;
  customer_id: string;
  status: string;
};

type Customer = {
  id: string;
  customer_name?: string;
  contact_person?: string;
  region?: string;
  contact?: string;
  source_platform?: string;
  lead_count: number;
  pending_count: number;
  latest_inquiry_time?: string;
  customer_status?: string;
  key_reason?: string;
  summary?: string;
};

type ConfigPayload = {
  module: Module;
  schema: Record<string, string>;
  values: Record<string, string>;
};

const navigation: Array<{ id: ViewId; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "dashboard", label: "仪表盘", icon: LayoutDashboard },
  { id: "modules", label: "功能管理", icon: Plug },
  { id: "mcp", label: "MCP 管理", icon: Server },
  { id: "configs", label: "配置中心", icon: Settings },
  { id: "upload", label: "CSV 上传", icon: Upload },
  { id: "intake", label: "飞书监听", icon: Activity },
  { id: "history", label: "上传历史", icon: History },
  { id: "runs", label: "工作流运行", icon: Workflow },
  { id: "logs", label: "任务日志", icon: ClipboardList },
  { id: "data", label: "数据中心", icon: Database }
];

const viewIds = new Set<ViewId>(navigation.map((item) => item.id));

function initialView(): ViewId {
  if (typeof window === "undefined") return "dashboard";
  const value = new URLSearchParams(window.location.search).get("view") as ViewId | null;
  return value && viewIds.has(value) ? value : "dashboard";
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `请求失败：${res.status}`);
  }
  return res.json();
}

export default function ConsolePage() {
  const [view, setView] = useState<ViewId>("dashboard");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [modules, setModules] = useState<Module[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [tools, setTools] = useState<ToolManifest[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [mcpMappings, setMcpMappings] = useState<McpMapping[]>([]);
  const [mcpLogs, setMcpLogs] = useState<McpCallLog[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [uploadHistory, setUploadHistory] = useState<UploadHistory[]>([]);
  const [intakeListener, setIntakeListener] = useState<IntakeListener | null>(null);
  const [intakeRuns, setIntakeRuns] = useState<IntakeRun[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const refreshAll = async () => {
    setLoading(true);
    try {
      const [
        dashboardData,
        moduleData,
        capabilityData,
        toolData,
        mcpServerData,
        mcpMappingData,
        mcpLogData,
        runData,
        logData,
        historyData,
        intakeStateData,
        intakeRunData,
        leadData,
        customerData
      ] = await Promise.all([
        api<Dashboard>("/api/dashboard"),
        api<Module[]>("/api/modules"),
        api<Capability[]>("/api/capabilities"),
        api<ToolManifest[]>("/api/tools"),
        api<McpServer[]>("/api/mcp/servers"),
        api<McpMapping[]>("/api/mcp/mappings"),
        api<McpCallLog[]>("/api/mcp/call-logs"),
        api<WorkflowRun[]>("/api/workflow-runs"),
        api<TaskLog[]>("/api/task-logs"),
        api<UploadHistory[]>("/api/upload-history"),
        api<IntakeListener>("/api/intake/listener"),
        api<IntakeRun[]>("/api/intake/runs"),
        api<Lead[]>("/api/leads"),
        api<Customer[]>("/api/customers")
      ]);
      setDashboard(dashboardData);
      setModules(moduleData);
      setCapabilities(capabilityData);
      setTools(toolData);
      setMcpServers(mcpServerData);
      setMcpMappings(mcpMappingData);
      setMcpLogs(mcpLogData);
      setRuns(runData);
      setLogs(logData);
      setUploadHistory(historyData);
      setIntakeListener(intakeStateData);
      setIntakeRuns(intakeRunData);
      setLeads(leadData);
      setCustomers(customerData);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setView(initialView());
    refreshAll();
  }, []);

  const currentTitle = navigation.find((item) => item.id === view)?.label ?? "仪表盘";

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <strong>自动化控制台 Lite</strong>
            <span>轻量 MCP 工具管理后台</span>
          </div>
        </div>
        <nav className="nav-list">
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={view === item.id ? "nav-item active" : "nav-item"}
                onClick={() => setView(item.id)}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">AI Automation Console</p>
            <h1>{currentTitle}</h1>
          </div>
          <button className="button secondary" onClick={refreshAll} disabled={loading}>
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            刷新
          </button>
        </header>

        {notice ? (
          <div className="notice">
            <AlertTriangle size={16} />
            <span>{notice}</span>
            <button onClick={() => setNotice("")}>关闭</button>
          </div>
        ) : null}

        {view === "dashboard" && <DashboardView dashboard={dashboard} modules={modules} />}
        {view === "modules" && (
          <ModulesView modules={modules} capabilities={capabilities} tools={tools} busy={busy} setBusy={setBusy} refreshAll={refreshAll} setNotice={setNotice} />
        )}
        {view === "mcp" && (
          <McpView
            servers={mcpServers}
            mappings={mcpMappings}
            logs={mcpLogs}
            busy={busy}
            setBusy={setBusy}
            setNotice={setNotice}
            refreshAll={refreshAll}
          />
        )}
        {view === "configs" && <ConfigView modules={modules} setNotice={setNotice} refreshAll={refreshAll} />}
        {view === "upload" && <UploadView setNotice={setNotice} setBusy={setBusy} busy={busy} refreshAll={refreshAll} />}
        {view === "intake" && (
          <IntakeListenerView
            listener={intakeListener}
            runs={intakeRuns}
            setNotice={setNotice}
            setBusy={setBusy}
            busy={busy}
            refreshAll={refreshAll}
          />
        )}
        {view === "history" && <UploadHistoryView items={uploadHistory} />}
        {view === "runs" && <RunsView runs={runs} />}
        {view === "logs" && <LogsView logs={logs} />}
        {view === "data" && <DataView leads={leads} customers={customers} />}
      </section>
    </main>
  );
}

function DashboardView({ dashboard, modules }: { dashboard: Dashboard | null; modules: Module[] }) {
  const metrics = [
    { label: "今日任务数", value: dashboard?.todayTasks ?? 0 },
    { label: "成功数", value: dashboard?.todaySuccess ?? 0 },
    { label: "部分成功", value: dashboard?.todayPartialSuccess ?? 0 },
    { label: "失败数", value: dashboard?.todayFailed ?? 0 },
    { label: "平均耗时", value: `${dashboard?.avgDurationMs ?? 0} ms` }
  ];
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
            {modules.filter((item) => !item.enabled || item.status !== "healthy").length ? (
              modules
                .filter((item) => !item.enabled || item.status !== "healthy")
                .map((item) => (
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

function ModulesView({
  modules,
  capabilities,
  tools,
  busy,
  setBusy,
  refreshAll,
  setNotice
}: {
  modules: Module[];
  capabilities: Capability[];
  tools: ToolManifest[];
  busy: string;
  setBusy: (value: string) => void;
  refreshAll: () => Promise<void>;
  setNotice: (value: string) => void;
}) {
  const capabilityByProvider = useMemo(() => {
    return capabilities.reduce<Record<string, Capability[]>>((acc, capability) => {
      const key = capability.provider_module_id;
      acc[key] = acc[key] ? [...acc[key], capability] : [capability];
      return acc;
    }, {});
  }, [capabilities]);

  const toggle = async (module: Module) => {
    setBusy(module.id);
    try {
      await api(`/api/modules/${module.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !module.enabled })
      });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "更新模块失败");
    } finally {
      setBusy("");
    }
  };

  const test = async (module: Module) => {
    setBusy(module.id);
    try {
      const result = await api<{ message: string }>(`/api/modules/${module.id}/test`, { method: "POST" });
      setNotice(result.message);
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "测试连接失败");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
      <div className="panel-head">
        <h2>功能模块</h2>
        <span>{modules.length} 个模块</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>模块</th>
              <th>版本</th>
              <th>健康状态</th>
              <th>能力</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {modules.map((module) => (
              <tr key={module.id}>
                <td>
                  <strong>{module.name}</strong>
                  <span className="muted block">{module.id}</span>
                </td>
                <td>{module.version}</td>
                <td>
                  <StatusBadge status={module.status} />
                </td>
                <td>
                  <div className="badge-row">
                    {(capabilityByProvider[module.id] ?? []).map((capability) => (
                      <span className="capability" key={capability.name}>
                        {capability.name}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <div className="action-row">
                    <button className="icon-button" onClick={() => toggle(module)} disabled={busy === module.id} title={module.enabled ? "停用模块" : "启用模块"}>
                      {module.enabled ? <PowerOff size={16} /> : <Power size={16} />}
                      {module.enabled ? "停用" : "启用"}
                    </button>
                    <button className="icon-button" onClick={() => test(module)} disabled={busy === module.id} title="测试连接">
                      <CheckCircle2 size={16} />
                      测试
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>

      <section className="panel">
        <div className="panel-head">
          <h2>工具目录</h2>
          <span>{tools.length} 个工具</span>
        </div>
        <div className="tool-grid">
          {tools.length ? (
            tools.map((tool) => (
              <article className="tool-card" key={tool.id}>
                <div className="tool-card-head">
                  <div>
                    <strong>{tool.name}</strong>
                    <span>{tool.path}</span>
                  </div>
                  <StatusBadge status={tool.registryStatus === "valid" ? "healthy" : "failed"} />
                </div>
                <div className="tool-meta">
                  <span>{tool.id}</span>
                  <span>{tool.type}</span>
                  <span>v{tool.version}</span>
                </div>
                {tool.description ? <p>{tool.description}</p> : null}
                <ToolCapabilityBlock title="提供" values={tool.provides} />
                <ToolCapabilityBlock title="依赖" values={tool.uses} />
                {tool.registryProblems.length ? <p className="error-text">{tool.registryProblems.join("；")}</p> : null}
              </article>
            ))
          ) : (
            <EmptyLine text="暂无工具 manifest" />
          )}
        </div>
      </section>
    </div>
  );
}

function ToolCapabilityBlock({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="tool-capability-block">
      <span>{title}</span>
      <div className="badge-row">
        {values.length ? values.map((value) => <span className="capability" key={value}>{value}</span>) : <span className="muted">-</span>}
      </div>
    </div>
  );
}

function McpView({
  servers,
  mappings,
  logs,
  busy,
  setBusy,
  setNotice,
  refreshAll
}: {
  servers: McpServer[];
  mappings: McpMapping[];
  logs: McpCallLog[];
  busy: string;
  setBusy: (value: string) => void;
  setNotice: (value: string) => void;
  refreshAll: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [selectedServerId, setSelectedServerId] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [capability, setCapability] = useState("");
  const [argumentsText, setArgumentsText] = useState("{}");
  const selectedServer = servers.find((server) => server.id === selectedServerId) ?? servers[0];
  const selectedTools = selectedServer?.tools ?? [];

  useEffect(() => {
    if (!selectedServerId && servers[0]?.id) {
      setSelectedServerId(servers[0].id);
    }
  }, [servers, selectedServerId]);

  useEffect(() => {
    if (!selectedTool && selectedTools[0]?.name) {
      setSelectedTool(selectedTools[0].name);
    }
  }, [selectedTool, selectedTools]);

  const createServer = async () => {
    if (!name.trim() || !endpointUrl.trim()) {
      setNotice("请填写 MCP 服务名称和 endpoint");
      return;
    }
    setBusy("mcp-create");
    try {
      await api<McpServer>("/api/mcp/servers", {
        method: "POST",
        body: JSON.stringify({ name, endpoint_url: endpointUrl, transport: "http", enabled: true })
      });
      setName("");
      setEndpointUrl("");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "添加 MCP 服务失败");
    } finally {
      setBusy("");
    }
  };

  const patchServer = async (server: McpServer, enabled: boolean) => {
    setBusy(server.id);
    try {
      await api<McpServer>(`/api/mcp/servers/${server.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled })
      });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "更新 MCP 服务失败");
    } finally {
      setBusy("");
    }
  };

  const deleteServer = async (server: McpServer) => {
    setBusy(server.id);
    try {
      await api(`/api/mcp/servers/${server.id}`, { method: "DELETE" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除 MCP 服务失败");
    } finally {
      setBusy("");
    }
  };

  const discover = async (server: McpServer) => {
    setBusy(`discover-${server.id}`);
    try {
      await api<McpServer>(`/api/mcp/servers/${server.id}/discover`, { method: "POST" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "发现 MCP 工具失败");
      await refreshAll();
    } finally {
      setBusy("");
    }
  };

  const saveMapping = async () => {
    if (!selectedServer || !selectedTool || !capability.trim()) {
      setNotice("请选择 MCP 工具并填写 capability");
      return;
    }
    setBusy("mcp-map");
    try {
      await api<McpMapping>("/api/mcp/mappings", {
        method: "POST",
        body: JSON.stringify({
          server_id: selectedServer.id,
          tool_name: selectedTool,
          capability,
          enabled: true
        })
      });
      await refreshAll();
      setNotice("MCP 能力映射已保存");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存 MCP 映射失败");
    } finally {
      setBusy("");
    }
  };

  const callTool = async () => {
    if (!selectedServer || !selectedTool) {
      setNotice("请选择 MCP 服务和工具");
      return;
    }
    let args: Record<string, unknown>;
    try {
      args = JSON.parse(argumentsText || "{}");
    } catch {
      setNotice("arguments 必须是合法 JSON");
      return;
    }
    setBusy("mcp-call");
    try {
      const result = await api<{ status: string; duration_ms: number; result: Record<string, unknown> }>(`/api/mcp/servers/${selectedServer.id}/call`, {
        method: "POST",
        body: JSON.stringify({ tool_name: selectedTool, arguments: args, capability })
      });
      setNotice(`调用完成：${result.duration_ms} ms`);
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "MCP 工具调用失败");
      await refreshAll();
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>MCP 服务</h2>
          <span>{servers.length} 个服务</span>
        </div>
        <div className="mcp-create-row">
          <input placeholder="服务名称，例如 PDF MCP" value={name} onChange={(event) => setName(event.target.value)} />
          <input placeholder="HTTP endpoint，例如 http://host:port/mcp" value={endpointUrl} onChange={(event) => setEndpointUrl(event.target.value)} />
          <button className="button primary" onClick={createServer} disabled={busy === "mcp-create"}>
            {busy === "mcp-create" ? <Loader2 className="spin" size={16} /> : <Server size={16} />}
            添加服务
          </button>
        </div>
        <div className="tool-grid">
          {servers.length ? (
            servers.map((server) => (
              <article className="tool-card" key={server.id}>
                <div className="tool-card-head">
                  <div>
                    <strong>{server.name}</strong>
                    <span>{server.endpoint_url}</span>
                  </div>
                  <StatusBadge status={server.enabled ? server.status : "disabled"} />
                </div>
                <div className="tool-meta">
                  <span>{server.transport}</span>
                  <span>{server.tools.length} tools</span>
                  <span>{formatTime(server.last_connected_at ?? undefined)}</span>
                </div>
                {server.last_error ? <p className="error-text">{server.last_error}</p> : null}
                <div className="action-row">
                  <button className="icon-button" onClick={() => patchServer(server, !server.enabled)} disabled={busy === server.id}>
                    {server.enabled ? <PowerOff size={16} /> : <Power size={16} />}
                    {server.enabled ? "停用" : "启用"}
                  </button>
                  <button className="icon-button" onClick={() => discover(server)} disabled={busy === `discover-${server.id}`}>
                    {busy === `discover-${server.id}` ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                    发现工具
                  </button>
                  <button className="icon-button" onClick={() => deleteServer(server)} disabled={busy === server.id}>
                    <Trash2 size={16} />
                    删除
                  </button>
                </div>
                <ToolCapabilityBlock title="工具" values={server.tools.map((tool) => tool.name)} />
              </article>
            ))
          ) : (
            <EmptyLine text="暂无 MCP 服务" />
          )}
        </div>
      </section>

      <section className="split-grid">
        <div className="panel">
          <div className="panel-head">
            <h2>工具调用</h2>
            <span>tools/call</span>
          </div>
          <div className="form-grid single">
            <label className="field">
              <span>server</span>
              <select value={selectedServer?.id ?? ""} onChange={(event) => setSelectedServerId(event.target.value)}>
                {servers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>tool</span>
              <select value={selectedTool} onChange={(event) => setSelectedTool(event.target.value)}>
                {selectedTools.map((tool) => (
                  <option key={tool.name} value={tool.name}>
                    {tool.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>capability</span>
              <input placeholder="例如 file.parse / image.generate" value={capability} onChange={(event) => setCapability(event.target.value)} />
            </label>
            <label className="field">
              <span>arguments JSON</span>
              <textarea value={argumentsText} onChange={(event) => setArgumentsText(event.target.value)} />
            </label>
            <div className="action-row">
              <button className="button secondary" onClick={saveMapping} disabled={busy === "mcp-map" || !selectedServer || !selectedTool}>
                {busy === "mcp-map" ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
                保存映射
              </button>
              <button className="button primary" onClick={callTool} disabled={busy === "mcp-call" || !selectedServer || !selectedTool}>
                {busy === "mcp-call" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
                调用工具
              </button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>能力映射</h2>
            <span>{mappings.length}</span>
          </div>
          <div className="list-block">
            {mappings.length ? (
              mappings.map((mapping) => (
                <div className="list-row" key={mapping.id}>
                  <span>{mapping.capability}</span>
                  <span className="muted">{mapping.tool_name}</span>
                </div>
              ))
            ) : (
              <EmptyLine text="暂无 MCP 能力映射" />
            )}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>MCP 调用日志</h2>
          <span>{logs.length}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>服务</th>
                <th>工具</th>
                <th>能力</th>
                <th>状态</th>
                <th>耗时</th>
                <th>时间</th>
                <th>输出/错误</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td>{log.server_id}</td>
                  <td>{log.tool_name}</td>
                  <td>{log.capability || "-"}</td>
                  <td>
                    <StatusBadge status={log.status} />
                  </td>
                  <td>{log.duration_ms} ms</td>
                  <td>{formatTime(log.started_at)}</td>
                  <td className="summary-cell">{log.error_message || JSON.stringify(log.output)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ConfigView({ modules, setNotice, refreshAll }: { modules: Module[]; setNotice: (value: string) => void; refreshAll: () => Promise<void> }) {
  const configurable = modules.filter((module) => Object.keys(module.manifest.configSchema ?? {}).length > 0);
  const [selectedId, setSelectedId] = useState(configurable[0]?.id ?? "");
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!selectedId && configurable[0]?.id) {
      setSelectedId(configurable[0].id);
    }
  }, [configurable, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    api<ConfigPayload>(`/api/modules/${selectedId}/config`)
      .then((payload) => {
        setConfig(payload);
        setValues(payload.values);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "配置加载失败"));
  }, [selectedId, setNotice]);

  const save = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const payload = await api<ConfigPayload>(`/api/modules/${selectedId}/config`, {
        method: "PUT",
        body: JSON.stringify({ values })
      });
      setConfig(payload);
      setValues(payload.values);
      setNotice("配置已保存");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存配置失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>模块配置</h2>
        <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          {configurable.map((module) => (
            <option key={module.id} value={module.id}>
              {module.name}
            </option>
          ))}
        </select>
      </div>
      {config ? (
        <div className="form-grid">
          {Object.entries(config.schema).map(([key, type]) => (
            <label className="field" key={key}>
              <span>
                {key}
                <em>{type}</em>
              </span>
              <input
                type={type === "secret" ? "password" : "text"}
                value={values[key] ?? ""}
                onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
              />
            </label>
          ))}
          <button className="button primary fit" onClick={save} disabled={saving}>
            {saving ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
            保存配置
          </button>
        </div>
      ) : (
        <EmptyLine text="暂无可配置模块" />
      )}
    </section>
  );
}

function UploadView({
  setNotice,
  setBusy,
  busy,
  refreshAll
}: {
  setNotice: (value: string) => void;
  setBusy: (value: string) => void;
  busy: string;
  refreshAll: () => Promise<void>;
}) {
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setFilename(file.name);
    setContent(await file.text());
    setResult(null);
  };

  const runWorkflow = async () => {
    if (!content) {
      setNotice("请选择 CSV 文件");
      return;
    }
    setBusy("run-workflow");
    try {
      const payload = await api<Record<string, unknown>>("/api/workflows/lead-import/run", {
        method: "POST",
        body: JSON.stringify({ filename, content })
      });
      setResult(payload);
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "工作流运行失败");
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>CSV 线索导入</h2>
        <StatusBadge status={content ? "ready" : "waiting"} />
      </div>
      <div className="upload-zone">
        <input type="file" accept=".csv,text/csv" onChange={(event) => handleFile(event.target.files?.[0])} />
        <div>
          <strong>{filename || "未选择文件"}</strong>
          <span>{content ? `${content.length} 个字符` : "等待上传 CSV"}</span>
        </div>
        <button className="button primary" onClick={runWorkflow} disabled={busy === "run-workflow"}>
          {busy === "run-workflow" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
          运行工作流
        </button>
      </div>
      {result ? (
        <pre className="result-box">{JSON.stringify(result, null, 2)}</pre>
      ) : null}
    </section>
  );
}

function RunsView({ runs }: { runs: WorkflowRun[] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>工作流运行记录</h2>
        <span>{runs.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>运行ID</th>
              <th>工作流</th>
              <th>状态</th>
              <th>开始时间</th>
              <th>耗时</th>
              <th>输出摘要</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{shortId(run.id)}</td>
                <td>{run.workflow_id}</td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>{formatTime(run.started_at)}</td>
                <td>{run.duration_ms ?? 0} ms</td>
                <td className="summary-cell">{run.output_summary || run.error_message || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LogsView({ logs }: { logs: TaskLog[] }) {
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

function IntakeListenerView({
  listener,
  runs,
  setNotice,
  setBusy,
  busy,
  refreshAll
}: {
  listener: IntakeListener | null;
  runs: IntakeRun[];
  setNotice: (value: string) => void;
  setBusy: (value: string) => void;
  busy: string;
  refreshAll: () => Promise<void>;
}) {
  const [intervalSeconds, setIntervalSeconds] = useState(listener?.interval_seconds ?? 60);

  useEffect(() => {
    if (listener?.interval_seconds) {
      setIntervalSeconds(listener.interval_seconds);
    }
  }, [listener?.interval_seconds]);

  const patchListener = async (enabled?: boolean) => {
    setBusy("intake-toggle");
    try {
      await api<IntakeListener>("/api/intake/listener", {
        method: "PATCH",
        body: JSON.stringify({ enabled, interval_seconds: intervalSeconds })
      });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "更新监听器失败");
    } finally {
      setBusy("");
    }
  };

  const scanNow = async () => {
    setBusy("intake-scan");
    try {
      await api<Record<string, unknown>>("/api/intake/scan", { method: "POST" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "扫描失败");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>飞书表单监听</h2>
          <StatusBadge status={listener?.enabled ? listener.status : "disabled"} />
        </div>
        <div className="listener-grid">
          <div className="helper-block">
            <strong>轮询模式</strong>
            <span>默认关闭。开启后按间隔扫描飞书提交任务表，只处理“待处理”记录，每次最多处理 10 条。</span>
            <span>飞书任务表字段建议：处理状态、CSV 文件、提交人、提交说明、处理结果、工作流ID、错误信息、处理时间。</span>
          </div>
          <div className="listener-controls">
            <label>
              扫描间隔（秒）
              <input
                type="number"
                min={30}
                max={3600}
                value={intervalSeconds}
                onChange={(event) => setIntervalSeconds(Number(event.target.value))}
              />
            </label>
            <button className="button secondary" onClick={() => patchListener(listener?.enabled)} disabled={busy === "intake-toggle"}>
              {busy === "intake-toggle" ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
              保存间隔
            </button>
            <button className={listener?.enabled ? "button danger" : "button primary"} onClick={() => patchListener(!listener?.enabled)} disabled={busy === "intake-toggle"}>
              {listener?.enabled ? <PowerOff size={16} /> : <Power size={16} />}
              {listener?.enabled ? "关闭监听" : "打开监听"}
            </button>
            <button className="button secondary" onClick={scanNow} disabled={busy === "intake-scan"}>
              {busy === "intake-scan" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              立即扫描
            </button>
          </div>
        </div>
        <div className="listener-meta">
          <span>上次扫描：{formatTime(listener?.last_scan_at)}</span>
          <span>下次扫描：{formatTime(listener?.next_scan_at)}</span>
          <span>错误：{listener?.last_error || "-"}</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>监听处理历史</h2>
          <span>{runs.length}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>扫描ID</th>
                <th>触发</th>
                <th>状态</th>
                <th>开始时间</th>
                <th>扫描</th>
                <th>处理</th>
                <th>成功/部分/失败</th>
                <th>记录</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>{shortId(run.id)}</td>
                  <td>{run.trigger_type === "auto" ? "自动" : "手动"}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{formatTime(run.started_at)}</td>
                  <td>{run.scanned_count}</td>
                  <td>{run.processed_count}</td>
                  <td>{run.success_count} / {run.partial_count} / {run.failed_count}</td>
                  <td className="summary-cell">{formatIntakeRecords(run.records)}</td>
                  <td className="summary-cell">{run.error_message || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function UploadHistoryView({ items }: { items: UploadHistory[] }) {
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

function DataView({ leads, customers }: { leads: Lead[]; customers: Customer[] }) {
  const [tab, setTab] = useState<"leads" | "customers">("leads");
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>业务数据</h2>
        <div className="segmented">
          <button className={tab === "leads" ? "active" : ""} onClick={() => setTab("leads")}>
            线索
          </button>
          <button className={tab === "customers" ? "active" : ""} onClick={() => setTab("customers")}>
            客户
          </button>
        </div>
      </div>
      {tab === "leads" ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>客户</th>
                <th>联系人</th>
                <th>平台</th>
                <th>商品</th>
                <th>数量</th>
                <th>意向</th>
                <th>缺失信息</th>
                <th>建议回复</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td>{lead.customer_name}</td>
                  <td>{lead.contact_person || "-"}</td>
                  <td>{lead.source_platform}</td>
                  <td>{lead.product_title || "-"}</td>
                  <td>{lead.quantity || "-"}</td>
                  <td>{lead.intent_level}</td>
                  <td>{lead.missing_info || "-"}</td>
                  <td className="summary-cell">{lead.suggested_reply}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>客户</th>
                <th>联系人</th>
                <th>地区</th>
                <th>来源</th>
                <th>联系方式</th>
                <th>线索数</th>
                <th>待处理</th>
                <th>状态</th>
                <th>摘要</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((customer) => (
                <tr key={customer.id}>
                  <td>{customer.customer_name}</td>
                  <td>{customer.contact_person || "-"}</td>
                  <td>{customer.region || "-"}</td>
                  <td>{customer.source_platform || "-"}</td>
                  <td>{customer.contact || "-"}</td>
                  <td>{customer.lead_count}</td>
                  <td>{customer.pending_count}</td>
                  <td>{customer.customer_status || "-"}</td>
                  <td className="summary-cell">{customer.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
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
    ready: "就绪",
    waiting: "等待",
    running: "运行中",
    scanning: "扫描中",
    stopped: "已停止"
  };
  return labels[status] ?? status;
}

function shortId(value: string) {
  return value.length > 14 ? `${value.slice(0, 10)}...` : value;
}

function formatTime(value?: string) {
  if (!value) return "-";
  return value.replace("T", " ").replace("+00:00", "");
}

function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatIntakeRecords(records: IntakeRun["records"]) {
  if (!records.length) return "-";
  return records
    .slice(0, 3)
    .map((record) => `${record.filename || record.remote_record_id} ${statusLabel(record.status)}`)
    .join("；");
}

function formatSyncCount(table: { rows: number; created?: number; updated?: number }) {
  if (typeof table.created === "number" || typeof table.updated === "number") {
    return `新 ${table.created ?? 0} / 更 ${table.updated ?? 0}`;
  }
  return `${table.rows} 条`;
}

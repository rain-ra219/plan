"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Database,
  History,
  Image as ImageIcon,
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

type ViewId = "dashboard" | "modules" | "mcp" | "mainImage" | "configs" | "upload" | "intake" | "history" | "runs" | "logs" | "data";

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

type WorkflowStepTemplate = {
  id: string;
  label: string;
  module_id?: string;
  capability?: string;
  target?: string;
  optional?: boolean;
};

type WorkflowNodeView = {
  id: string;
  label: string;
  status: string;
  module_id: string;
  capability: string;
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  input_summary?: string;
  output_summary?: string;
  error_message?: string;
  retry_count: number;
  task_id?: string;
  log_id?: number;
  optional?: boolean;
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

type FeishuBase = {
  id: string;
  name: string;
  app_token: string;
  description?: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
};

type FeishuTableConfig = {
  id: string;
  base_id: string;
  base_name?: string;
  app_token?: string;
  name: string;
  table_id: string;
  purpose: string;
  field_mapping: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type IntakeListener = {
  id: string;
  name: string;
  base_id?: string | null;
  table_config_id?: string | null;
  workflow_id: string;
  enabled: boolean;
  interval_seconds: number;
  status: string;
  last_scan_at?: string;
  next_scan_at?: string;
  last_error?: string;
  status_field: string;
  file_field: string;
  submitter_field: string;
  note_field: string;
  result_field: string;
  run_id_field: string;
  error_field: string;
  processed_at_field: string;
  pending_value: string;
  processing_value: string;
  success_value: string;
  partial_value: string;
  failed_value: string;
  table_name?: string;
  table_id?: string;
  base_name?: string;
  app_token?: string;
};

type IntakeRun = {
  id: string;
  listener_id: string;
  listener_name?: string;
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

type ProductTask = {
  id: string;
  product_name?: string;
  product_category?: string;
  prompt?: string;
  main_image_ratio?: string;
  main_image_status?: string;
  detail_page_status?: string;
  copy_status?: string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
  main_image_url?: string;
  main_image_asset?: {
    id: string;
    path: string;
    asset_type: string;
    created_at: string;
  } | null;
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
  { id: "mainImage", label: "主图生成", icon: ImageIcon },
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
  const [productTasks, setProductTasks] = useState<ProductTask[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [uploadHistory, setUploadHistory] = useState<UploadHistory[]>([]);
  const [feishuBases, setFeishuBases] = useState<FeishuBase[]>([]);
  const [feishuTables, setFeishuTables] = useState<FeishuTableConfig[]>([]);
  const [intakeListeners, setIntakeListeners] = useState<IntakeListener[]>([]);
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
        productTaskData,
        runData,
        logData,
        historyData,
        feishuBaseData,
        feishuTableData,
        intakeListenerData,
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
        api<ProductTask[]>("/api/product-tasks"),
        api<WorkflowRun[]>("/api/workflow-runs"),
        api<TaskLog[]>("/api/task-logs"),
        api<UploadHistory[]>("/api/upload-history"),
        api<FeishuBase[]>("/api/feishu/bases"),
        api<FeishuTableConfig[]>("/api/feishu/tables"),
        api<IntakeListener[]>("/api/intake/listeners"),
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
      setProductTasks(productTaskData);
      setRuns(runData);
      setLogs(logData);
      setUploadHistory(historyData);
      setFeishuBases(feishuBaseData);
      setFeishuTables(feishuTableData);
      setIntakeListeners(intakeListenerData);
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
        {view === "mainImage" && (
          <MainImageView
            tasks={productTasks}
            busy={busy}
            setBusy={setBusy}
            setNotice={setNotice}
            refreshAll={refreshAll}
          />
        )}
        {view === "configs" && <ConfigViewV2 modules={modules} setNotice={setNotice} refreshAll={refreshAll} />}
        {view === "upload" && <UploadView setNotice={setNotice} setBusy={setBusy} busy={busy} refreshAll={refreshAll} />}
        {view === "intake" && (
          <IntakeListenerView
            bases={feishuBases}
            tables={feishuTables}
            listeners={intakeListeners}
            runs={intakeRuns}
            setNotice={setNotice}
            setBusy={setBusy}
            busy={busy}
            refreshAll={refreshAll}
          />
        )}
        {view === "history" && <UploadHistoryView items={uploadHistory} />}
        {view === "runs" && <RunsView runs={runs} logs={logs} />}
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

function MainImageView({
  tasks,
  busy,
  setBusy,
  setNotice,
  refreshAll
}: {
  tasks: ProductTask[];
  busy: string;
  setBusy: (value: string) => void;
  setNotice: (value: string) => void;
  refreshAll: () => Promise<void>;
}) {
  const [productName, setProductName] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [ratio, setRatio] = useState("1:1");
  const [prompt, setPrompt] = useState("");

  const generate = async () => {
    if (!productName.trim()) {
      setNotice("请填写商品名称");
      return;
    }
    setBusy("main-image-generate");
    try {
      const result = await api<{ task: ProductTask; workflow: Record<string, unknown> }>("/api/product-tasks/main-image", {
        method: "POST",
        body: JSON.stringify({
          product_name: productName,
          product_category: productCategory,
          main_image_ratio: ratio,
          prompt
        })
      });
      setNotice(result.workflow.status === "success" ? "主图生成完成" : "已生成占位主图，请配置图片 API 后生成真实主图");
      setProductName("");
      setProductCategory("");
      setPrompt("");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "主图生成失败");
      await refreshAll();
    } finally {
      setBusy("");
    }
  };

  const rerun = async (task: ProductTask) => {
    setBusy(task.id);
    try {
      await api(`/api/product-tasks/${task.id}/generate-main-image`, { method: "POST" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "重新生成失败");
      await refreshAll();
    } finally {
      setBusy("");
    }
  };

  const deleteTask = async (task: ProductTask) => {
    const confirmed = window.confirm(`删除主图任务「${task.product_name || task.id}」？生成图片文件也会一起删除，任务日志会保留。`);
    if (!confirmed) return;
    setBusy(`delete-${task.id}`);
    try {
      await api(`/api/product-tasks/${task.id}`, { method: "DELETE" });
      setNotice("主图任务已删除");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除主图任务失败");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>一键生成主图</h2>
          <span>image.generate</span>
        </div>
        <div className="main-image-form">
          <label className="field">
            <span>商品名称</span>
            <input value={productName} onChange={(event) => setProductName(event.target.value)} placeholder="例如 便携式咖啡机" />
          </label>
          <label className="field">
            <span>商品分类</span>
            <input value={productCategory} onChange={(event) => setProductCategory(event.target.value)} placeholder="例如 小家电 / 户外用品" />
          </label>
          <label className="field">
            <span>主图比例</span>
            <select value={ratio} onChange={(event) => setRatio(event.target.value)}>
              <option value="1:1">1:1</option>
              <option value="4:3">4:3</option>
              <option value="3:4">3:4</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <label className="field main-image-prompt">
            <span>生成提示词</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="例如 白底电商主图，突出产品质感，柔和自然阴影，适合跨境平台展示"
            />
          </label>
          <button className="button primary fit" onClick={generate} disabled={busy === "main-image-generate"}>
            {busy === "main-image-generate" ? <Loader2 className="spin" size={16} /> : <ImageIcon size={16} />}
            一键生成主图
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>主图任务</h2>
          <span>{tasks.length}</span>
        </div>
        {tasks.length ? (
          <div className="product-task-grid">
            {tasks.map((task) => (
              <article className="product-task-card" key={task.id}>
                <div className="product-image-preview">
                  {task.main_image_url ? (
                    <img src={`${API_BASE}${task.main_image_url}`} alt={task.product_name || "主图"} />
                  ) : (
                    <ImageIcon size={42} />
                  )}
                </div>
                <div className="product-task-body">
                  <div className="tool-card-head">
                    <div>
                      <strong>{task.product_name || "-"}</strong>
                      <span>{task.product_category || "未填写分类"}</span>
                    </div>
                    <StatusBadge status={task.main_image_status || "unknown"} />
                  </div>
                  <p>{task.prompt || "未填写额外提示词"}</p>
                  <div className="tool-meta">
                    <span>{task.main_image_ratio || "1:1"}</span>
                    <span>{formatTime(task.updated_at)}</span>
                    <span>{shortId(task.id)}</span>
                  </div>
                  {task.error_message ? <p className="error-text">{task.error_message}</p> : null}
                  <div className="action-row">
                    <button className="button secondary fit" onClick={() => rerun(task)} disabled={busy === task.id || busy === `delete-${task.id}`}>
                      {busy === task.id ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                      重新生成
                    </button>
                    <button className="button danger fit" onClick={() => deleteTask(task)} disabled={busy === task.id || busy === `delete-${task.id}`}>
                      {busy === `delete-${task.id}` ? <Loader2 className="spin" size={16} /> : <Trash2 size={16} />}
                      删除
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyLine text="暂无主图任务" />
        )}
      </section>
    </div>
  );
}

function ConfigViewV2({ modules, setNotice, refreshAll }: { modules: Module[]; setNotice: (value: string) => void; refreshAll: () => Promise<void> }) {
  const configurable = modules.filter((module) => Object.keys(module.manifest.configSchema ?? {}).length > 0);
  const [selectedId, setSelectedId] = useState(configurable[0]?.id ?? "");
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const selectedModule = modules.find((module) => module.id === selectedId);
  const isImageGenerator = selectedId === "image-generator";
  const effectiveSchema = useMemo(() => {
    if (!config) return {};
    if (!isImageGenerator) return config.schema;
    return {
      ...config.schema,
      authMode: config.schema.authMode ?? "optional",
      providerMode: config.schema.providerMode ?? "optional"
    };
  }, [config, isImageGenerator]);

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

  const saveConfig = async (enableAfterSave = false) => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const payload = await api<ConfigPayload>(`/api/modules/${selectedId}/config`, {
        method: "PUT",
        body: JSON.stringify({ values })
      });
      setConfig(payload);
      setValues(payload.values);
      if (enableAfterSave) {
        await api(`/api/modules/${selectedId}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled: true })
        });
      }
      setNotice(enableAfterSave ? "配置已保存，模块已启用" : "配置已保存");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存配置失败");
    } finally {
      setSaving(false);
    }
  };

  const applyImagePreset = (preset: "chat" | "images") => {
    const nextValues =
      preset === "chat"
        ? {
            baseUrl: "https://ai.t8star.org/v1/chat/completions",
            model: "gpt-4o-image",
            authMode: "bearer",
            providerMode: "chat"
          }
        : {
            baseUrl: "https://ai.t8star.cn/v1",
            model: "gpt-image-2",
            authMode: "raw",
            providerMode: "images"
          };
    setValues((current) => ({ ...current, ...nextValues }));
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
        <div className="stack">
          {isImageGenerator ? (
            <div className="config-helper">
              <div>
                <strong>图片生成接口</strong>
                <span>选择预设后会自动填好 URL、模型、鉴权方式和接口类型。API Key 不会被覆盖。</span>
              </div>
              <div className="action-row">
                <button className="button secondary" type="button" onClick={() => applyImagePreset("chat")}>
                  Chat 图片接口
                </button>
                <button className="button secondary" type="button" onClick={() => applyImagePreset("images")}>
                  Images 接口
                </button>
              </div>
              <div className="config-preset-grid">
                <div>
                  <span>当前模块</span>
                  <strong>{selectedModule?.enabled ? "已启用" : "未启用"}</strong>
                </div>
                <div>
                  <span>推荐配置</span>
                  <strong>chat / bearer / gpt-4o-image</strong>
                </div>
              </div>
            </div>
          ) : null}

          <div className="form-grid">
            {Object.entries(effectiveSchema).map(([key, type]) => (
              <ConfigFieldV2
                key={key}
                name={key}
                type={type}
                value={values[key] ?? ""}
                imageMode={isImageGenerator}
                onChange={(value) => setValues((current) => ({ ...current, [key]: value }))}
              />
            ))}
            <div className="action-row">
              <button className="button primary fit" onClick={() => saveConfig(false)} disabled={saving}>
                {saving ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
                保存配置
              </button>
              {isImageGenerator ? (
                <button className="button secondary fit" onClick={() => saveConfig(true)} disabled={saving}>
                  {saving ? <Loader2 className="spin" size={16} /> : <Power size={16} />}
                  保存并启用
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : (
        <EmptyLine text="暂无可配置模块" />
      )}
    </section>
  );
}

function ConfigFieldV2({
  name,
  type,
  value,
  imageMode,
  onChange
}: {
  name: string;
  type: string;
  value: string;
  imageMode: boolean;
  onChange: (value: string) => void;
}) {
  if (imageMode && name === "authMode") {
    return (
      <label className="field">
        <span>
          authMode
          <em>鉴权方式</em>
        </span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">自动判断</option>
          <option value="bearer">Bearer Token</option>
          <option value="raw">Raw Authorization</option>
        </select>
      </label>
    );
  }

  if (imageMode && name === "providerMode") {
    return (
      <label className="field">
        <span>
          providerMode
          <em>接口类型</em>
        </span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">自动判断</option>
          <option value="chat">Chat 图片接口</option>
          <option value="images">Images 接口</option>
        </select>
      </label>
    );
  }

  return (
    <label className="field">
      <span>
        {name}
        <em>{type}</em>
      </span>
      <input type={type === "secret" ? "password" : "text"} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
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

const workflowStepTemplates: Record<string, WorkflowStepTemplate[]> = {
  "lead-import-to-feishu": [
    { id: "file-upload", label: "文件上传", module_id: "local-file-store", capability: "file.upload" },
    { id: "lead-normalize", label: "线索清洗", module_id: "lead-cleaner", capability: "lead.normalize" },
    { id: "customer-merge", label: "客户归并", module_id: "customer-merge", capability: "customer.merge" },
    { id: "lead-table-write", label: "写入线索明细表", module_id: "feishu-sync", capability: "table.write", target: "线索" },
    { id: "customer-table-write", label: "写入客户表", module_id: "feishu-sync", capability: "table.write", target: "客户" },
    { id: "message-notify", label: "异常通知", module_id: "message-notifier", capability: "message.send", optional: true }
  ],
  "product-main-image": [
    { id: "image-generate", label: "生成主图", module_id: "image-generator", capability: "image.generate" },
    { id: "asset-save", label: "保存生成资产", module_id: "image-generator", capability: "file.upload", optional: true }
  ]
};

function RunsView({ runs, logs }: { runs: WorkflowRun[]; logs: TaskLog[] }) {
  const [selectedRunId, setSelectedRunId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? runs[0];
  const nodes = selectedRun ? buildWorkflowNodes(selectedRun, logs) : [];
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0];

  useEffect(() => {
    if (!selectedRunId && runs[0]?.id) {
      setSelectedRunId(runs[0].id);
    }
  }, [runs, selectedRunId]);

  useEffect(() => {
    if (nodes[0]?.id && !nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [nodes, selectedNodeId]);

  return (
    <div className="stack">
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
                <tr className={selectedRun?.id === run.id ? "selected-row" : ""} key={run.id} onClick={() => setSelectedRunId(run.id)}>
                  <td>{shortId(run.id)}</td>
                  <td>{workflowTitle(run.workflow_id)}</td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{formatTime(run.started_at)}</td>
                  <td>{run.duration_ms ?? 0} ms</td>
                  <td className="summary-cell">{compactSummary(run.output_summary || run.error_message || "-")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selectedRun ? (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>执行过程</h2>
              <span>{shortId(selectedRun.id)} · {workflowTitle(selectedRun.workflow_id)}</span>
            </div>
            <StatusBadge status={selectedRun.status} />
          </div>

          <div className="run-summary-grid">
            <div>
              <span>开始时间</span>
              <strong>{formatTime(selectedRun.started_at)}</strong>
            </div>
            <div>
              <span>结束时间</span>
              <strong>{formatTime(selectedRun.ended_at)}</strong>
            </div>
            <div>
              <span>总耗时</span>
              <strong>{selectedRun.duration_ms ?? 0} ms</strong>
            </div>
            <div>
              <span>节点数</span>
              <strong>{nodes.filter((node) => node.status !== "not_run").length} / {nodes.length}</strong>
            </div>
          </div>

          <div className="workflow-run-layout">
            <div className="workflow-node-list">
              {nodes.length ? (
                nodes.map((node, index) => (
                  <button
                    className={
                      selectedNode?.id === node.id
                        ? `workflow-node selected ${node.status.replace(/_/g, "-")}`
                        : `workflow-node ${node.status.replace(/_/g, "-")}`
                    }
                    key={node.id}
                    onClick={() => setSelectedNodeId(node.id)}
                  >
                    <span className="node-index">{index + 1}</span>
                    <span className="node-main">
                      <strong>{node.label}</strong>
                      <em>{node.module_id || "-"} · {node.capability || "-"}</em>
                    </span>
                    <StatusBadge status={node.status} />
                  </button>
                ))
              ) : (
                <EmptyLine text="这次运行还没有节点日志" />
              )}
            </div>

            <div className="workflow-node-detail">
              {selectedNode ? (
                <>
                  <div className="node-detail-head">
                    <div>
                      <h3>{selectedNode.label}</h3>
                      <span>{selectedNode.task_id ? shortId(selectedNode.task_id) : selectedNode.id}</span>
                    </div>
                    <StatusBadge status={selectedNode.status} />
                  </div>
                  <div className="node-detail-grid">
                    <DetailItem label="模块" value={selectedNode.module_id || "-"} />
                    <DetailItem label="能力" value={selectedNode.capability || "-"} />
                    <DetailItem label="耗时" value={`${selectedNode.duration_ms ?? 0} ms`} />
                    <DetailItem label="重试" value={`${selectedNode.retry_count}`} />
                    <DetailItem label="开始" value={formatTime(selectedNode.started_at)} />
                    <DetailItem label="结束" value={formatTime(selectedNode.ended_at)} />
                  </div>
                  {selectedNode.error_message ? (
                    <div className="node-error">
                      <AlertTriangle size={16} />
                      <span>{selectedNode.error_message}</span>
                    </div>
                  ) : null}
                  <div className="node-summary-grid">
                    <div>
                      <strong>输入摘要</strong>
                      <pre>{formatSummaryBlock(selectedNode.input_summary)}</pre>
                    </div>
                    <div>
                      <strong>输出摘要</strong>
                      <pre>{formatSummaryBlock(selectedNode.output_summary)}</pre>
                    </div>
                  </div>
                </>
              ) : (
                <EmptyLine text="请选择一个节点" />
              )}
            </div>
          </div>
        </section>
      ) : (
        <section className="panel">
          <EmptyLine text="暂无工作流运行记录" />
        </section>
      )}
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
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
  bases,
  tables,
  listeners,
  runs,
  setNotice,
  setBusy,
  busy,
  refreshAll
}: {
  bases: FeishuBase[];
  tables: FeishuTableConfig[];
  listeners: IntakeListener[];
  runs: IntakeRun[];
  setNotice: (value: string) => void;
  setBusy: (value: string) => void;
  busy: string;
  refreshAll: () => Promise<void>;
}) {
  const [baseName, setBaseName] = useState("");
  const [baseToken, setBaseToken] = useState("");
  const [baseDescription, setBaseDescription] = useState("");
  const [tableBaseId, setTableBaseId] = useState("");
  const [tableName, setTableName] = useState("");
  const [tableId, setTableId] = useState("");
  const [tablePurpose, setTablePurpose] = useState("csv_intake");
  const [listenerName, setListenerName] = useState("");
  const [listenerTableConfigId, setListenerTableConfigId] = useState("");
  const [listenerInterval, setListenerInterval] = useState(60);
  const [statusField, setStatusField] = useState("处理状态");
  const [fileField, setFileField] = useState("CSV 文件");
  const [submitterField, setSubmitterField] = useState("提交人");
  const [noteField, setNoteField] = useState("提交说明");
  const [pendingValue, setPendingValue] = useState("待处理");

  useEffect(() => {
    if (!tableBaseId && bases[0]?.id) {
      setTableBaseId(bases[0].id);
    }
  }, [bases, tableBaseId]);

  useEffect(() => {
    if (!listenerTableConfigId && tables[0]?.id) {
      setListenerTableConfigId(tables[0].id);
    }
  }, [tables, listenerTableConfigId]);

  const createBase = async () => {
    if (!baseName.trim() || !baseToken.trim()) {
      setNotice("请填写 Base 名称和 appToken");
      return;
    }
    setBusy("feishu-base-create");
    try {
      await api<FeishuBase>("/api/feishu/bases", {
        method: "POST",
        body: JSON.stringify({
          name: baseName,
          app_token: baseToken,
          description: baseDescription,
          enabled: true
        })
      });
      setBaseName("");
      setBaseToken("");
      setBaseDescription("");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "新增飞书 Base 失败");
    } finally {
      setBusy("");
    }
  };

  const deleteBase = async (base: FeishuBase) => {
    setBusy(base.id);
    try {
      await api(`/api/feishu/bases/${base.id}`, { method: "DELETE" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除飞书 Base 失败");
    } finally {
      setBusy("");
    }
  };

  const createTable = async () => {
    if (!tableBaseId || !tableName.trim() || !tableId.trim()) {
      setNotice("请填写 Base、表名和 tableId");
      return;
    }
    setBusy("feishu-table-create");
    try {
      await api<FeishuTableConfig>("/api/feishu/tables", {
        method: "POST",
        body: JSON.stringify({
          base_id: tableBaseId,
          name: tableName,
          table_id: tableId,
          purpose: tablePurpose
        })
      });
      setTableName("");
      setTableId("");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "新增飞书表失败");
    } finally {
      setBusy("");
    }
  };

  const deleteTable = async (table: FeishuTableConfig) => {
    setBusy(table.id);
    try {
      await api(`/api/feishu/tables/${table.id}`, { method: "DELETE" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除飞书表失败");
    } finally {
      setBusy("");
    }
  };

  const createListener = async () => {
    const table = tables.find((item) => item.id === listenerTableConfigId);
    if (!table) {
      setNotice("请先选择一个飞书任务表");
      return;
    }
    setBusy("intake-listener-create");
    try {
      await api<IntakeListener>("/api/intake/listeners", {
        method: "POST",
        body: JSON.stringify({
          name: listenerName || `${table.name} 监听`,
          base_id: table.base_id,
          table_config_id: table.id,
          workflow_id: "lead-import-to-feishu",
          enabled: false,
          interval_seconds: listenerInterval,
          status_field: statusField,
          file_field: fileField,
          submitter_field: submitterField,
          note_field: noteField,
          result_field: "处理结果",
          run_id_field: "工作流ID",
          error_field: "错误信息",
          processed_at_field: "处理时间",
          pending_value: pendingValue,
          processing_value: "处理中",
          success_value: "处理成功",
          partial_value: "部分成功",
          failed_value: "处理失败"
        })
      });
      setListenerName("");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "新增监听器失败");
    } finally {
      setBusy("");
    }
  };

  const patchListener = async (listener: IntakeListener, payload: Partial<IntakeListener>) => {
    setBusy(listener.id);
    try {
      await api<IntakeListener>(`/api/intake/listeners/${listener.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "更新监听器失败");
    } finally {
      setBusy("");
    }
  };

  const scanListener = async (listener: IntakeListener) => {
    setBusy(`scan-${listener.id}`);
    try {
      await api<Record<string, unknown>>(`/api/intake/listeners/${listener.id}/scan`, { method: "POST" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "扫描失败");
    } finally {
      setBusy("");
    }
  };

  const scanAll = async () => {
    setBusy("intake-scan-all");
    try {
      await api<Record<string, unknown>>("/api/intake/scan", { method: "POST" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "扫描失败");
    } finally {
      setBusy("");
    }
  };

  const deleteListener = async (listener: IntakeListener) => {
    setBusy(listener.id);
    try {
      await api(`/api/intake/listeners/${listener.id}`, { method: "DELETE" });
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除监听器失败");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>飞书监听总览</h2>
          <div className="action-row">
            <button className="button secondary" onClick={scanAll} disabled={busy === "intake-scan-all"}>
              {busy === "intake-scan-all" ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
              扫描全部
            </button>
          </div>
        </div>
        <div className="helper-block">
          <strong>当前采用轮询模式</strong>
          <span>一个飞书机器人凭证可以对应多个 Base；每个 Base 下可以登记多张表；每个监听器绑定一张任务表，打开后按间隔扫描“待处理”记录。</span>
          <span>建议把“CSV 提交任务表”单独做入口表，处理完成后由平台写入线索明细表和客户表。</span>
        </div>
      </section>

      <section className="split-grid">
        <div className="panel">
          <div className="panel-head">
            <h2>飞书 Base</h2>
            <span>{bases.length}</span>
          </div>
          <div className="form-grid single dense-form">
            <label className="field">
              <span>Base 名称</span>
              <input value={baseName} onChange={(event) => setBaseName(event.target.value)} placeholder="例如 销售线索 Base" />
            </label>
            <label className="field">
              <span>appToken</span>
              <input value={baseToken} onChange={(event) => setBaseToken(event.target.value)} placeholder="多维表格 URL 中 /base/ 后面的 token" />
            </label>
            <label className="field">
              <span>说明</span>
              <input value={baseDescription} onChange={(event) => setBaseDescription(event.target.value)} placeholder="可选" />
            </label>
            <button className="button primary fit" onClick={createBase} disabled={busy === "feishu-base-create"}>
              {busy === "feishu-base-create" ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
              新增 Base
            </button>
          </div>
          <div className="list-block">
            {bases.length ? (
              bases.map((base) => (
                <div className="list-row" key={base.id}>
                  <span>
                    <strong>{base.name}</strong>
                    <span className="muted block">{shortToken(base.app_token)}</span>
                  </span>
                  <div className="action-row">
                    <StatusBadge status={base.enabled ? "healthy" : "disabled"} />
                    <button className="icon-button" onClick={() => deleteBase(base)} disabled={busy === base.id} title="删除 Base">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <EmptyLine text="暂无飞书 Base" />
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <h2>飞书表配置</h2>
            <span>{tables.length}</span>
          </div>
          <div className="form-grid single dense-form">
            <label className="field">
              <span>所属 Base</span>
              <select value={tableBaseId} onChange={(event) => setTableBaseId(event.target.value)}>
                {bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>表名</span>
              <input value={tableName} onChange={(event) => setTableName(event.target.value)} placeholder="例如 CSV 提交任务表" />
            </label>
            <label className="field">
              <span>tableId</span>
              <input value={tableId} onChange={(event) => setTableId(event.target.value)} placeholder="URL 里的 table=tbxxxx" />
            </label>
            <label className="field">
              <span>用途</span>
              <select value={tablePurpose} onChange={(event) => setTablePurpose(event.target.value)}>
                <option value="csv_intake">CSV 提交任务表</option>
                <option value="lead_detail">线索明细表</option>
                <option value="customer">客户表</option>
                <option value="product_task">商品任务表</option>
                <option value="custom">其他</option>
              </select>
            </label>
            <button className="button primary fit" onClick={createTable} disabled={busy === "feishu-table-create" || !bases.length}>
              {busy === "feishu-table-create" ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
              新增表
            </button>
          </div>
          <div className="list-block">
            {tables.length ? (
              tables.map((table) => (
                <div className="list-row" key={table.id}>
                  <span>
                    <strong>{table.name}</strong>
                    <span className="muted block">{table.base_name || table.base_id} · {table.purpose || "未分类"} · {shortToken(table.table_id)}</span>
                  </span>
                  <button className="icon-button" onClick={() => deleteTable(table)} disabled={busy === table.id} title="删除表配置">
                    <Trash2 size={15} />
                  </button>
                </div>
              ))
            ) : (
              <EmptyLine text="暂无飞书表配置" />
            )}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>监听器</h2>
          <span>{listeners.length}</span>
        </div>
        <div className="listener-create-grid">
          <label className="field">
            <span>监听器名称</span>
            <input value={listenerName} onChange={(event) => setListenerName(event.target.value)} placeholder="例如 销售 CSV 入口监听" />
          </label>
          <label className="field">
            <span>任务表</span>
            <select value={listenerTableConfigId} onChange={(event) => setListenerTableConfigId(event.target.value)}>
              {tables.map((table) => (
                <option key={table.id} value={table.id}>
                  {table.name} / {table.base_name || table.base_id}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>间隔秒数</span>
            <input type="number" min={30} max={3600} value={listenerInterval} onChange={(event) => setListenerInterval(Number(event.target.value))} />
          </label>
          <label className="field">
            <span>状态字段</span>
            <input value={statusField} onChange={(event) => setStatusField(event.target.value)} />
          </label>
          <label className="field">
            <span>文件字段</span>
            <input value={fileField} onChange={(event) => setFileField(event.target.value)} />
          </label>
          <label className="field">
            <span>提交人字段</span>
            <input value={submitterField} onChange={(event) => setSubmitterField(event.target.value)} />
          </label>
          <label className="field">
            <span>说明字段</span>
            <input value={noteField} onChange={(event) => setNoteField(event.target.value)} />
          </label>
          <label className="field">
            <span>待处理值</span>
            <input value={pendingValue} onChange={(event) => setPendingValue(event.target.value)} />
          </label>
          <button className="button primary fit" onClick={createListener} disabled={busy === "intake-listener-create" || !tables.length}>
            {busy === "intake-listener-create" ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
            新增监听器
          </button>
        </div>

        <div className="listener-card-grid">
          {listeners.length ? (
            listeners.map((listener) => (
              <article className="listener-card" key={listener.id}>
                <div className="tool-card-head">
                  <div>
                    <strong>{listener.name}</strong>
                    <span>{listener.base_name || "-"} / {listener.table_name || "未绑定表"}</span>
                  </div>
                  <StatusBadge status={listener.enabled ? listener.status : "disabled"} />
                </div>
                <div className="tool-meta">
                  <span>{listener.workflow_id}</span>
                  <span>{listener.interval_seconds}s</span>
                  <span>{listener.pending_value}</span>
                </div>
                <div className="listener-meta compact">
                  <span>上次：{formatTime(listener.last_scan_at)}</span>
                  <span>下次：{formatTime(listener.next_scan_at)}</span>
                  <span>错误：{listener.last_error || "-"}</span>
                </div>
                <div className="action-row">
                  <button
                    className={listener.enabled ? "button danger" : "button primary"}
                    onClick={() => patchListener(listener, { enabled: !listener.enabled })}
                    disabled={busy === listener.id}
                  >
                    {listener.enabled ? <PowerOff size={16} /> : <Power size={16} />}
                    {listener.enabled ? "关闭" : "打开"}
                  </button>
                  <button className="button secondary" onClick={() => scanListener(listener)} disabled={busy === `scan-${listener.id}`}>
                    {busy === `scan-${listener.id}` ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                    扫描
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => deleteListener(listener)}
                    disabled={busy === listener.id || listener.id === "feishu-form-csv"}
                    title={listener.id === "feishu-form-csv" ? "默认监听器不能删除" : "删除监听器"}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </article>
            ))
          ) : (
            <EmptyLine text="暂无监听器" />
          )}
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
                <th>监听器</th>
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
                  <td>{run.listener_name || run.listener_id}</td>
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

function buildWorkflowNodes(run: WorkflowRun, logs: TaskLog[]): WorkflowNodeView[] {
  const runLogs = logs
    .filter((log) => log.workflow_run_id === run.id)
    .sort((left, right) => left.id - right.id);
  const template = workflowStepTemplates[run.workflow_id];
  if (!template) {
    return runLogs.map((log) => taskLogToNode(log));
  }

  const usedLogIndexes = new Set<number>();
  const templateNodes = template.map((step) => {
    const logIndex = runLogs.findIndex((log, index) => !usedLogIndexes.has(index) && matchesWorkflowStep(log, step));
    if (logIndex >= 0) {
      usedLogIndexes.add(logIndex);
      return taskLogToNode(runLogs[logIndex], step);
    }
    return emptyWorkflowNode(step);
  });

  const extraNodes = runLogs
    .filter((_, index) => !usedLogIndexes.has(index))
    .map((log) => taskLogToNode(log));
  return [...templateNodes, ...extraNodes];
}

function matchesWorkflowStep(log: TaskLog, step: WorkflowStepTemplate) {
  if (step.module_id && log.module_id !== step.module_id) return false;
  if (step.capability && log.capability !== step.capability) return false;
  if (step.target && !summaryText(log).includes(step.target)) return false;
  return true;
}

function taskLogToNode(log: TaskLog, step?: WorkflowStepTemplate): WorkflowNodeView {
  return {
    id: step ? step.id : `log-${log.id}`,
    label: step?.label ?? nodeLabelForLog(log),
    status: log.status,
    module_id: log.module_id,
    capability: log.capability,
    started_at: log.started_at,
    ended_at: log.ended_at,
    duration_ms: log.duration_ms,
    input_summary: log.input_summary,
    output_summary: log.output_summary,
    error_message: log.error_message,
    retry_count: log.retry_count,
    task_id: log.task_id,
    log_id: log.id,
    optional: step?.optional
  };
}

function emptyWorkflowNode(step: WorkflowStepTemplate): WorkflowNodeView {
  return {
    id: step.id,
    label: step.label,
    status: "not_run",
    module_id: step.module_id ?? "",
    capability: step.capability ?? "",
    retry_count: 0,
    optional: step.optional
  };
}

function nodeLabelForLog(log: TaskLog) {
  if (log.capability === "file.upload") return "文件上传";
  if (log.capability === "lead.normalize") return "线索清洗";
  if (log.capability === "customer.merge") return "客户归并";
  if (log.capability === "table.write") {
    const text = summaryText(log);
    if (text.includes("线索")) return "写入线索明细表";
    if (text.includes("客户")) return "写入客户表";
    return "写入外部表";
  }
  if (log.capability === "message.send") return "消息通知";
  if (log.capability === "image.generate") return "生成图片";
  return log.capability || log.module_id;
}

function summaryText(log: TaskLog) {
  return `${log.input_summary ?? ""} ${log.output_summary ?? ""} ${log.error_message ?? ""}`;
}

function workflowTitle(workflowId: string) {
  const titles: Record<string, string> = {
    "lead-import-to-feishu": "CSV 线索清洗与飞书同步",
    "product-main-image": "商品主图生成"
  };
  return titles[workflowId] ?? workflowId;
}

function parseSummary(value?: string) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function compactSummary(value?: string) {
  const parsed = parseSummary(value);
  const text = typeof parsed === "string" ? parsed : JSON.stringify(parsed);
  if (!text || text === "null") return "-";
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

function formatSummaryBlock(value?: string) {
  const parsed = parseSummary(value);
  if (!parsed) return "-";
  const text = typeof parsed === "string" ? parsed : JSON.stringify(parsed, null, 2);
  return text.length > 1800 ? `${text.slice(0, 1800)}...` : text;
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
    not_run: "未执行",
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

function shortToken(value?: string) {
  if (!value) return "-";
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
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

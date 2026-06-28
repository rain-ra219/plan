"use client";

import {
  Activity,
  AlertTriangle,
  ClipboardList,
  Database,
  History,
  Image as ImageIcon,
  LayoutDashboard,
  Loader2,
  Plug,
  RefreshCw,
  Search,
  Server,
  Settings,
  Upload,
  Workflow
} from "lucide-react";
import { useEffect, useState } from "react";

import { DataView } from "./views/DataView";
import { ConfigView } from "./views/ConfigView";
import { DashboardView } from "./views/DashboardView";
import { IntakeListenerView } from "./views/IntakeListenerView";
import { LogsView } from "./views/LogsView";
import { MainImageView } from "./views/MainImageView";
import { McpView } from "./views/McpView";
import { ModulesView } from "./views/ModulesView";
import { RunsView } from "./views/RunsView";
import { UploadView } from "./views/UploadView";
import { UploadHistoryView } from "./views/UploadHistoryView";
import { XhsWeeklyReportView } from "./views/XhsWeeklyReportView";
import { api } from "./lib/api";

type ViewId = "dashboard" | "modules" | "mcp" | "mainImage" | "xhsReport" | "configs" | "upload" | "intake" | "history" | "runs" | "logs" | "data";

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
  product_name_field: string;
  product_category_field: string;
  product_image_field: string;
  prompt_field: string;
  aspect_ratio_field: string;
  reference_image_field: string;
  product_description_field: string;
  reference_style_field: string;
  final_prompt_field: string;
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

type QueueTask = {
  id: string;
  source: string;
  workflow_id: string;
  listener_id?: string | null;
  intake_run_id?: string | null;
  remote_record_id?: string | null;
  workflow_run_id?: string | null;
  status: string;
  priority: number;
  attempt_count: number;
  max_attempts: number;
  run_after?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  error_message?: string | null;
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

const navigation: Array<{ id: ViewId; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "dashboard", label: "仪表盘", icon: LayoutDashboard },
  { id: "modules", label: "功能管理", icon: Plug },
  { id: "mcp", label: "MCP 管理", icon: Server },
  { id: "mainImage", label: "主图生成", icon: ImageIcon },
  { id: "xhsReport", label: "TikHub", icon: Search },
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
  const [taskQueue, setTaskQueue] = useState<QueueTask[]>([]);
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
        taskQueueData,
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
        api<QueueTask[]>("/api/task-queue"),
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
      setTaskQueue(taskQueueData);
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
        {view === "xhsReport" && (
          <XhsWeeklyReportView
            runs={runs}
            logs={logs}
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
            bases={feishuBases}
            tables={feishuTables}
            listeners={intakeListeners}
            runs={intakeRuns}
            queue={taskQueue}
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

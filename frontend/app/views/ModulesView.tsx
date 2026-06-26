import { CheckCircle2, Power, PowerOff } from "lucide-react";
import { useMemo } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

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

export function ModulesView({
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

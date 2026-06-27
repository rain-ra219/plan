import { Loader2, Play, Power, PowerOff, RefreshCw, Server, Settings, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { EmptyLine } from "../components/EmptyLine";
import { StatusBadge } from "../components/StatusBadge";
import { formatTime, statusLabel } from "../lib/format";

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

export function McpView({
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

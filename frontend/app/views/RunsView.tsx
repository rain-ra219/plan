import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyLine } from "../components/EmptyLine";
import { StatusBadge } from "../components/StatusBadge";
import { formatTime, shortId, statusLabel, workflowTitle } from "../lib/format";

type WorkflowRun = {
  id: string;
  workflow_id: string;
  status: string;
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
  ],
  "product-main-detail": [
    { id: "product-image-describe", label: "产品图反推", module_id: "model-provider", capability: "image.describe", target: "产品图" },
    { id: "reference-style-describe", label: "参考图反推", module_id: "model-provider", capability: "image.describe", target: "参考图" },
    { id: "prompt-compose", label: "最终提示词", module_id: "model-provider", capability: "prompt.compose", target: "最终提示词" },
    { id: "image-generate", label: "生成主图", module_id: "image-generator", capability: "image.generate" },
    { id: "asset-save", label: "保存生成资产", module_id: "image-generator", capability: "file.upload", optional: true }
  ]
};

export function RunsView({ runs, logs }: { runs: WorkflowRun[]; logs: TaskLog[] }) {
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
    id: step?.id ?? `log-${log.id}`,
    label: step?.label ?? nodeLabelForLog(log),
    module_id: log.module_id,
    capability: log.capability,
    status: log.status,
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
    module_id: step.module_id ?? "",
    capability: step.capability ?? "",
    status: step.optional ? "skipped" : "not_run",
    retry_count: 0,
    optional: step.optional
  };
}

function nodeLabelForLog(log: TaskLog) {
  if (log.capability === "table.write") {
    const text = summaryText(log);
    if (text.includes("客户")) return "写入客户表";
    if (text.includes("线索")) return "写入线索明细表";
    return "写入表格";
  }
  if (log.capability === "image.describe") {
    const text = summaryText(log);
    if (text.includes("参考")) return "参考图反推";
    return "产品图反推";
  }
  return log.capability || log.module_id;
}

function summaryText(log: TaskLog) {
  return `${log.input_summary || ""} ${log.output_summary || ""}`;
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

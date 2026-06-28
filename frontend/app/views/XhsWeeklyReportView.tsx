import { FileText, Loader2, Play, RefreshCw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { EmptyLine } from "../components/EmptyLine";
import { StatusBadge } from "../components/StatusBadge";
import { formatTime, shortId } from "../lib/format";

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
  workflow_id: string;
  workflow_run_id: string;
  module_id: string;
  capability: string;
  status: string;
  duration_ms: number;
  error_message?: string;
};

type RunResult = {
  workflow_run_id: string;
  status: string;
  keyword: string;
  notes: number;
  analyzed_notes: number;
  comments: number;
};

type PromptPayload = {
  noteAnalysisSystemPrompt: string;
  reportSystemPrompt: string;
};

export function XhsWeeklyReportView({
  runs,
  logs,
  busy,
  setBusy,
  setNotice,
  refreshAll
}: {
  runs: WorkflowRun[];
  logs: TaskLog[];
  busy: string;
  setBusy: (value: string) => void;
  setNotice: (value: string) => void;
  refreshAll: () => Promise<void>;
}) {
  const [keyword, setKeyword] = useState("");
  const [maxNotes, setMaxNotes] = useState("20");
  const [sortType, setSortType] = useState("comment_descending");
  const [timeFilter, setTimeFilter] = useState("一周内");
  const [noteType, setNoteType] = useState("不限");
  const [lastResult, setLastResult] = useState<RunResult | null>(null);
  const [noteAnalysisPrompt, setNoteAnalysisPrompt] = useState("");
  const [reportPrompt, setReportPrompt] = useState("");
  const [promptSaving, setPromptSaving] = useState(false);

  const xhsRuns = useMemo(() => runs.filter((run) => run.workflow_id === "xhs-weekly-report").slice(0, 8), [runs]);

  useEffect(() => {
    api<PromptPayload>("/api/xhs/prompts")
      .then((payload) => {
        setNoteAnalysisPrompt(payload.noteAnalysisSystemPrompt ?? "");
        setReportPrompt(payload.reportSystemPrompt ?? "");
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "提示词配置加载失败"));
  }, [setNotice]);

  const savePrompts = async () => {
    setPromptSaving(true);
    try {
      await api<PromptPayload>("/api/xhs/prompts", {
        method: "PUT",
        body: JSON.stringify({
          noteAnalysisSystemPrompt: noteAnalysisPrompt,
          reportSystemPrompt: reportPrompt
        })
      });
      setNotice("TikHub 提示词已保存");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "提示词保存失败");
    } finally {
      setPromptSaving(false);
    }
  };

  const runReport = async () => {
    if (!keyword.trim()) {
      setNotice("请填写小红书搜索关键词");
      return;
    }
    setBusy("xhs-weekly-report");
    try {
      const result = await api<RunResult>("/api/xhs-weekly-report/run", {
        method: "POST",
        body: JSON.stringify({
          keyword,
          max_notes: Number(maxNotes) || 20,
          sort_type: sortType,
          time_filter: timeFilter,
          note_type: noteType
        })
      });
      setLastResult(result);
      setNotice(result.status === "success" ? "TikHub 周报已生成" : "TikHub 周报部分完成，请查看任务日志");
      await refreshAll();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "TikHub 周报生成失败");
      await refreshAll();
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-head">
          <h2>TikHub</h2>
          <span>xhs.search + xhs.comments + report.generate</span>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>搜索关键词</span>
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="例如 洗头 / 防脱洗发水 / 头皮护理" />
          </label>
          <label className="field">
            <span>笔记数量</span>
            <input min={1} max={50} type="number" value={maxNotes} onChange={(event) => setMaxNotes(event.target.value)} />
          </label>
          <label className="field">
            <span>时间范围</span>
            <select value={timeFilter} onChange={(event) => setTimeFilter(event.target.value)}>
              <option value="一天内">一天内</option>
              <option value="一周内">一周内</option>
              <option value="半年内">半年内</option>
              <option value="不限">不限</option>
            </select>
          </label>
          <label className="field">
            <span>排序方式</span>
            <select value={sortType} onChange={(event) => setSortType(event.target.value)}>
              <option value="comment_descending">评论最多</option>
              <option value="popularity_descending">点赞最多</option>
              <option value="time_descending">最新发布</option>
              <option value="collect_descending">收藏最多</option>
              <option value="general">综合排序</option>
            </select>
          </label>
          <label className="field">
            <span>笔记类型</span>
            <select value={noteType} onChange={(event) => setNoteType(event.target.value)}>
              <option value="不限">不限</option>
              <option value="普通笔记">普通笔记</option>
              <option value="视频笔记">视频笔记</option>
              <option value="直播笔记">直播笔记</option>
            </select>
          </label>
          <div className="action-row">
            <button className="button primary fit" onClick={runReport} disabled={busy === "xhs-weekly-report"}>
              {busy === "xhs-weekly-report" ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
              生成周报
            </button>
            <button className="button secondary fit" onClick={refreshAll} disabled={busy === "xhs-weekly-report"}>
              <RefreshCw size={16} />
              刷新结果
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>提示词配置</h2>
          <span>保存后对周报和单条链接分析生效</span>
        </div>
        <div className="form-grid">
          <label className="field prompt-field">
            <span>单篇/单条评论分析 system prompt</span>
            <textarea value={noteAnalysisPrompt} onChange={(event) => setNoteAnalysisPrompt(event.target.value)} />
          </label>
          <label className="field prompt-field">
            <span>周报汇总 system prompt</span>
            <textarea value={reportPrompt} onChange={(event) => setReportPrompt(event.target.value)} />
          </label>
          <div className="action-row">
            <button className="button primary fit" onClick={savePrompts} disabled={promptSaving}>
              {promptSaving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
              保存提示词
            </button>
          </div>
        </div>
      </section>

      {lastResult ? (
        <section className="panel">
          <div className="panel-head">
            <h2>本次结果</h2>
            <StatusBadge status={lastResult.status} />
          </div>
          <div className="metric-grid">
            <Metric label="关键词" value={lastResult.keyword} />
            <Metric label="笔记" value={lastResult.notes} />
            <Metric label="已分析" value={lastResult.analyzed_notes} />
            <Metric label="评论" value={lastResult.comments} />
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="panel-head">
          <h2>最近运行</h2>
          <span>{xhsRuns.length}</span>
        </div>
        {xhsRuns.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>运行ID</th>
                  <th>状态</th>
                  <th>关键词</th>
                  <th>笔记/评论</th>
                  <th>开始时间</th>
                  <th>耗时</th>
                  <th>错误</th>
                </tr>
              </thead>
              <tbody>
                {xhsRuns.map((run) => {
                  const input = parseJson(run.input_summary);
                  const output = parseJson(run.output_summary);
                  return (
                    <tr key={run.id}>
                      <td>{shortId(run.id)}</td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td>{input.keyword ?? output.keyword ?? "-"}</td>
                      <td>
                        {output.notes ?? 0} / {output.comments ?? 0}
                      </td>
                      <td>{formatTime(run.started_at)}</td>
                      <td>{run.duration_ms ?? 0} ms</td>
                      <td>{run.error_message || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyLine text="暂无 TikHub 运行记录" />
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>最近步骤</h2>
          <FileText size={18} />
        </div>
        {logs.filter((log) => log.workflow_id === "xhs-weekly-report").slice(0, 8).length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>能力</th>
                  <th>模块</th>
                  <th>状态</th>
                  <th>耗时</th>
                  <th>错误</th>
                </tr>
              </thead>
              <tbody>
                {logs
                  .filter((log) => log.workflow_id === "xhs-weekly-report")
                  .slice(0, 8)
                  .map((log) => (
                    <tr key={log.id}>
                      <td>{log.capability}</td>
                      <td>{log.module_id}</td>
                      <td>
                        <StatusBadge status={log.status} />
                      </td>
                      <td>{log.duration_ms} ms</td>
                      <td>{log.error_message || "-"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyLine text="暂无 TikHub 步骤日志" />
        )}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function parseJson(value?: string): Record<string, string | number | boolean | null> {
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

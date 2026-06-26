import { Loader2, Play } from "lucide-react";
import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export function UploadView({
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

function StatusBadge({ status }: { status: string }) {
  const normalized = status || "unknown";
  return <span className={`status ${normalized.replace(/_/g, "-")}`}>{statusLabel(normalized)}</span>;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    ready: "就绪",
    waiting: "等待",
    running: "运行中"
  };
  return labels[status] ?? status;
}

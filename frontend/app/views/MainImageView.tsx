import { Image as ImageIcon, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { API_BASE, api } from "../lib/api";
import { EmptyLine } from "../components/EmptyLine";
import { StatusBadge } from "../components/StatusBadge";
import { formatTime, shortId } from "../lib/format";

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

export function MainImageView({
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

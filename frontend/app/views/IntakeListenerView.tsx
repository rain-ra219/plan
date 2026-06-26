import { Loader2, Power, PowerOff, RefreshCw, Settings, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

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

export function IntakeListenerView({
  bases,
  tables,
  listeners,
  runs,
  queue,
  setNotice,
  setBusy,
  busy,
  refreshAll
}: {
  bases: FeishuBase[];
  tables: FeishuTableConfig[];
  listeners: IntakeListener[];
  runs: IntakeRun[];
  queue: QueueTask[];
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
  const [listenerWorkflowId, setListenerWorkflowId] = useState("lead-import-to-feishu");
  const [listenerInterval, setListenerInterval] = useState(60);
  const [statusField, setStatusField] = useState("处理状态");
  const [fileField, setFileField] = useState("CSV 文件");
  const [submitterField, setSubmitterField] = useState("提交人");
  const [noteField, setNoteField] = useState("提交说明");
  const [productNameField, setProductNameField] = useState("商品名称");
  const [productCategoryField, setProductCategoryField] = useState("商品分类");
  const [productImageField, setProductImageField] = useState("产品图");
  const [promptField, setPromptField] = useState("图片提示词");
  const [aspectRatioField, setAspectRatioField] = useState("生成比例");
  const [referenceImageField, setReferenceImageField] = useState("参考图片");
  const [productDescriptionField, setProductDescriptionField] = useState("产品图描述");
  const [referenceStyleField, setReferenceStyleField] = useState("参考图风格描述");
  const [finalPromptField, setFinalPromptField] = useState("最终提示词");
  const [resultField, setResultField] = useState("处理结果");
  const [runIdField, setRunIdField] = useState("工作流ID");
  const [errorField, setErrorField] = useState("错误信息");
  const [processedAtField, setProcessedAtField] = useState("处理时间");
  const [pendingValue, setPendingValue] = useState("待处理");
  const [processingValue, setProcessingValue] = useState("处理中");
  const [successValue, setSuccessValue] = useState("处理成功");
  const [partialValue, setPartialValue] = useState("部分成功");
  const [failedValue, setFailedValue] = useState("处理失败");

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

  useEffect(() => {
    if (listenerWorkflowId === "product-main-detail") {
      setProductNameField((value) => (value === "图片编号" || value === "商品名称" ? "商品名称" : value));
      setProductCategoryField((value) => (value === "商品分类" || value === "任务类型" ? "任务类型" : value));
      setProductImageField((value) => (value === "产品图" ? "产品图" : value));
      setPromptField((value) => (value === "图片提示词" || value === "主图提示词" ? "主图提示词" : value));
      setAspectRatioField((value) => (value === "生成比例" || value === "主图比例" ? "主图比例" : value));
      setReferenceImageField((value) => (value === "参考图片" || value === "参考图" ? "参考图" : value));
      setProductDescriptionField((value) => value || "产品图描述");
      setReferenceStyleField((value) => value || "参考图风格描述");
      setFinalPromptField((value) => value || "最终提示词");
      setResultField((value) => (value === "处理结果" || value === "生成结果" || value === "主图结果" ? "主图结果" : value));
      setPendingValue((value) => value || "待处理");
      setProcessingValue((value) => (value === "处理中" ? "生成中" : value));
      setSuccessValue((value) => (value === "处理成功" ? "已完成" : value));
      setPartialValue((value) => (value === "部分成功" ? "部分完成" : value));
      setFailedValue((value) => (value === "处理失败" ? "失败" : value));
    } else if (listenerWorkflowId === "product-main-image") {
      setResultField((value) => (value === "处理结果" ? "生成结果" : value));
      setPendingValue((value) => value || "待处理");
      setProcessingValue((value) => (value === "处理中" ? "生成中" : value));
      setSuccessValue((value) => (value === "处理成功" ? "已完成" : value));
      setPartialValue((value) => (value === "部分成功" ? "部分完成" : value));
      setFailedValue((value) => (value === "处理失败" ? "失败" : value));
    } else {
      setResultField((value) => (value === "生成结果" || value === "主图结果" ? "处理结果" : value));
      setPromptField((value) => (value === "主图提示词" ? "图片提示词" : value));
      setAspectRatioField((value) => (value === "主图比例" ? "生成比例" : value));
      setReferenceImageField((value) => (value === "参考图" ? "参考图片" : value));
      setPendingValue((value) => value || "待处理");
      setProcessingValue((value) => (value === "生成中" ? "处理中" : value));
      setSuccessValue((value) => (value === "已完成" ? "处理成功" : value));
      setPartialValue((value) => (value === "部分完成" ? "部分成功" : value));
      setFailedValue((value) => (value === "失败" ? "处理失败" : value));
    }
  }, [listenerWorkflowId]);

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
          workflow_id: listenerWorkflowId,
          enabled: false,
          interval_seconds: listenerInterval,
          status_field: statusField,
          file_field: fileField,
          submitter_field: submitterField,
          note_field: noteField,
          product_name_field: productNameField,
          product_category_field: productCategoryField,
          product_image_field: productImageField,
          prompt_field: promptField,
          aspect_ratio_field: aspectRatioField,
          reference_image_field: referenceImageField,
          product_description_field: productDescriptionField,
          reference_style_field: referenceStyleField,
          final_prompt_field: finalPromptField,
          result_field: resultField,
          run_id_field: runIdField,
          error_field: errorField,
          processed_at_field: processedAtField,
          pending_value: pendingValue,
          processing_value: processingValue,
          success_value: successValue,
          partial_value: partialValue,
          failed_value: failedValue
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
                <option value="product_task">图片生成任务表</option>
                <option value="product_detail_task">主图详情页生成表</option>
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
            <span>监听类型</span>
            <select value={listenerWorkflowId} onChange={(event) => setListenerWorkflowId(event.target.value)}>
              <option value="lead-import-to-feishu">CSV 线索导入</option>
              <option value="product-main-image">图片生成</option>
              <option value="product-main-detail">主图详情页生成</option>
            </select>
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
          {listenerWorkflowId === "lead-import-to-feishu" ? (
            <>
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
            </>
          ) : (
            <>
              <label className="field">
                <span>商品名称字段</span>
                <input value={productNameField} onChange={(event) => setProductNameField(event.target.value)} />
              </label>
              <label className="field">
                <span>商品分类字段</span>
                <input value={productCategoryField} onChange={(event) => setProductCategoryField(event.target.value)} />
              </label>
              {listenerWorkflowId === "product-main-detail" ? (
                <label className="field">
                  <span>产品图字段</span>
                  <input value={productImageField} onChange={(event) => setProductImageField(event.target.value)} />
                </label>
              ) : null}
              <label className="field">
                <span>提示词字段</span>
                <input value={promptField} onChange={(event) => setPromptField(event.target.value)} />
              </label>
              <label className="field">
                <span>比例字段</span>
                <input value={aspectRatioField} onChange={(event) => setAspectRatioField(event.target.value)} />
              </label>
              <label className="field">
                <span>参考图片字段</span>
                <input value={referenceImageField} onChange={(event) => setReferenceImageField(event.target.value)} />
              </label>
              {listenerWorkflowId === "product-main-detail" ? (
                <>
                  <label className="field">
                    <span>产品图描述字段</span>
                    <input value={productDescriptionField} onChange={(event) => setProductDescriptionField(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>参考图风格字段</span>
                    <input value={referenceStyleField} onChange={(event) => setReferenceStyleField(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>最终提示词字段</span>
                    <input value={finalPromptField} onChange={(event) => setFinalPromptField(event.target.value)} />
                  </label>
                </>
              ) : null}
            </>
          )}
          <label className="field">
            <span>待处理值</span>
            <input value={pendingValue} onChange={(event) => setPendingValue(event.target.value)} />
          </label>
          <label className="field">
            <span>处理中值</span>
            <input value={processingValue} onChange={(event) => setProcessingValue(event.target.value)} />
          </label>
          <label className="field">
            <span>成功值</span>
            <input value={successValue} onChange={(event) => setSuccessValue(event.target.value)} />
          </label>
          <label className="field">
            <span>部分成功值</span>
            <input value={partialValue} onChange={(event) => setPartialValue(event.target.value)} />
          </label>
          <label className="field">
            <span>失败值</span>
            <input value={failedValue} onChange={(event) => setFailedValue(event.target.value)} />
          </label>
          <label className="field">
            <span>结果字段</span>
            <input value={resultField} onChange={(event) => setResultField(event.target.value)} />
          </label>
          <label className="field">
            <span>错误字段</span>
            <input value={errorField} onChange={(event) => setErrorField(event.target.value)} />
          </label>
          <label className="field">
            <span>工作流ID字段</span>
            <input value={runIdField} onChange={(event) => setRunIdField(event.target.value)} />
          </label>
          <label className="field">
            <span>处理时间字段</span>
            <input value={processedAtField} onChange={(event) => setProcessedAtField(event.target.value)} />
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
                  <span>{workflowTitle(listener.workflow_id)}</span>
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
          <h2>任务队列</h2>
          <span>{queue.length}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务ID</th>
                <th>来源</th>
                <th>工作流</th>
                <th>状态</th>
                <th>尝试</th>
                <th>飞书记录</th>
                <th>创建时间</th>
                <th>下次重试</th>
                <th>开始 / 结束</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {queue.length ? (
                queue.map((task) => (
                  <tr key={task.id}>
                    <td>{shortId(task.id)}</td>
                    <td>{task.source}</td>
                    <td>{workflowTitle(task.workflow_id)}</td>
                    <td>
                      <StatusBadge status={task.status} />
                    </td>
                    <td>{task.attempt_count} / {task.max_attempts}</td>
                    <td>{shortId(task.remote_record_id || "-")}</td>
                    <td>{formatTime(task.created_at)}</td>
                    <td>{formatTime(task.run_after ?? undefined)}</td>
                    <td>
                      <span className="block">{formatTime(task.started_at ?? undefined)}</span>
                      <span className="muted block">{formatTime(task.ended_at ?? undefined)}</span>
                    </td>
                    <td className="summary-cell">{task.error_message || "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={10}>
                    <EmptyLine text="暂无队列任务" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
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
    throw new Error(body.detail ?? `?????${res.status}`);
  }
  return res.json();
}

function workflowTitle(workflowId: string) {
  const titles: Record<string, string> = {
    "lead-import-to-feishu": "CSV 线索清洗与飞书同步",
    "product-main-image": "图片生成",
    "product-main-detail": "主图详情页生成"
  };
  return titles[workflowId] ?? workflowId;
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

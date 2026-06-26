import { Eye, EyeOff, Loader2, Power, Settings } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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

type ConfigPayload = {
  module: Module;
  schema: Record<string, string>;
  values: Record<string, string>;
};

export function ConfigViewV2({ modules, setNotice, refreshAll }: { modules: Module[]; setNotice: (value: string) => void; refreshAll: () => Promise<void> }) {
  const configurable = modules.filter((module) => Object.keys(module.manifest.configSchema ?? {}).length > 0);
  const [selectedId, setSelectedId] = useState(configurable[0]?.id ?? "");
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [revealedSecrets, setRevealedSecrets] = useState<Record<string, boolean>>({});
  const [loadingSecret, setLoadingSecret] = useState("");

  const hasProviderControls = selectedId === "image-generator" || selectedId === "model-provider";
  const effectiveSchema = useMemo(() => {
    if (!config) return {};
    if (!hasProviderControls) return config.schema;
    return {
      ...config.schema,
      authMode: config.schema.authMode ?? "optional",
      providerMode: config.schema.providerMode ?? "optional"
    };
  }, [config, hasProviderControls]);

  useEffect(() => {
    if (!selectedId && configurable[0]?.id) {
      setSelectedId(configurable[0].id);
    }
  }, [configurable, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    setRevealedSecrets({});
    setLoadingSecret("");
    api<ConfigPayload>(`/api/modules/${selectedId}/config`)
      .then((payload) => {
        setConfig(payload);
        setValues(payload.values);
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "配置加载失败"));
  }, [selectedId, setNotice]);

  const toggleSecret = async (key: string) => {
    if (!selectedId) return;
    if (revealedSecrets[key]) {
      setRevealedSecrets((current) => ({ ...current, [key]: false }));
      return;
    }
    if (values[key] && values[key] !== "********") {
      setRevealedSecrets((current) => ({ ...current, [key]: true }));
      return;
    }
    setLoadingSecret(key);
    try {
      const payload = await api<ConfigPayload>(`/api/modules/${selectedId}/config?reveal=1`);
      setValues((current) => ({ ...current, [key]: payload.values[key] ?? current[key] ?? "" }));
      setRevealedSecrets((current) => ({ ...current, [key]: true }));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "密钥读取失败");
    } finally {
      setLoadingSecret("");
    }
  };

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
      setRevealedSecrets({});
      setLoadingSecret("");
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
          <div className="form-grid">
            {Object.entries(effectiveSchema).map(([key, type]) => (
              <ConfigFieldV2
                key={key}
                name={key}
                type={type}
                value={values[key] ?? ""}
                providerControls={hasProviderControls}
                revealed={Boolean(revealedSecrets[key])}
                loading={loadingSecret === key}
                onToggleReveal={type === "secret" ? () => toggleSecret(key) : undefined}
                onChange={(value) => setValues((current) => ({ ...current, [key]: value }))}
              />
            ))}
            <div className="action-row">
              <button className="button primary fit" onClick={() => saveConfig(false)} disabled={saving}>
                {saving ? <Loader2 className="spin" size={16} /> : <Settings size={16} />}
                保存配置
              </button>
              {hasProviderControls ? (
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
  providerControls,
  revealed = false,
  loading = false,
  onToggleReveal,
  onChange
}: {
  name: string;
  type: string;
  value: string;
  providerControls: boolean;
  revealed?: boolean;
  loading?: boolean;
  onToggleReveal?: () => void;
  onChange: (value: string) => void;
}) {
  if (providerControls && name === "authMode") {
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

  if (providerControls && name === "providerMode") {
    return (
      <label className="field">
        <span>
          providerMode
          <em>接口类型</em>
        </span>
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">自动判断</option>
          <option value="chat">Chat / Vision 接口</option>
          <option value="images">Images 接口</option>
        </select>
      </label>
    );
  }

  const isSecret = type === "secret";

  return (
    <label className="field">
      <span>
        {name}
        <em>{type}</em>
      </span>
      {isSecret ? (
        <div className="secret-input">
          <input type={revealed ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} />
          <button type="button" className="icon-button" onClick={onToggleReveal} disabled={loading} title={revealed ? "隐藏密钥" : "显示密钥"}>
            {loading ? <Loader2 className="spin" size={16} /> : revealed ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
      ) : (
        <input type="text" value={value} onChange={(event) => onChange(event.target.value)} />
      )}
    </label>
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

function EmptyLine({ text }: { text: string }) {
  return <div className="empty-line">{text}</div>;
}

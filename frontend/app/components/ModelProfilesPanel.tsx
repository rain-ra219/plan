import { Eye, EyeOff, Loader2, Plus, Save, Star, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

type ModelProfile = {
  id: string;
  name: string;
  purpose: string;
  baseUrl: string;
  apiKey: string;
  model: string;
  authMode: string;
  providerMode: string;
  enabled: boolean;
  isDefault: boolean;
};

const PURPOSES = [
  ["default", "默认"],
  ["text", "文本分析"],
  ["vision", "图片理解"],
  ["prompt", "提示词整理"]
];

export function ModelProfilesPanel({ setNotice }: { setNotice: (value: string) => void }) {
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState("");
  const [revealed, setRevealed] = useState(false);

  const loadProfiles = async (reveal = false) => {
    setLoading(true);
    try {
      const payload = await api<ModelProfile[]>(`/api/model-profiles${reveal ? "?reveal=1" : ""}`);
      setProfiles(payload);
      setRevealed(reveal);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "模型列表加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProfiles(false);
  }, []);

  const updateProfile = (id: string, patch: Partial<ModelProfile>) => {
    setProfiles((current) => current.map((profile) => (profile.id === id ? { ...profile, ...patch } : profile)));
  };

  const createProfile = async () => {
    setSavingId("__new");
    try {
      await api<ModelProfile>("/api/model-profiles", {
        method: "POST",
        body: JSON.stringify({
          name: "新模型",
          purpose: "default",
          baseUrl: "",
          apiKey: "",
          model: "",
          authMode: "bearer",
          providerMode: "chat",
          enabled: true,
          isDefault: profiles.length === 0
        })
      });
      await loadProfiles(false);
      setNotice("已新增模型配置");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "新增模型失败");
    } finally {
      setSavingId("");
    }
  };

  const saveProfile = async (profile: ModelProfile) => {
    setSavingId(profile.id);
    try {
      await api<ModelProfile>(`/api/model-profiles/${profile.id}`, {
        method: "PATCH",
        body: JSON.stringify(profile)
      });
      await loadProfiles(false);
      setNotice("模型配置已保存");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "保存模型失败");
    } finally {
      setSavingId("");
    }
  };

  const setDefaultProfile = async (profile: ModelProfile) => {
    setSavingId(profile.id);
    try {
      await api<ModelProfile>(`/api/model-profiles/${profile.id}/set-default`, { method: "POST" });
      await loadProfiles(false);
      setNotice("默认模型已更新");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "设置默认模型失败");
    } finally {
      setSavingId("");
    }
  };

  const deleteProfile = async (profile: ModelProfile) => {
    if (!window.confirm(`删除模型配置：${profile.name}？`)) return;
    setSavingId(profile.id);
    try {
      await api<{ status: string }>(`/api/model-profiles/${profile.id}`, { method: "DELETE" });
      await loadProfiles(false);
      setNotice("模型配置已删除");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除模型失败");
    } finally {
      setSavingId("");
    }
  };

  return (
    <div className="model-profile-panel">
      <div className="panel-head compact-headline">
        <div>
          <h2>模型档案</h2>
          <span>default / text / vision / prompt</span>
        </div>
        <div className="action-row">
          <button className="button secondary fit" onClick={() => loadProfiles(!revealed)} disabled={loading}>
            {loading ? <Loader2 className="spin" size={16} /> : revealed ? <EyeOff size={16} /> : <Eye size={16} />}
            {revealed ? "隐藏密钥" : "显示密钥"}
          </button>
          <button className="button primary fit" onClick={createProfile} disabled={Boolean(savingId)}>
            {savingId === "__new" ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
            新增模型
          </button>
        </div>
      </div>

      {profiles.length ? (
        <div className="model-profile-list">
          {profiles.map((profile) => (
            <div className="model-profile-card" key={profile.id}>
              <div className="model-profile-card-head">
                <strong>{profile.name || "未命名模型"}</strong>
                <div className="badge-row">
                  {profile.isDefault ? <span className="status healthy">默认</span> : null}
                  <span className={profile.enabled ? "status ready" : "status disabled"}>{profile.enabled ? "启用" : "停用"}</span>
                </div>
              </div>
              <div className="form-grid">
                <label className="field">
                  <span>名称</span>
                  <input value={profile.name} onChange={(event) => updateProfile(profile.id, { name: event.target.value })} />
                </label>
                <label className="field">
                  <span>用途</span>
                  <select value={profile.purpose} onChange={(event) => updateProfile(profile.id, { purpose: event.target.value })}>
                    {PURPOSES.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>baseUrl</span>
                  <input value={profile.baseUrl} onChange={(event) => updateProfile(profile.id, { baseUrl: event.target.value })} />
                </label>
                <label className="field">
                  <span>model</span>
                  <input value={profile.model} onChange={(event) => updateProfile(profile.id, { model: event.target.value })} />
                </label>
                <label className="field">
                  <span>apiKey</span>
                  <input type={revealed ? "text" : "password"} value={profile.apiKey} onChange={(event) => updateProfile(profile.id, { apiKey: event.target.value })} />
                </label>
                <label className="field">
                  <span>authMode</span>
                  <select value={profile.authMode} onChange={(event) => updateProfile(profile.id, { authMode: event.target.value })}>
                    <option value="bearer">Bearer Token</option>
                    <option value="raw">Raw Authorization</option>
                  </select>
                </label>
                <label className="field">
                  <span>providerMode</span>
                  <select value={profile.providerMode} onChange={(event) => updateProfile(profile.id, { providerMode: event.target.value })}>
                    <option value="chat">Chat / Vision 接口</option>
                    <option value="images">Images 接口</option>
                  </select>
                </label>
                <label className="field">
                  <span>状态</span>
                  <select value={profile.enabled ? "1" : "0"} onChange={(event) => updateProfile(profile.id, { enabled: event.target.value === "1" })}>
                    <option value="1">启用</option>
                    <option value="0">停用</option>
                  </select>
                </label>
              </div>
              <div className="action-row">
                <button className="button primary fit" onClick={() => saveProfile(profile)} disabled={savingId === profile.id}>
                  {savingId === profile.id ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
                  保存模型
                </button>
                <button className="button secondary fit" onClick={() => setDefaultProfile(profile)} disabled={savingId === profile.id || profile.isDefault}>
                  <Star size={16} />
                  设为默认
                </button>
                <button className="button danger fit" onClick={() => deleteProfile(profile)} disabled={savingId === profile.id}>
                  <Trash2 size={16} />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <button className="button primary fit" onClick={createProfile} disabled={Boolean(savingId)}>
          {savingId === "__new" ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
          新增第一个模型
        </button>
      )}
    </div>
  );
}

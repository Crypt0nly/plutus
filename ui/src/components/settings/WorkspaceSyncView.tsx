import { useState, useEffect, useCallback } from "react";
import {
  Cloud,
  CloudOff,
  Upload,
  Download,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Eye,
  EyeOff,
  ArrowUpDown,
  Plug,
  Zap,
  AlertTriangle,
  Link2,
  Folder,
  FolderOpen,
  RotateCcw,
} from "lucide-react";
import { api, extractCloudUrlFromToken, extractRawUrlFromToken } from "../../lib/api";

interface SyncConfig {
  url: string;
  token: string;
  auto_sync: boolean;
  auto_sync_interval: number;
  last_push: number;
  last_pull: number;
  workspace_dir?: string;
}

interface WorkspaceInfo {
  path: string;
  default_path: string;
  custom_path: string;
  total_size_bytes: number;
  file_count: number;
}

interface SyncStatus {
  local_only: number;
  cloud_only: number;
  newer_local: number;
  newer_cloud: number;
  in_sync: number;
  total_local: number;
  total_cloud: number;
}

function formatRelative(ts: number): string {
  if (!ts) return "Never";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function WorkspaceSyncView() {
  const [config, setConfig] = useState<SyncConfig>({
    url: "",
    token: "",
    auto_sync: false,
    auto_sync_interval: 300,
    last_push: 0,
    last_pull: 0,
    workspace_dir: "",
  });
  const [workspaceInfo, setWorkspaceInfo] = useState<WorkspaceInfo | null>(null);
  const [editingPath, setEditingPath] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [pathMsg, setPathMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [pushMsg, setPushMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [pullMsg, setPullMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const [data, info] = await Promise.all([
        api.getConfig(),
        api.getWorkspaceInfo().catch(() => null),
      ]);
      if (data.cloud_sync && typeof data.cloud_sync === "object") {
        setConfig((prev) => ({
          ...prev,
          ...(data.cloud_sync as Partial<SyncConfig>),
        }));
      }
      if (info) setWorkspaceInfo(info);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  // Derive the cloud URL from the embedded token automatically
  const derivedUrl = extractCloudUrlFromToken(config.token) || config.url;
  const isConfigured = !!(derivedUrl && config.token);

  const saveConfig = async () => {
    try {
      const toSave = { ...config, url: derivedUrl || config.url };
      await api.updateConfig({ cloud_sync: toSave });
      setSaveMsg({ text: "Saved successfully", ok: true });
      setTimeout(() => setSaveMsg(null), 2500);
    } catch {
      setSaveMsg({ text: "Failed to save", ok: false });
      setTimeout(() => setSaveMsg(null), 3000);
    }
  };

  const fetchStatus = async () => {
    if (!isConfigured) return;
    setStatusLoading(true);
    try {
      const data = await api.getWorkspaceSyncStatus(config.token);
      const localResp = await api.getWorkspaceManifest();
      setStatus({
        ...data,
        total_local: localResp.total,
        total_cloud: data.local_only + data.cloud_only + data.newer_local + data.newer_cloud + data.in_sync,
      });
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  const handlePush = async () => {
    if (!isConfigured) {
      setPushMsg({ text: "Paste your sync token first", ok: false });
      setTimeout(() => setPushMsg(null), 3000);
      return;
    }
    setPushing(true);
    setPushMsg(null);
    try {
      const resp = await api.workspacePush(config.token);
      await api.updateConfig({ cloud_sync: { ...config, url: derivedUrl, last_push: Date.now() / 1000 } });
      setConfig((c) => ({ ...c, last_push: Date.now() / 1000 }));
      const skippedNote = resp.uploaded === 0 ? " (all files already up to date)" : "";
      setPushMsg({ text: `Pushed ${resp.uploaded} file${resp.uploaded !== 1 ? "s" : ""}${skippedNote}`, ok: true });
      setTimeout(() => setPushMsg(null), 4000);
    } catch (e: any) {
      setPushMsg({ text: `Push failed: ${e.message || e}`, ok: false });
      setTimeout(() => setPushMsg(null), 5000);
    } finally {
      setPushing(false);
    }
  };

  const handlePull = async () => {
    if (!isConfigured) {
      setPullMsg({ text: "Paste your sync token first", ok: false });
      setTimeout(() => setPullMsg(null), 3000);
      return;
    }
    setPulling(true);
    setPullMsg(null);
    try {
      const resp = await api.workspacePull(config.token);
      await api.updateConfig({ cloud_sync: { ...config, url: derivedUrl, last_pull: Date.now() / 1000 } });
      setConfig((c) => ({ ...c, last_pull: Date.now() / 1000 }));
      // Refresh workspace info after pull
      api.getWorkspaceInfo().then((info) => setWorkspaceInfo(info)).catch(() => {});
      let msg = `Downloaded ${resp.downloaded} file${resp.downloaded !== 1 ? "s" : ""}`;
      if (resp.downloaded === 0 && (resp.skipped ?? 0) === 0) msg = "All files already up to date";
      else if (resp.downloaded === 0 && (resp.skipped ?? 0) > 0) msg = `All files already up to date (${resp.skipped} skipped)`;
      else if ((resp.skipped ?? 0) > 0) msg += ` · ${resp.skipped} already up to date`;
      if ((resp.failed ?? 0) > 0) msg += ` · ${resp.failed} not found on server`;
      setPullMsg({ text: msg, ok: true });
      setTimeout(() => setPullMsg(null), 5000);
    } catch (e: any) {
      setPullMsg({ text: `Pull failed: ${e.message || e}`, ok: false });
      setTimeout(() => setPullMsg(null), 5000);
    } finally {
      setPulling(false);
    }
  };

  const handleSavePath = async () => {
    try {
      const result = await api.setWorkspaceDir(newPath.trim());
      setWorkspaceInfo((prev) =>
        prev ? { ...prev, path: result.path, custom_path: result.custom_path } : null
      );
      setConfig((c) => ({ ...c, workspace_dir: result.custom_path }));
      setEditingPath(false);
      setPathMsg({ text: "Workspace directory updated", ok: true });
      setTimeout(() => setPathMsg(null), 3000);
    } catch (e: any) {
      setPathMsg({ text: `Failed: ${e.message || e}`, ok: false });
      setTimeout(() => setPathMsg(null), 4000);
    }
  };

  const handleResetPath = async () => {
    try {
      const result = await api.setWorkspaceDir("");
      setWorkspaceInfo((prev) =>
        prev ? { ...prev, path: result.path, custom_path: "" } : null
      );
      setConfig((c) => ({ ...c, workspace_dir: "" }));
      setEditingPath(false);
      setNewPath("");
      setPathMsg({ text: "Reset to default", ok: true });
      setTimeout(() => setPathMsg(null), 2500);
    } catch {
      setPathMsg({ text: "Failed to reset", ok: false });
      setTimeout(() => setPathMsg(null), 3000);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10">
        <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5">

      {/* ── Workspace path ── */}
      <div
        className="rounded-xl p-4 space-y-3"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2">
          <Folder className="w-3.5 h-3.5 text-amber-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Local Workspace</h4>
          {workspaceInfo && (
            <span className="ml-auto text-[11px] text-gray-600">
              {workspaceInfo.file_count} file{workspaceInfo.file_count !== 1 ? "s" : ""} · {formatBytes(workspaceInfo.total_size_bytes)}
            </span>
          )}
        </div>

        {workspaceInfo && !editingPath && (
          <div
            className="flex items-center gap-2 px-3 py-2.5 rounded-xl"
            style={{ background: "rgba(245,158,11,0.05)", border: "1px solid rgba(245,158,11,0.12)" }}
          >
            <FolderOpen className="w-4 h-4 text-amber-400/70 flex-shrink-0" />
            <span className="text-xs text-gray-300 font-mono flex-1 truncate" title={workspaceInfo.path}>
              {workspaceInfo.path}
            </span>
            <button
              onClick={() => { setEditingPath(true); setNewPath(workspaceInfo.custom_path || workspaceInfo.path); }}
              className="text-[11px] text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0 px-2 py-0.5 rounded-lg hover:bg-white/5"
            >
              Change
            </button>
          </div>
        )}

        {editingPath && (
          <div className="space-y-2">
            <input
              type="text"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder={workspaceInfo?.default_path ?? "~/plutus-workspace"}
              className="w-full bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-all font-mono"
              onKeyDown={(e) => { if (e.key === "Enter") handleSavePath(); if (e.key === "Escape") setEditingPath(false); }}
              autoFocus
            />
            <div className="flex items-center gap-2">
              <button
                onClick={handleSavePath}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-all"
                style={{ background: "rgba(245,158,11,0.7)" }}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Apply
              </button>
              <button
                onClick={handleResetPath}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 transition-all"
                style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset to default
              </button>
              <button
                onClick={() => setEditingPath(false)}
                className="text-xs text-gray-600 hover:text-gray-400 transition-colors ml-auto"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {pathMsg && (
          <p className={`text-[11px] flex items-center gap-1.5 ${pathMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
            {pathMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
            {pathMsg.text}
          </p>
        )}

        {!workspaceInfo && (
          <p className="text-xs text-gray-600 font-mono">~/plutus-workspace</p>
        )}
      </div>

      {/* ── Connection status banner ── */}
      <div
        className="flex items-center gap-3 px-4 py-3 rounded-xl"
        style={
          isConfigured
            ? { background: "rgba(6, 182, 212, 0.06)", border: "1px solid rgba(6, 182, 212, 0.18)" }
            : { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }
        }
      >
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={
            isConfigured
              ? { background: "rgba(6, 182, 212, 0.12)", color: "#22d3ee" }
              : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }
          }
        >
          {isConfigured ? <Cloud className="w-4 h-4" /> : <CloudOff className="w-4 h-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-200">
            {isConfigured ? "Connected to cloud" : "Not connected"}
          </p>
          <p className="text-xs text-gray-500 truncate mt-0.5">
            {isConfigured
              ? derivedUrl
              : "Paste your sync token from the cloud Settings → Workspace tab"}
          </p>
        </div>
        {isConfigured && (
          <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-cyan-400 flex-shrink-0"
            style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}>
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            Active
          </span>
        )}
      </div>

      {/* ── API Token input ── */}
      <div
        className="rounded-xl p-4 space-y-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2">
          <Link2 className="w-3.5 h-3.5 text-cyan-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Sync Token</h4>
        </div>

        <div>
          <div className="relative">
            <input
              type={showToken ? "text" : "password"}
              value={config.token}
              onChange={(e) => setConfig((c) => ({ ...c, token: e.target.value }))}
              placeholder="Paste your token from cloud Settings → Workspace"
              className="w-full bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 pr-10 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-all font-mono"
            />
            <button
              onClick={() => setShowToken((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors"
            >
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {config.token && !extractCloudUrlFromToken(config.token) && (() => {
            const raw = extractRawUrlFromToken(config.token);
            const isLocalhost = raw && (raw.includes("localhost") || raw.includes("127.0.0.1"));
            return (
              <p className="text-[11px] text-amber-400/80 mt-2 flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                {isLocalhost
                  ? "Token embeds localhost — the cloud server's SERVER_BASE_URL is not set. Regenerate the token after configuring it."
                  : "Legacy token — please regenerate a new one from cloud Settings → Workspace"}
              </p>
            );
          })()}
          {config.token && extractCloudUrlFromToken(config.token) && (
            <p className="text-[11px] text-cyan-400/70 mt-2 flex items-center gap-1.5">
              <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
              Server URL detected automatically from token
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={saveConfig}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-white text-sm font-medium transition-all active:scale-[0.98]"
            style={{ background: "rgba(6, 182, 212, 0.8)", boxShadow: "0 4px 14px rgba(6, 182, 212, 0.2)" }}
          >
            <Plug className="w-3.5 h-3.5" />
            Save
          </button>
          {saveMsg && (
            <span className={`flex items-center gap-1.5 text-xs ${saveMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
              {saveMsg.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
              {saveMsg.text}
            </span>
          )}
        </div>
      </div>

      {/* ── Auto-sync toggle ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-200">Auto-sync</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Automatically push local changes every{" "}
              {Math.round(config.auto_sync_interval / 60)} min
            </p>
          </div>
          <button
            onClick={() => {
              const updated = { ...config, auto_sync: !config.auto_sync };
              setConfig(updated);
              api.updateConfig({ cloud_sync: updated });
            }}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              config.auto_sync ? "bg-cyan-500" : "bg-gray-700"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                config.auto_sync ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {config.auto_sync && (
          <div className="mt-3 pt-3 flex items-center gap-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <label className="text-xs text-gray-500">Interval</label>
            <input
              type="number"
              min={1}
              max={60}
              value={Math.round(config.auto_sync_interval / 60)}
              onChange={(e) => {
                const updated = {
                  ...config,
                  auto_sync_interval: Math.max(1, parseInt(e.target.value) || 5) * 60,
                };
                setConfig(updated);
                api.updateConfig({ cloud_sync: updated });
              }}
              className="w-16 bg-gray-900/80 border border-gray-800/60 rounded-lg px-2 py-1 text-sm text-gray-200 text-center focus:outline-none focus:border-cyan-500/50 transition-all"
            />
            <span className="text-xs text-gray-500">minutes</span>
          </div>
        )}
      </div>

      {/* ── Push / Pull ── */}
      <div
        className="rounded-xl p-4 space-y-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2">
          <ArrowUpDown className="w-3.5 h-3.5 text-gray-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Manual Sync</h4>
          {(config.last_push > 0 || config.last_pull > 0) && (
            <div className="ml-auto flex items-center gap-3 text-[11px] text-gray-600">
              {config.last_push > 0 && (
                <span className="flex items-center gap-1">
                  <Upload className="w-3 h-3" />
                  {formatRelative(config.last_push)}
                </span>
              )}
              {config.last_pull > 0 && (
                <span className="flex items-center gap-1">
                  <Download className="w-3 h-3" />
                  {formatRelative(config.last_pull)}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* Push */}
          <div className="space-y-2">
            <button
              onClick={handlePush}
              disabled={pushing || !isConfigured}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
              style={
                isConfigured
                  ? { background: "rgba(6, 182, 212, 0.08)", border: "1px solid rgba(6, 182, 212, 0.2)", color: "#22d3ee" }
                  : { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }
              }
            >
              {pushing ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              {pushing ? "Pushing…" : "Push to Cloud"}
            </button>
            {pushMsg && (
              <p className={`text-[11px] text-center flex items-center justify-center gap-1 ${pushMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
                {pushMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {pushMsg.text}
              </p>
            )}
          </div>

          {/* Pull */}
          <div className="space-y-2">
            <button
              onClick={handlePull}
              disabled={pulling || !isConfigured}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
              style={
                isConfigured
                  ? { background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#34d399" }
                  : { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }
              }
            >
              {pulling ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              {pulling ? "Pulling…" : "Pull from Cloud"}
            </button>
            {pullMsg && (
              <p className={`text-[11px] text-center flex items-center justify-center gap-1 ${pullMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
                {pullMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {pullMsg.text}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Sync status ── */}
      {isConfigured && (
        <div
          className="rounded-xl p-4 space-y-3"
          style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5 text-gray-400" />
              <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Sync Status</h4>
            </div>
            <button
              onClick={fetchStatus}
              disabled={statusLoading}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${statusLoading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>

          {status ? (
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: "In sync", value: status.in_sync, color: "text-emerald-400", bg: "rgba(16,185,129,0.06)", border: "rgba(16,185,129,0.15)", icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
                { label: "Local only", value: status.local_only, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Upload className="w-3.5 h-3.5" /> },
                { label: "Cloud only", value: status.cloud_only, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Download className="w-3.5 h-3.5" /> },
                { label: "Newer locally", value: status.newer_local, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
                { label: "Newer in cloud", value: status.newer_cloud, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between rounded-xl px-3 py-2.5"
                  style={{ background: item.bg, border: `1px solid ${item.border}` }}
                >
                  <div className={`flex items-center gap-1.5 ${item.color}`}>
                    {item.icon}
                    <span className="text-xs text-gray-400">{item.label}</span>
                  </div>
                  <span className={`text-sm font-bold ${item.color}`}>{item.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <button
              onClick={fetchStatus}
              className="w-full py-4 text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center justify-center gap-2"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Click to check sync status
            </button>
          )}
        </div>
      )}

      {/* ── How to get a token ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: "rgba(6, 182, 212, 0.03)", border: "1px solid rgba(6, 182, 212, 0.1)" }}
      >
        <p className="text-xs font-semibold text-cyan-400/70 mb-2.5 uppercase tracking-wider">How to connect</p>
        <ol className="space-y-2 text-xs text-gray-500">
          <li className="flex gap-2">
            <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">1</span>
            Open <span className="text-gray-300 mx-1">cloud Plutus → Settings → Workspace Sync</span>
          </li>
          <li className="flex gap-2">
            <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">2</span>
            Click <span className="text-gray-300 mx-1">Generate Token</span> and copy it
          </li>
          <li className="flex gap-2">
            <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">3</span>
            Paste it above — the server URL is embedded automatically
          </li>
        </ol>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import {
  Cloud,
  Upload,
  Download,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Key,
  Copy,
  Trash2,
  AlertTriangle,
  ArrowUpDown,
  Zap,
  Link2,
  ShieldCheck,
  Server,
  FolderOpen,
  File,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { api } from "../../lib/api";

interface SyncStatus {
  local_only: number;
  cloud_only: number;
  newer_local: number;
  newer_cloud: number;
  in_sync: number;
}

interface TokenStatus {
  has_token: boolean;
  created_at: number | null;
}

interface WorkspaceFile {
  path: string;
  size: number;
  mtime: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRelative(ts: number | null): string {
  if (!ts) return "Never";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function WorkspaceSyncView() {
  const [tokenStatus, setTokenStatus] = useState<TokenStatus | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [generatingToken, setGeneratingToken] = useState(false);
  const [revokingToken, setRevokingToken] = useState(false);
  const [autoSync, setAutoSync] = useState(false);
  const [autoSyncInterval, setAutoSyncInterval] = useState(5);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [pushMsg, setPushMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [pullMsg, setPullMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[] | null>(null);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const [deletingFile, setDeletingFile] = useState<string | null>(null);

  const loadTokenStatus = useCallback(async () => {
    try {
      const data = await api.getSyncTokenStatus();
      setTokenStatus(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const data = await api.getConfig();
      if (data.cloud_sync) {
        const cs = data.cloud_sync as { auto_sync?: boolean; auto_sync_interval?: number };
        setAutoSync(cs.auto_sync ?? false);
        setAutoSyncInterval(Math.round((cs.auto_sync_interval ?? 300) / 60));
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadTokenStatus();
    loadConfig();
  }, [loadTokenStatus, loadConfig]);

  const handleGenerateToken = async () => {
    setGeneratingToken(true);
    setNewToken(null);
    try {
      const data = await api.generateSyncToken();
      setNewToken(data.token);
      setTokenStatus({ has_token: true, created_at: Date.now() / 1000 });
    } catch (e: any) {
      console.error("Failed to generate token:", e);
    } finally {
      setGeneratingToken(false);
    }
  };

  const handleRevokeToken = async () => {
    if (!confirm("Revoke the sync token? The local client will stop syncing until a new token is generated.")) return;
    setRevokingToken(true);
    try {
      await api.revokeSyncToken();
      setTokenStatus({ has_token: false, created_at: null });
      setNewToken(null);
    } catch {
      // ignore
    } finally {
      setRevokingToken(false);
    }
  };

  const handleCopy = () => {
    if (!newToken) return;
    navigator.clipboard.writeText(newToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAutoSyncToggle = async () => {
    const updated = !autoSync;
    setAutoSync(updated);
    await api.updateConfig({
      cloud_sync: { auto_sync: updated, auto_sync_interval: autoSyncInterval * 60 },
    });
  };

  const fetchSyncStatus = async () => {
    setStatusLoading(true);
    try {
      const data = await api.getWorkspaceSyncStatus();
      setSyncStatus(data);
    } catch {
      setSyncStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  const handlePush = async () => {
    setPushing(true);
    setPushMsg(null);
    try {
      const resp = await api.workspacePush();
      setPushMsg({ text: resp.message, ok: true });
      setTimeout(() => setPushMsg(null), 5000);
    } catch (e: any) {
      setPushMsg({ text: e.message || "Push failed", ok: false });
      setTimeout(() => setPushMsg(null), 5000);
    } finally {
      setPushing(false);
    }
  };

  const loadWorkspaceFiles = async () => {
    setFilesLoading(true);
    try {
      const data = await api.getWorkspaceFiles();
      setWorkspaceFiles(data.files || []);
    } catch {
      setWorkspaceFiles([]);
    } finally {
      setFilesLoading(false);
    }
  };

  const handleDeleteFile = async (path: string) => {
    if (!confirm(`Delete "${path}" from the server workspace?`)) return;
    setDeletingFile(path);
    try {
      await api.deleteWorkspaceFile(path);
      setWorkspaceFiles((prev) => prev?.filter((f) => f.path !== path) ?? null);
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`);
    } finally {
      setDeletingFile(null);
    }
  };

  const handlePull = async () => {
    setPulling(true);
    setPullMsg(null);
    try {
      const resp = await api.workspacePull();
      setPullMsg({ text: resp.message, ok: true });
      setTimeout(() => setPullMsg(null), 5000);
    } catch (e: any) {
      const msg = e.message?.includes("409")
        ? "No active sandbox — start a conversation first"
        : e.message || "Pull failed";
      setPullMsg({ text: msg, ok: false });
      setTimeout(() => setPullMsg(null), 5000);
    } finally {
      setPulling(false);
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

      {/* ── Token status banner ── */}
      <div
        className="flex items-center gap-3 px-4 py-3 rounded-xl"
        style={
          tokenStatus?.has_token
            ? { background: "rgba(6, 182, 212, 0.06)", border: "1px solid rgba(6, 182, 212, 0.18)" }
            : { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }
        }
      >
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={
            tokenStatus?.has_token
              ? { background: "rgba(6, 182, 212, 0.12)", color: "#22d3ee" }
              : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }
          }
        >
          {tokenStatus?.has_token ? <ShieldCheck className="w-4 h-4" /> : <Key className="w-4 h-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-200">
            {tokenStatus?.has_token ? "Sync token active" : "No sync token"}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {tokenStatus?.has_token
              ? `Generated ${formatRelative(tokenStatus.created_at)} — paste into local Plutus to connect`
              : "Generate a token to link your local Plutus installation"}
          </p>
        </div>
        {tokenStatus?.has_token && (
          <span
            className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-cyan-400 flex-shrink-0"
            style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}
          >
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            Active
          </span>
        )}
      </div>

      {/* ── API Token management ── */}
      <div
        className="rounded-xl p-4 space-y-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2">
          <Link2 className="w-3.5 h-3.5 text-cyan-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Local Connection Token</h4>
        </div>

        <p className="text-xs text-gray-500 leading-relaxed">
          Generate a token and paste it into{" "}
          <span className="text-gray-300">local Plutus → Settings → Cloud Sync</span>.
          The server URL is embedded automatically — no extra fields needed on the local side.
        </p>

        {/* Newly generated token display */}
        {newToken && (
          <div className="space-y-3">
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
              style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", color: "#fbbf24" }}
            >
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              Copy this token now — it will not be shown again
            </div>
            <div
              className="flex items-center gap-2 p-3 rounded-xl"
              style={{ background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.15)" }}
            >
              <code className="flex-1 text-xs text-cyan-300 font-mono break-all leading-relaxed">
                {newToken}
              </code>
              <button
                onClick={handleCopy}
                className="flex-shrink-0 p-2 rounded-lg transition-all"
                style={
                  copied
                    ? { background: "rgba(16,185,129,0.15)", color: "#34d399" }
                    : { background: "rgba(255,255,255,0.06)", color: "#9ca3af" }
                }
                title="Copy token"
              >
                {copied ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            {copied && (
              <p className="text-[11px] text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3 h-3" />
                Copied to clipboard
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerateToken}
            disabled={generatingToken}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-white text-sm font-medium transition-all disabled:opacity-50 active:scale-[0.98]"
            style={{ background: "rgba(6, 182, 212, 0.8)", boxShadow: "0 4px 14px rgba(6, 182, 212, 0.2)" }}
          >
            {generatingToken ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Key className="w-3.5 h-3.5" />
            )}
            {tokenStatus?.has_token ? "Regenerate Token" : "Generate Token"}
          </button>

          {tokenStatus?.has_token && (
            <button
              onClick={handleRevokeToken}
              disabled={revokingToken}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all disabled:opacity-50 active:scale-[0.98]"
              style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#f87171" }}
            >
              {revokingToken ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Revoke
            </button>
          )}
        </div>
      </div>

      {/* ── Sandbox ↔ Workspace Push / Pull ── */}
      <div
        className="rounded-xl p-4 space-y-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center gap-2">
          <ArrowUpDown className="w-3.5 h-3.5 text-gray-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Sandbox Sync</h4>
          <span className="ml-auto text-[10px] text-gray-600">Sandbox ↔ Cloud Workspace</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* Push sandbox → workspace */}
          <div className="space-y-2">
            <button
              onClick={handlePush}
              disabled={pushing}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
              style={{ background: "rgba(6, 182, 212, 0.08)", border: "1px solid rgba(6, 182, 212, 0.2)", color: "#22d3ee" }}
            >
              {pushing ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              {pushing ? "Pushing…" : "Push to Workspace"}
            </button>
            <p className="text-[10px] text-gray-600 text-center">Sandbox → Server workspace</p>
            {pushMsg && (
              <p className={`text-[11px] text-center flex items-center justify-center gap-1 ${pushMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
                {pushMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {pushMsg.text}
              </p>
            )}
          </div>

          {/* Pull workspace → sandbox */}
          <div className="space-y-2">
            <button
              onClick={handlePull}
              disabled={pulling}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
              style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#34d399" }}
            >
              {pulling ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              {pulling ? "Pulling…" : "Pull to Sandbox"}
            </button>
            <p className="text-[10px] text-gray-600 text-center">Server workspace → Sandbox</p>
            {pullMsg && (
              <p className={`text-[11px] text-center flex items-center justify-center gap-1 ${pullMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
                {pullMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                {pullMsg.text}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Auto-sync toggle ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-200">Auto-sync sandbox</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Automatically push sandbox files to the workspace every{" "}
              {autoSyncInterval} min
            </p>
          </div>
          <button
            onClick={handleAutoSyncToggle}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
              autoSync ? "bg-cyan-500" : "bg-gray-700"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                autoSync ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {autoSync && (
          <div className="mt-3 pt-3 flex items-center gap-3" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <label className="text-xs text-gray-500">Interval</label>
            <input
              type="number"
              min={1}
              max={60}
              value={autoSyncInterval}
              onChange={async (e) => {
                const v = Math.max(1, parseInt(e.target.value) || 5);
                setAutoSyncInterval(v);
                await api.updateConfig({
                  cloud_sync: { auto_sync: true, auto_sync_interval: v * 60 },
                });
              }}
              className="w-16 bg-gray-900/80 border border-gray-800/60 rounded-lg px-2 py-1 text-sm text-gray-200 text-center focus:outline-none focus:border-cyan-500/50 transition-all"
            />
            <span className="text-xs text-gray-500">minutes</span>
          </div>
        )}
      </div>

      {/* ── Sync status ── */}
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
            onClick={fetchSyncStatus}
            disabled={statusLoading}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${statusLoading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {syncStatus ? (
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "In sync", value: syncStatus.in_sync, color: "text-emerald-400", bg: "rgba(16,185,129,0.06)", border: "rgba(16,185,129,0.15)", icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
              { label: "Sandbox only", value: syncStatus.local_only, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Upload className="w-3.5 h-3.5" /> },
              { label: "Workspace only", value: syncStatus.cloud_only, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Server className="w-3.5 h-3.5" /> },
              { label: "Newer in sandbox", value: syncStatus.newer_local, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
              { label: "Newer in workspace", value: syncStatus.newer_cloud, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
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
            onClick={fetchSyncStatus}
            className="w-full py-4 text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center justify-center gap-2"
          >
            <Zap className="w-3.5 h-3.5" />
            Click to compare sandbox and workspace
          </button>
        )}
      </div>

      {/* ── Server Workspace Files ── */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <button
          className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
          onClick={() => {
            const next = !filesExpanded;
            setFilesExpanded(next);
            if (next && workspaceFiles === null) loadWorkspaceFiles();
          }}
        >
          <FolderOpen className="w-3.5 h-3.5 text-gray-400" />
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex-1">Server Workspace Files</h4>
          {workspaceFiles !== null && (
            <span className="text-[10px] text-gray-600 mr-2">
              {workspaceFiles.length} file{workspaceFiles.length !== 1 ? "s" : ""}
            </span>
          )}
          {filesExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-gray-600" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
          )}
        </button>

        {filesExpanded && (
          <div className="px-4 pb-4 space-y-2">
            <div className="flex items-center justify-between mb-1">
              <p className="text-[10px] text-gray-600">Files stored on the server — available to pull into the sandbox</p>
              <button
                onClick={loadWorkspaceFiles}
                disabled={filesLoading}
                className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
              >
                <RefreshCw className={`w-3 h-3 ${filesLoading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>

            {filesLoading ? (
              <div className="flex items-center justify-center py-6">
                <div className="w-5 h-5 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
              </div>
            ) : workspaceFiles && workspaceFiles.length > 0 ? (
              <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
                {workspaceFiles
                  .sort((a, b) => b.mtime - a.mtime)
                  .map((f) => (
                    <div
                      key={f.path}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg group"
                      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
                    >
                      <File className="w-3 h-3 text-gray-600 flex-shrink-0" />
                      <span className="flex-1 text-xs text-gray-400 font-mono truncate" title={f.path}>
                        {f.path}
                      </span>
                      <span className="text-[10px] text-gray-600 flex-shrink-0">{formatBytes(f.size)}</span>
                      <span className="text-[10px] text-gray-700 flex-shrink-0 ml-1">{formatRelative(f.mtime)}</span>
                      <button
                        onClick={() => handleDeleteFile(f.path)}
                        disabled={deletingFile === f.path}
                        className="opacity-0 group-hover:opacity-100 flex-shrink-0 p-1 rounded transition-all hover:bg-red-500/10"
                        style={{ color: "#f87171" }}
                        title="Delete from server workspace"
                      >
                        {deletingFile === f.path ? (
                          <RefreshCw className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                      </button>
                    </div>
                  ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-6 gap-2">
                <FolderOpen className="w-8 h-8 text-gray-700" />
                <p className="text-xs text-gray-600">No files on the server workspace yet</p>
                <p className="text-[10px] text-gray-700">Push from local or from the sandbox to add files</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── How it works ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: "rgba(6, 182, 212, 0.03)", border: "1px solid rgba(6, 182, 212, 0.1)" }}
      >
        <p className="text-xs font-semibold text-cyan-400/70 mb-2.5 uppercase tracking-wider">How it works</p>
        <ul className="space-y-2 text-xs text-gray-500">
          <li className="flex gap-2">
            <Cloud className="w-3.5 h-3.5 text-cyan-400/50 flex-shrink-0 mt-0.5" />
            The <span className="text-gray-300 mx-1">cloud workspace</span> is the persistent server-side file store — it survives sandbox restarts
          </li>
          <li className="flex gap-2">
            <Upload className="w-3.5 h-3.5 text-amber-400/50 flex-shrink-0 mt-0.5" />
            <span><span className="text-gray-300">Push</span> — copies files from the active sandbox into the workspace</span>
          </li>
          <li className="flex gap-2">
            <Download className="w-3.5 h-3.5 text-sky-400/50 flex-shrink-0 mt-0.5" />
            <span><span className="text-gray-300">Pull</span> — restores workspace files into the active sandbox</span>
          </li>
          <li className="flex gap-2">
            <Key className="w-3.5 h-3.5 text-cyan-400/50 flex-shrink-0 mt-0.5" />
            The <span className="text-gray-300 mx-1">local connection token</span> lets your local Plutus push/pull to this same workspace
          </li>
        </ul>
      </div>
    </div>
  );
}

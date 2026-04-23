import { useState, useEffect, useCallback, useRef } from "react";
import {
  Cloud,
  CloudOff,
  Upload,
  Download,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowUpDown,
  Plug,
  PlugZap,
  Zap,
  Folder,
  FolderOpen,
  RotateCcw,
  Unplug,
  Loader2,
  Copy,
} from "lucide-react";
import { api, extractCloudUrlFromToken } from "../../lib/api";

/* ── Default cloud URL (can be overridden in the pairing input) ── */
const DEFAULT_CLOUD_URL = "https://api.useplutus.ai";

/* ── Types ── */

interface SyncConfig {
  url: string;
  token: string;
  enabled: boolean;
  workspace_dir?: string;
  auto_sync?: boolean;
  auto_sync_interval?: number;
  last_push?: number;
  last_pull?: number;
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

interface CloudStatus {
  connected: boolean;
  token_configured: boolean;
  cloud_url: string;
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
  /* ── State ── */
  const [config, setConfig] = useState<SyncConfig>({
    url: "",
    token: "",
    enabled: true,
    workspace_dir: "",
  });
  const [cloudStatus, setCloudStatus] = useState<CloudStatus>({
    connected: false,
    token_configured: false,
    cloud_url: "",
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
  const [pushMsg, setPushMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [pullMsg, setPullMsg] = useState<{ text: string; ok: boolean } | null>(null);

  /* Pairing state */
  const [pairing, setPairing] = useState(false);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingMsg, setPairingMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [cloudUrl, setCloudUrl] = useState(DEFAULT_CLOUD_URL);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── Load config + cloud status ── */
  const loadConfig = useCallback(async () => {
    try {
      const [data, info, cs] = await Promise.all([
        api.getConfig(),
        api.getWorkspaceInfo().catch(() => null),
        api.getCloudBridgeStatus(),
      ]);
      if (data.cloud_sync && typeof data.cloud_sync === "object") {
        setConfig((prev) => ({ ...prev, ...(data.cloud_sync as Partial<SyncConfig>) }));
        const syncCfg = data.cloud_sync as Partial<SyncConfig>;
        if (syncCfg.url) setCloudUrl(syncCfg.url);
      }
      if (info) setWorkspaceInfo(info);
      setCloudStatus(cs);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  /* Poll cloud status every 5s while connected */
  useEffect(() => {
    if (!cloudStatus.token_configured) return;
    const id = setInterval(async () => {
      try {
        const cs = await api.getCloudBridgeStatus();
        setCloudStatus(cs);
      } catch {
        // ignore
      }
    }, 5000);
    return () => clearInterval(id);
  }, [cloudStatus.token_configured]);

  /* Cleanup pairing poll on unmount */
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const derivedUrl = extractCloudUrlFromToken(config.token) || config.url;
  const isConfigured = !!(derivedUrl && config.token);

  /* ── Pairing flow ── */
  const startPairing = async () => {
    setPairing(true);
    setPairingCode(null);
    setPairingMsg(null);
    setCodeCopied(false);
    try {
      const result = await api.cloudPairInitiate(cloudUrl);
      setPairingCode(result.code);

      // Also tell the local backend to start polling
      await fetch("/api/cloud/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cloud_url: cloudUrl }),
      });

      // Poll for completion on the frontend side too (for UI updates)
      if (pollRef.current) clearInterval(pollRef.current);
      const expiresAt = result.expires_at;
      pollRef.current = setInterval(async () => {
        if (Date.now() / 1000 > expiresAt) {
          if (pollRef.current) clearInterval(pollRef.current);
          setPairing(false);
          setPairingCode(null);
          setPairingMsg({ text: "Pairing timed out — try again", ok: false });
          setTimeout(() => setPairingMsg(null), 5000);
          return;
        }
        try {
          const cs = await api.getCloudBridgeStatus();
          if (cs.token_configured) {
            if (pollRef.current) clearInterval(pollRef.current);
            setCloudStatus(cs);
            setPairing(false);
            setPairingCode(null);
            setPairingMsg({ text: "Connected to cloud!", ok: true });
            setTimeout(() => setPairingMsg(null), 5000);
            // Reload config to get the saved token
            const data = await api.getConfig();
            if (data.cloud_sync && typeof data.cloud_sync === "object") {
              setConfig((prev) => ({ ...prev, ...(data.cloud_sync as Partial<SyncConfig>) }));
            }
          }
        } catch {
          // ignore
        }
      }, 3000);
    } catch (e: any) {
      setPairing(false);
      setPairingMsg({
        text: `Failed to start pairing: ${e.message || e}`,
        ok: false,
      });
      setTimeout(() => setPairingMsg(null), 5000);
    }
  };

  const cancelPairing = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setPairing(false);
    setPairingCode(null);
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await api.cloudDisconnect();
      setCloudStatus({ connected: false, token_configured: false, cloud_url: "" });
      setConfig((c) => ({ ...c, token: "", url: "", enabled: false }));
    } catch {
      // ignore
    } finally {
      setDisconnecting(false);
    }
  };

  const copyCode = () => {
    if (pairingCode) {
      navigator.clipboard.writeText(pairingCode);
      setCodeCopied(true);
      setTimeout(() => setCodeCopied(false), 2000);
    }
  };

  /* ── Workspace sync handlers (same as before) ── */
  const handlePush = async () => {
    if (!isConfigured) return;
    setPushing(true);
    setPushMsg(null);
    try {
      const resp = await api.workspacePush(config.token);
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
    if (!isConfigured) return;
    setPulling(true);
    setPullMsg(null);
    try {
      const resp = await api.workspacePull(config.token);
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

  const handleSavePath = async () => {
    try {
      const result = await api.setWorkspaceDir(newPath.trim());
      setWorkspaceInfo((prev) => prev ? { ...prev, path: result.path, custom_path: result.custom_path } : null);
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
      setWorkspaceInfo((prev) => prev ? { ...prev, path: result.path, custom_path: "" } : null);
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

  /* ── Render ── */

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

      {/* ── Cloud Connection ── */}
      <div
        className="rounded-xl p-4 space-y-4"
        style={
          cloudStatus.connected
            ? { background: "rgba(6, 182, 212, 0.06)", border: "1px solid rgba(6, 182, 212, 0.18)" }
            : cloudStatus.token_configured
            ? { background: "rgba(245,158,11,0.04)", border: "1px solid rgba(245,158,11,0.15)" }
            : { background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }
        }
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
            style={
              cloudStatus.connected
                ? { background: "rgba(6, 182, 212, 0.12)", color: "#22d3ee" }
                : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }
            }
          >
            {cloudStatus.connected ? <Cloud className="w-5 h-5" /> : <CloudOff className="w-5 h-5" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-200">
              {cloudStatus.connected
                ? "Connected to Plutus Cloud"
                : cloudStatus.token_configured
                ? "Connecting to cloud…"
                : "Not connected to cloud"}
            </p>
            <p className="text-xs text-gray-500 truncate mt-0.5">
              {cloudStatus.connected
                ? cloudStatus.cloud_url || derivedUrl || "Bridge active"
                : cloudStatus.token_configured
                ? "Bridge is reconnecting…"
                : "Connect to sync files and enable remote control"}
            </p>
          </div>
          {cloudStatus.connected && (
            <span
              className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-cyan-400 flex-shrink-0"
              style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}
            >
              <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              Connected
            </span>
          )}
          {cloudStatus.token_configured && !cloudStatus.connected && (
            <span
              className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-amber-400 flex-shrink-0"
              style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)" }}
            >
              <Loader2 className="w-3 h-3 animate-spin" />
              Reconnecting
            </span>
          )}
        </div>

        {/* Not connected — show pairing UI */}
        {!cloudStatus.token_configured && !pairing && (
          <div className="space-y-3">
            <button
              onClick={startPairing}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-white text-sm font-medium transition-all active:scale-[0.98]"
              style={{ background: "rgba(6, 182, 212, 0.8)", boxShadow: "0 4px 14px rgba(6, 182, 212, 0.2)" }}
            >
              <PlugZap className="w-4 h-4" />
              Connect to Plutus Cloud
            </button>

            {showAdvanced ? (
              <div className="space-y-2">
                <label className="text-[11px] text-gray-500 uppercase tracking-wider">Cloud Server URL</label>
                <input
                  type="text"
                  value={cloudUrl}
                  onChange={(e) => setCloudUrl(e.target.value)}
                  placeholder={DEFAULT_CLOUD_URL}
                  className="w-full bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 transition-all font-mono"
                />
              </div>
            ) : (
              <button
                onClick={() => setShowAdvanced(true)}
                className="text-[11px] text-gray-600 hover:text-gray-400 transition-colors"
              >
                Advanced: use a custom cloud server
              </button>
            )}
          </div>
        )}

        {/* Pairing in progress — show code */}
        {pairing && pairingCode && (
          <div className="space-y-3">
            <div
              className="rounded-xl p-4 text-center"
              style={{ background: "rgba(6, 182, 212, 0.06)", border: "1px solid rgba(6, 182, 212, 0.15)" }}
            >
              <p className="text-xs text-gray-400 mb-2">Enter this code in your Plutus Cloud settings:</p>
              <div className="flex items-center justify-center gap-3">
                <span className="text-3xl font-mono font-bold text-cyan-400 tracking-[0.2em]">
                  {pairingCode}
                </span>
                <button
                  onClick={copyCode}
                  className="p-1.5 rounded-lg hover:bg-white/5 transition-colors text-gray-500 hover:text-gray-300"
                  title="Copy code"
                >
                  {codeCopied ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-[11px] text-gray-600 mt-2">Code expires in 5 minutes</p>
            </div>
            <div className="flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
              <span className="text-xs text-gray-400">Waiting for confirmation from cloud…</span>
              <button
                onClick={cancelPairing}
                className="ml-auto text-xs text-gray-600 hover:text-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {pairing && !pairingCode && (
          <div className="flex items-center justify-center gap-2 py-4">
            <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
            <span className="text-xs text-gray-400">Connecting to cloud server…</span>
          </div>
        )}

        {/* Connected — show disconnect button */}
        {cloudStatus.token_configured && (
          <button
            onClick={handleDisconnect}
            disabled={disconnecting}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:text-red-400 transition-all"
            style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}
          >
            {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unplug className="w-3.5 h-3.5" />}
            Disconnect from cloud
          </button>
        )}

        {pairingMsg && (
          <p className={`text-[11px] flex items-center gap-1.5 ${pairingMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
            {pairingMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
            {pairingMsg.text}
          </p>
        )}
      </div>

      {/* ── Push / Pull (only when connected) ── */}
      {isConfigured && (
        <div
          className="rounded-xl p-4 space-y-4"
          style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
        >
          <div className="flex items-center gap-2">
            <ArrowUpDown className="w-3.5 h-3.5 text-gray-400" />
            <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">File Sync</h4>
            {((config.last_push ?? 0) > 0 || (config.last_pull ?? 0) > 0) && (
              <div className="ml-auto flex items-center gap-3 text-[11px] text-gray-600">
                {(config.last_push ?? 0) > 0 && (
                  <span className="flex items-center gap-1">
                    <Upload className="w-3 h-3" />
                    {formatRelative(config.last_push ?? 0)}
                  </span>
                )}
                {(config.last_pull ?? 0) > 0 && (
                  <span className="flex items-center gap-1">
                    <Download className="w-3 h-3" />
                    {formatRelative(config.last_pull ?? 0)}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <button
                onClick={handlePush}
                disabled={pushing}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
                style={{ background: "rgba(6, 182, 212, 0.08)", border: "1px solid rgba(6, 182, 212, 0.2)", color: "#22d3ee" }}
              >
                {pushing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {pushing ? "Pushing…" : "Push to Cloud"}
              </button>
              {pushMsg && (
                <p className={`text-[11px] text-center flex items-center justify-center gap-1 ${pushMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
                  {pushMsg.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                  {pushMsg.text}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <button
                onClick={handlePull}
                disabled={pulling}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.98]"
                style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.2)", color: "#34d399" }}
              >
                {pulling ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
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
      )}

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

      {/* ── How it works (only when not connected) ── */}
      {!cloudStatus.token_configured && !pairing && (
        <div
          className="rounded-xl p-4"
          style={{ background: "rgba(6, 182, 212, 0.03)", border: "1px solid rgba(6, 182, 212, 0.1)" }}
        >
          <p className="text-xs font-semibold text-cyan-400/70 mb-2.5 uppercase tracking-wider">How it works</p>
          <ol className="space-y-2 text-xs text-gray-500">
            <li className="flex gap-2">
              <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">1</span>
              Click <span className="text-gray-300 mx-1">Connect to Plutus Cloud</span> above
            </li>
            <li className="flex gap-2">
              <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">2</span>
              Enter the pairing code in <span className="text-gray-300 mx-1">cloud Plutus → Settings</span>
            </li>
            <li className="flex gap-2">
              <span className="flex-shrink-0 w-4 h-4 rounded-full bg-cyan-500/15 text-cyan-400 text-[10px] font-bold flex items-center justify-center">3</span>
              Done — bridge connects automatically and stays connected
            </li>
          </ol>
        </div>
      )}
    </div>
  );
}

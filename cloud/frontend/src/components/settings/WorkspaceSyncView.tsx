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
          <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-cyan-400 flex-shrink-0"
            style={{ background: "rgba(6, 182, 212, 0.1)", border: "1px solid rgba(6, 182, 212, 0.2)" }}>
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
          <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Sync Token</h4>
        </div>

        <p className="text-xs text-gray-500 leading-relaxed">
          Generate a token and paste it into{" "}
          <span className="text-gray-300">local Plutus → Settings → Cloud Sync</span>.
          The server URL is embedded automatically — no extra fields needed.
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

      {/* ── Auto-sync toggle ── */}
      <div
        className="rounded-xl p-4"
        style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)" }}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-200">Auto-sync to local</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Push cloud workspace changes to connected local clients every{" "}
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
            <ArrowUpDown className="w-3.5 h-3.5 text-gray-400" />
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
              { label: "Local only", value: syncStatus.local_only, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Upload className="w-3.5 h-3.5" /> },
              { label: "Cloud only", value: syncStatus.cloud_only, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Download className="w-3.5 h-3.5" /> },
              { label: "Newer locally", value: syncStatus.newer_local, color: "text-amber-400", bg: "rgba(245,158,11,0.06)", border: "rgba(245,158,11,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
              { label: "Newer in cloud", value: syncStatus.newer_cloud, color: "text-sky-400", bg: "rgba(14,165,233,0.06)", border: "rgba(14,165,233,0.15)", icon: <Clock className="w-3.5 h-3.5" /> },
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
            Click to compare cloud and local workspaces
          </button>
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
            Files created by Plutus in the sandbox are synced here every 5 minutes
          </li>
          <li className="flex gap-2">
            <Upload className="w-3.5 h-3.5 text-amber-400/50 flex-shrink-0 mt-0.5" />
            <span><span className="text-gray-300">Push</span> — uploads your local workspace to the cloud</span>
          </li>
          <li className="flex gap-2">
            <Download className="w-3.5 h-3.5 text-sky-400/50 flex-shrink-0 mt-0.5" />
            <span><span className="text-gray-300">Pull</span> — downloads cloud files to your local machine</span>
          </li>
          <li className="flex gap-2">
            <Key className="w-3.5 h-3.5 text-cyan-400/50 flex-shrink-0 mt-0.5" />
            The generated token includes the server URL — no separate URL field needed on the local side
          </li>
        </ul>
      </div>
    </div>
  );
}

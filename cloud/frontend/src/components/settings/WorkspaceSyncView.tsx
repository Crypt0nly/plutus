import { useState, useEffect, useCallback } from "react";
import {
  Cloud,
  Upload,
  Download,
  RefreshCw,
  CheckCircle,
  Clock,
  ToggleLeft,
  ToggleRight,
  Key,
  Copy,
  Trash2,
  AlertCircle,
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
        setAutoSyncInterval(
          Math.round((cs.auto_sync_interval ?? 300) / 60)
        );
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
      cloud_sync: {
        auto_sync: updated,
        auto_sync_interval: autoSyncInterval * 60,
      },
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
      <div className="flex items-center justify-center py-8">
        <RefreshCw className="w-5 h-5 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* API Token */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Key className="w-4 h-4 text-cyan-400" />
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            Sync API Token
          </h3>
        </div>

        <p className="text-xs text-zinc-400">
          Generate a token and paste it into{" "}
          <span className="text-zinc-200">
            local Plutus → Settings → Cloud Sync → API Token
          </span>{" "}
          to enable push/pull between your local machine and this workspace.
        </p>

        {tokenStatus?.has_token && !newToken && (
          <div className="flex items-center gap-2 text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">
            <CheckCircle className="w-3.5 h-3.5 shrink-0" />
            Token active — created {formatRelative(tokenStatus.created_at)}
          </div>
        )}

        {newToken && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              Copy this token now — it will not be shown again
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-cyan-300 font-mono break-all">
                {newToken}
              </code>
              <button
                onClick={handleCopy}
                className="shrink-0 p-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-zinc-400 hover:text-white transition-colors"
              >
                {copied ? (
                  <CheckCircle className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        )}

        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerateToken}
            disabled={generatingToken}
            className="flex items-center gap-2 px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
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
              className="flex items-center gap-2 px-4 py-1.5 bg-red-900/40 hover:bg-red-900/60 disabled:opacity-50 text-red-400 text-xs rounded-lg border border-red-800/40 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Revoke
            </button>
          )}
        </div>
      </div>

      {/* Auto-sync toggle */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-white">Auto-sync to local</h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Automatically push cloud workspace changes to connected local
              clients every {autoSyncInterval} minute{autoSyncInterval !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={handleAutoSyncToggle}
            className="text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            {autoSync ? (
              <ToggleRight className="w-8 h-8" />
            ) : (
              <ToggleLeft className="w-8 h-8 text-zinc-500" />
            )}
          </button>
        </div>

        {autoSync && (
          <div className="mt-3 flex items-center gap-3">
            <label className="text-xs text-zinc-400">Interval (minutes)</label>
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
              className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
        )}
      </div>

      {/* Sync status */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            Sync Status
          </h3>
          <button
            onClick={fetchSyncStatus}
            disabled={statusLoading}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white transition-colors"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${statusLoading ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        </div>

        {syncStatus ? (
          <div className="grid grid-cols-2 gap-2">
            {[
              {
                label: "In sync",
                value: syncStatus.in_sync,
                color: "text-green-400",
                icon: <CheckCircle className="w-3.5 h-3.5" />,
              },
              {
                label: "Local only",
                value: syncStatus.local_only,
                color: "text-yellow-400",
                icon: <Upload className="w-3.5 h-3.5" />,
              },
              {
                label: "Cloud only",
                value: syncStatus.cloud_only,
                color: "text-blue-400",
                icon: <Download className="w-3.5 h-3.5" />,
              },
              {
                label: "Newer locally",
                value: syncStatus.newer_local,
                color: "text-yellow-400",
                icon: <Clock className="w-3.5 h-3.5" />,
              },
              {
                label: "Newer in cloud",
                value: syncStatus.newer_cloud,
                color: "text-blue-400",
                icon: <Clock className="w-3.5 h-3.5" />,
              },
            ].map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between bg-zinc-800 rounded-lg px-3 py-2"
              >
                <div className={`flex items-center gap-1.5 ${item.color}`}>
                  {item.icon}
                  <span className="text-xs text-zinc-400">{item.label}</span>
                </div>
                <span className={`text-sm font-semibold ${item.color}`}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-zinc-500 text-center py-2">
            Click Refresh to compare cloud and local workspaces
          </p>
        )}
      </div>

      {/* How it works */}
      <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-4">
        <h3 className="text-xs font-semibold text-zinc-400 mb-2">How it works</h3>
        <ul className="space-y-1.5 text-xs text-zinc-500">
          <li>
            <span className="text-zinc-300">Cloud workspace</span> — files
            created by Plutus in the sandbox are automatically synced here every
            5 minutes
          </li>
          <li>
            <span className="text-zinc-300">Local push</span> — run{" "}
            <code className="text-zinc-400">plutus push</code> or use the local
            settings to upload your local workspace here
          </li>
          <li>
            <span className="text-zinc-300">Local pull</span> — run{" "}
            <code className="text-zinc-400">plutus pull</code> to download cloud
            files to your local machine
          </li>
          <li>
            <span className="text-zinc-300">Packages</span> — installed packages
            are saved as{" "}
            <code className="text-zinc-400">.sandbox_requirements.txt</code> and
            auto-installed when a new sandbox starts
          </li>
        </ul>
      </div>
    </div>
  );
}

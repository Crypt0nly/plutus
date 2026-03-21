import { useState, useEffect, useCallback } from "react";
import {
  Cloud,
  CloudOff,
  Upload,
  Download,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  ToggleLeft,
  ToggleRight,
  Eye,
  EyeOff,
} from "lucide-react";
import { api } from "../../lib/api";

interface SyncConfig {
  url: string;
  token: string;
  auto_sync: boolean;
  auto_sync_interval: number;
  last_push: number;
  last_pull: number;
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

function formatTime(ts: number): string {
  if (!ts) return "Never";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

function formatRelative(ts: number): string {
  if (!ts) return "Never";
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function WorkspaceSyncView() {
  const [config, setConfig] = useState<SyncConfig>({
    url: "",
    token: "",
    auto_sync: false,
    auto_sync_interval: 300,
    last_push: 0,
    last_pull: 0,
  });
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushing, setPushing] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [pushMsg, setPushMsg] = useState("");
  const [pullMsg, setPullMsg] = useState("");

  const loadConfig = useCallback(async () => {
    try {
      const data = await api.getConfig();
      if (data.cloud_sync) {
        setConfig(data.cloud_sync);
      }
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const saveConfig = async () => {
    try {
      await api.updateConfig({ cloud_sync: config });
      setSaveMsg("Saved!");
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e) {
      setSaveMsg("Save failed");
      setTimeout(() => setSaveMsg(""), 3000);
    }
  };

  const fetchStatus = async () => {
    if (!config.url || !config.token) return;
    setStatusLoading(true);
    try {
      const resp = await fetch(`${config.url}/api/workspace/manifest`, {
        headers: { Authorization: `Bearer ${config.token}` },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const remoteFiles: Record<string, { mtime: number }> = {};
      for (const f of data.files || []) {
        remoteFiles[f.path] = f;
      }
      // Get local manifest from local server
      const localResp = await api.getWorkspaceManifest();
      const localFiles: Record<string, { mtime: number }> = {};
      for (const f of localResp.files || []) {
        localFiles[f.path] = f;
      }
      const allPaths = new Set([...Object.keys(localFiles), ...Object.keys(remoteFiles)]);
      let local_only = 0, cloud_only = 0, newer_local = 0, newer_cloud = 0, in_sync = 0;
      for (const p of allPaths) {
        const l = localFiles[p];
        const r = remoteFiles[p];
        if (l && !r) local_only++;
        else if (!l && r) cloud_only++;
        else if (l && r) {
          if (l.mtime > r.mtime + 1) newer_local++;
          else if (r.mtime > l.mtime + 1) newer_cloud++;
          else in_sync++;
        }
      }
      setStatus({
        local_only,
        cloud_only,
        newer_local,
        newer_cloud,
        in_sync,
        total_local: Object.keys(localFiles).length,
        total_cloud: Object.keys(remoteFiles).length,
      });
    } catch (e) {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  };

  const handlePush = async () => {
    if (!config.url || !config.token) {
      setPushMsg("Configure URL and token first");
      setTimeout(() => setPushMsg(""), 3000);
      return;
    }
    setPushing(true);
    setPushMsg("");
    try {
      const resp = await api.workspacePush(config.url, config.token);
      setPushMsg(`✓ Pushed ${resp.uploaded} file(s)`);
      await api.updateConfig({ cloud_sync: { ...config, last_push: Date.now() / 1000 } });
      setConfig((c) => ({ ...c, last_push: Date.now() / 1000 }));
      setTimeout(() => setPushMsg(""), 4000);
    } catch (e: any) {
      setPushMsg(`Push failed: ${e.message || e}`);
      setTimeout(() => setPushMsg(""), 4000);
    } finally {
      setPushing(false);
    }
  };

  const handlePull = async () => {
    if (!config.url || !config.token) {
      setPullMsg("Configure URL and token first");
      setTimeout(() => setPullMsg(""), 3000);
      return;
    }
    setPulling(true);
    setPullMsg("");
    try {
      const resp = await api.workspacePull(config.url, config.token);
      setPullMsg(`✓ Pulled ${resp.downloaded} file(s)`);
      await api.updateConfig({ cloud_sync: { ...config, last_pull: Date.now() / 1000 } });
      setConfig((c) => ({ ...c, last_pull: Date.now() / 1000 }));
      setTimeout(() => setPullMsg(""), 4000);
    } catch (e: any) {
      setPullMsg(`Pull failed: ${e.message || e}`);
      setTimeout(() => setPullMsg(""), 4000);
    } finally {
      setPulling(false);
    }
  };

  const isConfigured = config.url && config.token;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-5 h-5 animate-spin text-zinc-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Cloud className="w-5 h-5 text-cyan-400" />
        <div>
          <h2 className="text-sm font-semibold text-white">Cloud Workspace Sync</h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Keep your local{" "}
            <code className="text-zinc-300">~/plutus-workspace</code> in sync with
            the cloud sandbox
          </p>
        </div>
      </div>

      {/* Connection config */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
        <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
          Connection
        </h3>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Cloud URL</label>
            <input
              type="url"
              value={config.url}
              onChange={(e) => setConfig((c) => ({ ...c, url: e.target.value }))}
              placeholder="https://app.plutus.ai"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-400 mb-1">API Token</label>
            <div className="relative">
              <input
                type={showToken ? "text" : "password"}
                value={config.token}
                onChange={(e) => setConfig((c) => ({ ...c, token: e.target.value }))}
                placeholder="Paste your token from cloud Settings → Workspace"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 pr-10 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500"
              />
              <button
                onClick={() => setShowToken((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
              >
                {showToken ? (
                  <EyeOff className="w-4 h-4" />
                ) : (
                  <Eye className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={saveConfig}
            className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs rounded-lg transition-colors"
          >
            Save
          </button>
          {saveMsg && (
            <span
              className={`text-xs ${saveMsg.includes("failed") ? "text-red-400" : "text-green-400"}`}
            >
              {saveMsg}
            </span>
          )}
        </div>
      </div>

      {/* Auto-sync toggle */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-white">Auto-sync</h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Automatically push changes to the cloud every{" "}
              {Math.round(config.auto_sync_interval / 60)} minutes
            </p>
          </div>
          <button
            onClick={() => {
              const updated = { ...config, auto_sync: !config.auto_sync };
              setConfig(updated);
              api.updateConfig({ cloud_sync: updated });
            }}
            className="text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            {config.auto_sync ? (
              <ToggleRight className="w-8 h-8" />
            ) : (
              <ToggleLeft className="w-8 h-8 text-zinc-500" />
            )}
          </button>
        </div>

        {config.auto_sync && (
          <div className="mt-3 flex items-center gap-3">
            <label className="text-xs text-zinc-400">Interval (minutes)</label>
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
              className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
        )}
      </div>

      {/* Push / Pull actions */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-4">
        <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
          Manual Sync
        </h3>

        <div className="grid grid-cols-2 gap-3">
          {/* Push */}
          <div className="space-y-2">
            <button
              onClick={handlePush}
              disabled={pushing || !isConfigured}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed border border-zinc-700 rounded-xl text-sm text-white transition-colors"
            >
              {pushing ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4 text-cyan-400" />
              )}
              {pushing ? "Pushing…" : "Push to Cloud"}
            </button>
            {config.last_push > 0 && (
              <p className="text-xs text-zinc-500 text-center">
                Last: {formatRelative(config.last_push)}
              </p>
            )}
            {pushMsg && (
              <p
                className={`text-xs text-center ${pushMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}
              >
                {pushMsg}
              </p>
            )}
          </div>

          {/* Pull */}
          <div className="space-y-2">
            <button
              onClick={handlePull}
              disabled={pulling || !isConfigured}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed border border-zinc-700 rounded-xl text-sm text-white transition-colors"
            >
              {pulling ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4 text-emerald-400" />
              )}
              {pulling ? "Pulling…" : "Pull from Cloud"}
            </button>
            {config.last_pull > 0 && (
              <p className="text-xs text-zinc-500 text-center">
                Last: {formatRelative(config.last_pull)}
              </p>
            )}
            {pullMsg && (
              <p
                className={`text-xs text-center ${pullMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}
              >
                {pullMsg}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Sync status */}
      {isConfigured && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              Sync Status
            </h3>
            <button
              onClick={fetchStatus}
              disabled={statusLoading}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white transition-colors"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${statusLoading ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
          </div>

          {status ? (
            <div className="grid grid-cols-2 gap-2">
              {[
                {
                  label: "In sync",
                  value: status.in_sync,
                  color: "text-green-400",
                  icon: <CheckCircle className="w-3.5 h-3.5" />,
                },
                {
                  label: "Local only",
                  value: status.local_only,
                  color: "text-yellow-400",
                  icon: <Upload className="w-3.5 h-3.5" />,
                },
                {
                  label: "Cloud only",
                  value: status.cloud_only,
                  color: "text-blue-400",
                  icon: <Download className="w-3.5 h-3.5" />,
                },
                {
                  label: "Newer locally",
                  value: status.newer_local,
                  color: "text-yellow-400",
                  icon: <Clock className="w-3.5 h-3.5" />,
                },
                {
                  label: "Newer in cloud",
                  value: status.newer_cloud,
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
            <button
              onClick={fetchStatus}
              className="w-full py-3 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Click Refresh to check sync status
            </button>
          )}
        </div>
      )}

      {/* Help */}
      <div className="bg-zinc-900/50 border border-zinc-800/50 rounded-xl p-4">
        <h3 className="text-xs font-semibold text-zinc-400 mb-2">How it works</h3>
        <ul className="space-y-1.5 text-xs text-zinc-500">
          <li>
            <span className="text-zinc-300">Push</span> — uploads your local{" "}
            <code className="text-zinc-400">~/plutus-workspace</code> to the cloud
          </li>
          <li>
            <span className="text-zinc-300">Pull</span> — downloads cloud files to
            your local workspace
          </li>
          <li>
            <span className="text-zinc-300">Auto-sync</span> — automatically pushes
            changes on a schedule
          </li>
          <li>
            <span className="text-zinc-300">Cloud sandbox</span> — files are
            automatically synced to/from the E2B sandbox every 5 minutes
          </li>
          <li>
            Get your API token from{" "}
            <span className="text-zinc-300">cloud Settings → Workspace → API Token</span>
          </li>
        </ul>
      </div>
    </div>
  );
}

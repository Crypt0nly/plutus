import { useEffect, useState, useCallback } from "react";
import { Bot, Server, Database, Info, Sun, Moon, Monitor, BatteryCharging, FileText, ArrowUpCircle, CheckCircle, RefreshCw, ExternalLink, X } from "lucide-react";
import { api } from "../../lib/api";
import { ModelConfig } from "./ModelConfig";
import { HeartbeatConfig } from "./HeartbeatConfig";
import { useAppStore } from "../../stores/appStore";
import { applyTheme, type ThemeMode } from "../../hooks/useTheme";

export function SettingsView() {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});
  const [keepAlive, setKeepAlive] = useState<{ enabled: boolean; active: boolean; platform: string | null } | null>(null);

  const fetchKeyStatus = useCallback(() => {
    api.getKeyStatus().then((data) => {
      setKeyStatus(data.providers || {});
      useAppStore.getState().setKeyConfigured(data.current_provider_configured);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => {});
    fetchKeyStatus();
    api.getKeepAliveStatus().then((d) => setKeepAlive(d as any)).catch(() => {});
  }, [fetchKeyStatus]);

  const handleSave = async (patch: Record<string, any>) => {
    setSaving(true);
    setSaved(false);
    try {
      await api.updateConfig(patch);
      setSaved(true);
      const updated = await api.getConfig();
      setConfig(updated);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      console.error("Failed to save:", e);
    } finally {
      setSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-plutus-500/30 border-t-plutus-500 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-100">Settings</h2>
            <p className="text-sm text-gray-500 mt-1">
              Configure your AI provider, model, and system preferences
            </p>
          </div>
          {saved && (
            <div className="flex items-center gap-2 text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg animate-fade-in">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Saved
            </div>
          )}
        </div>

        {/* Version Banner */}
        <VersionBanner />

        {/* Appearance */}
        <AppearanceSection />

        {/* Coordinator Model + API Keys */}
        <ModelConfig
          config={config.model || {}}
          onSave={(model) => handleSave({ model })}
          saving={saving}
          keyStatus={keyStatus}
          onKeyStatusChange={fetchKeyStatus}
        />

        {/* System Prompt */}
        <SystemPromptEditor
          value={config.agent?.system_prompt || ""}
          onSave={(value) => handleSave({ agent: { system_prompt: value } })}
          saving={saving}
        />

        {/* Heartbeat */}
        <HeartbeatConfig
          config={config.heartbeat || {}}
          onSave={handleSave}
          saving={saving}
        />

        {/* Agent Behavior */}
        <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Bot className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Agent Behavior</h3>
              <p className="text-xs text-gray-500">Control how the coordinator processes tasks</p>
            </div>
          </div>

          <div className="space-y-5">
            {/* Max tool rounds */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm text-gray-300">Max Tool Rounds</label>
                <span className="text-sm font-mono text-plutus-400 bg-plutus-500/10 px-2.5 py-0.5 rounded-md">
                  {config.agent?.max_tool_rounds || 25}
                </span>
              </div>
              <input
                type="range"
                min="5"
                max="100"
                step="5"
                className="w-full accent-plutus-500 h-2 rounded-full"
                defaultValue={config.agent?.max_tool_rounds || 25}
                onChange={(e) =>
                  handleSave({
                    agent: { max_tool_rounds: parseInt(e.target.value) || 25 },
                  })
                }
              />
              <div className="flex justify-between text-[10px] text-gray-600 mt-1.5 px-0.5">
                <span>5</span>
                <span>25</span>
                <span>50</span>
                <span>75</span>
                <span>100</span>
              </div>
              <p className="text-xs text-gray-500 mt-2">
                Maximum tool calls (browser, shell, etc.) per message before the agent pauses.
              </p>
            </div>

            {/* Scheduler toggle */}
            <div className="flex items-center justify-between py-3 border-t border-gray-800/40">
              <div>
                <p className="text-sm text-gray-300">Scheduler</p>
                <p className="text-xs text-gray-500 mt-0.5">Allow Plutus to create and run cron jobs</p>
              </div>
              <button
                onClick={() => handleSave({ scheduler: { enabled: !(config.scheduler?.enabled ?? true) } })}
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 ${
                  config.scheduler?.enabled !== false ? "bg-plutus-500" : "bg-gray-700"
                }`}
              >
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  config.scheduler?.enabled !== false ? "translate-x-6" : "translate-x-1"
                }`} />
              </button>
            </div>

            {/* Keep Alive toggle */}
            <div className="flex items-center justify-between py-3 border-t border-gray-800/40">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                  <BatteryCharging className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <p className="text-sm text-gray-300">Keep Alive</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Prevent system sleep while Plutus is running
                  </p>
                  {keepAlive?.active && (
                    <p className="text-[10px] text-emerald-400 mt-0.5">
                      Active on {keepAlive.platform}
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={async () => {
                  const newEnabled = !(keepAlive?.enabled ?? false);
                  try {
                    const result = await api.setKeepAlive(newEnabled);
                    setKeepAlive(result as any);
                  } catch (e) {
                    console.error("Failed to toggle keep-alive:", e);
                  }
                }}
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 ${
                  keepAlive?.enabled ? "bg-emerald-500" : "bg-gray-700"
                }`}
              >
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  keepAlive?.enabled ? "translate-x-6" : "translate-x-1"
                }`} />
              </button>
            </div>
          </div>
        </div>

        {/* Network & Storage */}
        <div className="grid grid-cols-2 gap-4">
          {/* Gateway */}
          <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <Server className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Gateway</h3>
                <p className="text-xs text-gray-500">Network settings</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Host</label>
                <div className="bg-gray-800/50 rounded-lg px-3 py-2 text-sm text-gray-400 font-mono">
                  {config.gateway?.host || "127.0.0.1"}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Port</label>
                <div className="bg-gray-800/50 rounded-lg px-3 py-2 text-sm text-gray-400 font-mono">
                  {config.gateway?.port || 7777}
                </div>
              </div>
              <div className="flex items-start gap-1.5 pt-1">
                <Info className="w-3 h-3 text-gray-600 mt-0.5 shrink-0" />
                <p className="text-[10px] text-gray-600">Restart Plutus to change these values</p>
              </div>
            </div>
          </div>

          {/* Memory */}
          <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center">
                <Database className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Memory</h3>
                <p className="text-xs text-gray-500">Context & history</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Context Window</label>
                <input
                  type="number"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                  defaultValue={config.memory?.context_window_messages || 20}
                  onChange={(e) =>
                    handleSave({
                      memory: { context_window_messages: parseInt(e.target.value) || 20 },
                    })
                  }
                />
                <p className="text-[10px] text-gray-600 mt-1">Messages kept in active context</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Max History</label>
                <input
                  type="number"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                  defaultValue={config.memory?.max_conversation_history || 100}
                  onChange={(e) =>
                    handleSave({
                      memory: { max_conversation_history: parseInt(e.target.value) || 100 },
                    })
                  }
                />
                <p className="text-[10px] text-gray-600 mt-1">Total messages stored per conversation</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Auto-Delete After (days)</label>
                <input
                  type="number"
                  min="0"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                  defaultValue={config.memory?.conversation_auto_delete_days ?? 30}
                  onChange={(e) =>
                    handleSave({
                      memory: { conversation_auto_delete_days: parseInt(e.target.value) || 0 },
                    })
                  }
                />
                <p className="text-[10px] text-gray-600 mt-1">
                  Conversations with no activity for this many days are automatically deleted. Set to 0 to disable.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SystemPromptEditor({
  value,
  onSave,
  saving,
}: {
  value: string;
  onSave: (value: string) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setDraft(value);
    setDirty(false);
  }, [value]);

  const handleChange = (text: string) => {
    setDraft(text);
    setDirty(text !== value);
  };

  const handleSave = () => {
    onSave(draft);
    setDirty(false);
  };

  const handleClear = () => {
    setDraft("");
    onSave("");
    setDirty(false);
  };

  return (
    <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-rose-500/10 flex items-center justify-center">
            <FileText className="w-5 h-5 text-rose-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">System Prompt</h3>
            <p className="text-xs text-gray-500">
              Custom instructions appended to the default system prompt
            </p>
          </div>
        </div>
        {dirty && (
          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
            Unsaved
          </span>
        )}
      </div>

      <textarea
        rows={8}
        placeholder="e.g. Always respond in Spanish. Prefer Python over JavaScript. Never delete files without asking first..."
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2.5 text-sm text-gray-300 placeholder-gray-600 font-mono leading-relaxed resize-y focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 min-h-[120px]"
      />

      <div className="flex items-center justify-between mt-3">
        <p className="text-[10px] text-gray-600">
          These instructions are added under a "User Instructions" section in every conversation.
        </p>
        <div className="flex items-center gap-2">
          {draft && (
            <button
              onClick={handleClear}
              className="text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-800/50 transition-colors"
            >
              Clear
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!dirty || saving}
            className={`text-xs font-medium px-4 py-1.5 rounded-lg transition-colors ${
              dirty && !saving
                ? "bg-plutus-500 text-white hover:bg-plutus-600"
                : "bg-gray-800/50 text-gray-600 cursor-not-allowed"
            }`}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

const themeOptions: { value: ThemeMode; label: string; icon: React.ElementType; description: string }[] = [
  { value: "light", label: "Light", icon: Sun, description: "Always use light theme" },
  { value: "dark", label: "Dark", icon: Moon, description: "Always use dark theme" },
  { value: "system", label: "System", icon: Monitor, description: "Follow your OS setting" },
];

function AppearanceSection() {
  const { theme, setTheme } = useAppStore();

  const handleChange = (mode: ThemeMode) => {
    setTheme(mode);
    applyTheme(mode);
  };

  return (
    <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-lg bg-plutus-500/10 flex items-center justify-center">
          <Sun className="w-5 h-5 text-plutus-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-200">Appearance</h3>
          <p className="text-xs text-gray-500">Choose your preferred color theme</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {themeOptions.map((opt) => {
          const Icon = opt.icon;
          const active = theme === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => handleChange(opt.value)}
              className={`flex flex-col items-center gap-2.5 p-4 rounded-xl border transition-all duration-150 ${
                active
                  ? "border-plutus-500/40 bg-plutus-500/10 ring-1 ring-plutus-500/20"
                  : "border-gray-800/60 hover:border-gray-700 hover:bg-gray-800/40"
              }`}
            >
              <Icon className={`w-5 h-5 ${active ? "text-plutus-400" : "text-gray-500"}`} />
              <div className="text-center">
                <span className={`text-xs font-medium block ${active ? "text-gray-100" : "text-gray-400"}`}>
                  {opt.label}
                </span>
                <span className="text-[10px] text-gray-500 mt-0.5 block">{opt.description}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

interface UpdateInfo {
  update_available: boolean;
  dismissed?: boolean;
  current_version: string;
  latest_version: string;
  release_name?: string;
  release_notes?: string;
  release_url?: string;
  published_at?: string;
  error?: string;
}

function VersionBanner() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [updateResult, setUpdateResult] = useState<{ success: boolean; new_version?: string; error?: string } | null>(null);
  const [showNotes, setShowNotes] = useState(false);

  const checkUpdate = useCallback(async () => {
    setChecking(true);
    try {
      const data = await api.checkForUpdate();
      setInfo(data);
    } catch {
      setInfo(null);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    checkUpdate();
  }, [checkUpdate]);

  const handleUpdate = async () => {
    setUpdating(true);
    setUpdateResult(null);
    try {
      const result = await api.applyUpdate();
      setUpdateResult(result);
      if (result.success) {
        // Re-check to reflect new version
        setTimeout(checkUpdate, 2000);
      }
    } catch (e) {
      setUpdateResult({ success: false, error: String(e) });
    } finally {
      setUpdating(false);
    }
  };

  const handleDismiss = async () => {
    if (!info) return;
    try {
      await api.dismissUpdate(info.latest_version);
      setInfo((prev) => prev ? { ...prev, dismissed: true } : prev);
    } catch {
      // ignore
    }
  };

  // Loading state
  if (checking && !info) {
    return (
      <div className="bg-surface rounded-xl border border-gray-800/60 p-4">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-gray-600 border-t-gray-400 rounded-full animate-spin" />
          <span className="text-sm text-gray-500">Checking version...</span>
        </div>
      </div>
    );
  }

  if (!info) return null;

  const hasUpdate = info.update_available && !info.dismissed;

  return (
    <div
      className={`rounded-xl border p-4 ${
        hasUpdate
          ? "bg-plutus-500/5 border-plutus-500/30"
          : "bg-surface border-gray-800/60"
      }`}
    >
      {/* Version row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`w-9 h-9 rounded-lg flex items-center justify-center ${
              hasUpdate ? "bg-plutus-500/15" : "bg-gray-800/60"
            }`}
          >
            {hasUpdate ? (
              <ArrowUpCircle className="w-5 h-5 text-plutus-400" />
            ) : (
              <CheckCircle className="w-5 h-5 text-emerald-400" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-200">
                Plutus v{info.current_version}
              </span>
              {hasUpdate && (
                <span className="text-[10px] font-medium text-plutus-400 bg-plutus-500/15 px-2 py-0.5 rounded-full">
                  v{info.latest_version} available
                </span>
              )}
              {!hasUpdate && !info.update_available && (
                <span className="text-[10px] text-emerald-400/70">Up to date</span>
              )}
              {info.dismissed && (
                <span className="text-[10px] text-gray-600">Update dismissed</span>
              )}
            </div>
            {hasUpdate && info.release_name && (
              <p className="text-xs text-gray-500 mt-0.5">{info.release_name}</p>
            )}
            {hasUpdate && info.published_at && (
              <p className="text-[10px] text-gray-600 mt-0.5">
                Released {new Date(info.published_at).toLocaleDateString()}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Check again */}
          <button
            onClick={checkUpdate}
            disabled={checking}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition-colors"
            title="Check for updates"
          >
            <RefreshCw className={`w-4 h-4 ${checking ? "animate-spin" : ""}`} />
          </button>

          {hasUpdate && (
            <>
              {/* View release notes */}
              {info.release_notes && (
                <button
                  onClick={() => setShowNotes(!showNotes)}
                  className="text-xs text-gray-400 hover:text-gray-200 px-2.5 py-1.5 rounded-lg hover:bg-gray-800/50 transition-colors"
                >
                  {showNotes ? "Hide notes" : "Release notes"}
                </button>
              )}

              {/* Release link */}
              {info.release_url && (
                <a
                  href={info.release_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition-colors"
                  title="View on GitHub"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}

              {/* Dismiss */}
              <button
                onClick={handleDismiss}
                className="p-1.5 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-gray-800/50 transition-colors"
                title="Dismiss this update"
              >
                <X className="w-4 h-4" />
              </button>

              {/* Update button */}
              <button
                onClick={handleUpdate}
                disabled={updating}
                className="flex items-center gap-1.5 text-xs font-medium px-4 py-1.5 rounded-lg bg-plutus-500 text-white hover:bg-plutus-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {updating ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Updating...
                  </>
                ) : (
                  <>
                    <ArrowUpCircle className="w-3.5 h-3.5" />
                    Update
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Release notes expandable */}
      {showNotes && info.release_notes && (
        <div className="mt-3 pt-3 border-t border-gray-800/40">
          <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed max-h-60 overflow-y-auto">
            {info.release_notes}
          </pre>
        </div>
      )}

      {/* Update result */}
      {updateResult && (
        <div
          className={`mt-3 pt-3 border-t border-gray-800/40 text-xs ${
            updateResult.success ? "text-emerald-400" : "text-red-400"
          }`}
        >
          {updateResult.success ? (
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4" />
              <span>
                Updated to v{updateResult.new_version}. Restart Plutus to apply changes.
              </span>
            </div>
          ) : (
            <span>Update failed: {updateResult.error}</span>
          )}
        </div>
      )}

      {/* Error */}
      {info.error && (
        <p className="text-[10px] text-gray-600 mt-2">
          Could not check for updates: {info.error}
        </p>
      )}
    </div>
  );
}

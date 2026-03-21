import { useEffect, useState, useCallback, useRef } from "react";
import { Bot, Server, Database, Info, Sun, Moon, Monitor, BatteryCharging, FileText, ArrowUpCircle, CheckCircle, RefreshCw, ExternalLink, X, Minus, Plus, Check, Globe, Cloud } from "lucide-react";
import WorkspaceSyncView from "./WorkspaceSyncView";
import { api } from "../../lib/api";
import { ModelConfig } from "./ModelConfig";
import { HeartbeatConfig } from "./HeartbeatConfig";
import { BrowserConfig } from "./BrowserConfig";
import { useAppStore } from "../../stores/appStore";
import { applyTheme, type ThemeMode } from "../../hooks/useTheme";

/* ═══════════════════════════════════════════════════════════
   Reusable UI Components
   ═══════════════════════════════════════════════════════════ */

/** Custom slider with filled track */
function PlutusSlider({
  min,
  max,
  step,
  value,
  onChange,
}: {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
}) {
  const fill = ((value - min) / (max - min)) * 100;
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value))}
      className="plutus-slider w-full"
      style={{ "--slider-fill": `${fill}%` } as React.CSSProperties}
    />
  );
}

/** Custom toggle switch */
function ToggleSwitch({
  enabled,
  onChange,
  variant = "default",
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  variant?: "default" | "emerald" | "amber";
}) {
  const variantClass = variant === "emerald"
    ? "toggle-switch-emerald"
    : variant === "amber"
    ? "toggle-switch-amber"
    : "";

  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`toggle-switch ${variantClass}`}
      data-state={enabled ? "on" : "off"}
      role="switch"
      aria-checked={enabled}
    >
      <span className="toggle-thumb" />
    </button>
  );
}

/** Number input with stepper buttons */
function NumberStepper({
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  const clamp = (v: number) => {
    if (min !== undefined && v < min) return min;
    if (max !== undefined && v > max) return max;
    return v;
  };

  return (
    <div className="number-input-group h-10">
      <button
        onClick={() => onChange(clamp(value - step))}
        className="px-2"
        disabled={min !== undefined && value <= min}
      >
        <Minus className="w-3.5 h-3.5" />
      </button>
      <input
        type="number"
        value={value}
        onChange={(e) => {
          const v = parseInt(e.target.value);
          if (!isNaN(v)) onChange(clamp(v));
        }}
        min={min}
        max={max}
        step={step}
        className="text-sm text-gray-200 py-2 w-20"
      />
      {suffix && <span className="text-xs text-gray-500 pr-1">{suffix}</span>}
      <button
        onClick={() => onChange(clamp(value + step))}
        className="px-2"
        disabled={max !== undefined && value >= max}
      >
        <Plus className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   Main Settings View
   ═══════════════════════════════════════════════════════════ */

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

  const maxToolRounds = config.agent?.max_tool_rounds || 25;
  const schedulerEnabled = config.scheduler?.enabled !== false;

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
              <Check className="w-4 h-4" />
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
        <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
          <div className="flex items-center gap-3 mb-5">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(168, 85, 247, 0.08)", border: "1px solid rgba(168, 85, 247, 0.12)" }}>
              <Bot className="w-4 h-4 text-purple-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Agent Behavior</h3>
              <p className="text-xs text-gray-500">Control how the coordinator processes tasks</p>
            </div>
          </div>

          <div className="space-y-5">
            {/* Max tool rounds — custom slider */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm text-gray-300">Max Tool Rounds</label>
                <span className="text-sm font-mono text-plutus-400 bg-plutus-500/10 px-2.5 py-0.5 rounded-md min-w-[3rem] text-center">
                  {maxToolRounds}
                </span>
              </div>
              <PlutusSlider
                min={5}
                max={100}
                step={5}
                value={maxToolRounds}
                onChange={(v) =>
                  handleSave({ agent: { max_tool_rounds: v } })
                }
              />
              <div className="flex justify-between text-[10px] text-gray-600 mt-2 px-0.5">
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

            {/* Scheduler toggle — custom toggle */}
            <div className="flex items-center justify-between py-3" style={{ borderTop: "1px solid rgb(var(--gray-700) / 0.3)" }}>
              <div>
                <p className="text-sm text-gray-300">Scheduler</p>
                <p className="text-xs text-gray-500 mt-0.5">Allow Plutus to create and run cron jobs</p>
              </div>
              <ToggleSwitch
                enabled={schedulerEnabled}
                onChange={(v) => handleSave({ scheduler: { enabled: v } })}
              />
            </div>

            {/* Keep Alive toggle — custom toggle */}
            <div className="flex items-center justify-between py-3" style={{ borderTop: "1px solid rgb(var(--gray-700) / 0.3)" }}>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.12)" }}>
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
              <ToggleSwitch
                enabled={keepAlive?.enabled ?? false}
                onChange={async (v) => {
                  try {
                    const result = await api.setKeepAlive(v);
                    setKeepAlive(result as any);
                  } catch (e) {
                    console.error("Failed to toggle keep-alive:", e);
                  }
                }}
                variant="emerald"
              />
            </div>
          </div>
        </div>

        {/* Browser */}
        <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
          <div className="flex items-center gap-3 mb-5">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.12)" }}>
              <Globe className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Browser</h3>
              <p className="text-xs text-gray-500">Choose which browser Plutus uses for web tasks</p>
            </div>
          </div>
          <BrowserConfig
            config={config.browser || { mode: "auto", executable_path: "", cdp_port: 9222, use_profile: true }}
            onUpdate={handleSave}
          />
        </div>

        {/* Network & Storage */}
        <div className="grid grid-cols-2 gap-4">
          {/* Gateway */}
          <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.12)" }}>
                <Server className="w-4 h-4 text-blue-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Gateway</h3>
                <p className="text-xs text-gray-500">Network settings</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Host</label>
                <div className="bg-gray-800/50 rounded-lg px-3 py-2 text-sm text-gray-400 font-mono border border-gray-700/30">
                  {config.gateway?.host || "127.0.0.1"}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1 block">Port</label>
                <div className="bg-gray-800/50 rounded-lg px-3 py-2 text-sm text-gray-400 font-mono border border-gray-700/30">
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
          <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.12)" }}>
                <Database className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Memory</h3>
                <p className="text-xs text-gray-500">Context & history</p>
              </div>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500 mb-1.5 block">Context Window</label>
                <NumberStepper
                  value={config.memory?.context_window_messages || 20}
                  onChange={(v) =>
                    handleSave({ memory: { context_window_messages: v } })
                  }
                  min={5}
                  max={100}
                  step={5}
                  suffix="msgs"
                />
                <p className="text-[10px] text-gray-600 mt-1.5">Messages kept in active context</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1.5 block">Max History</label>
                <NumberStepper
                  value={config.memory?.max_conversation_history || 100}
                  onChange={(v) =>
                    handleSave({ memory: { max_conversation_history: v } })
                  }
                  min={10}
                  max={1000}
                  step={10}
                  suffix="msgs"
                />
                <p className="text-[10px] text-gray-600 mt-1.5">Total messages stored per conversation</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 mb-1.5 block">Auto-Delete After</label>
                <NumberStepper
                  value={config.memory?.conversation_auto_delete_days ?? 30}
                  onChange={(v) =>
                    handleSave({ memory: { conversation_auto_delete_days: v } })
                  }
                  min={0}
                  max={365}
                  step={1}
                  suffix="days"
                />
                <p className="text-[10px] text-gray-600 mt-1.5">
                  Conversations with no activity are auto-deleted. 0 = disabled.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Cloud Workspace Sync */}
      <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(6, 182, 212, 0.08)", border: "1px solid rgba(6, 182, 212, 0.12)" }}>
            <Cloud className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Cloud Sync</h3>
            <p className="text-xs text-gray-500">Sync your workspace with the cloud version</p>
          </div>
        </div>
        <WorkspaceSyncView />
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
    <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(244, 63, 94, 0.08)", border: "1px solid rgba(244, 63, 94, 0.12)" }}>
            <FileText className="w-4 h-4 text-rose-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">System Prompt</h3>
            <p className="text-xs text-gray-500">
              Custom instructions appended to the default system prompt
            </p>
          </div>
        </div>
        {dirty && (
          <span className="text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full animate-fade-in">
            Unsaved
          </span>
        )}
      </div>

      <textarea
        rows={8}
        placeholder="e.g. Always respond in Spanish. Prefer Python over JavaScript. Never delete files without asking first..."
        value={draft}
        onChange={(e) => handleChange(e.target.value)}
        className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-3 text-sm text-gray-300 placeholder-gray-600 font-mono leading-relaxed resize-y focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 min-h-[120px] transition-all duration-200"
      />

      <div className="flex items-center justify-between mt-3">
        <p className="text-[10px] text-gray-600">
          These instructions are added under a "User Instructions" section in every conversation.
        </p>
        <div className="flex items-center gap-2">
          {draft && (
            <button
              onClick={handleClear}
              className="text-xs text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-800/50 transition-all duration-200"
            >
              Clear
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={!dirty || saving}
            className={`text-xs font-medium px-4 py-1.5 rounded-lg transition-all duration-200 ${
              dirty && !saving
                ? "bg-plutus-500 text-white hover:bg-plutus-600 shadow-sm shadow-plutus-500/20 active:scale-[0.97]"
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
    <div className="rounded-2xl p-5" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.12)" }}>
          <Sun className="w-4 h-4 text-plutus-400" />
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
              className="selector-card relative flex flex-col items-center gap-2.5 p-4 rounded-xl transition-all duration-200"
              style={active ? { background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.3)", boxShadow: "0 0 16px rgba(99, 102, 241, 0.1)" } : { background: "rgb(var(--gray-800) / 0.5)", border: "1px solid rgb(var(--gray-700) / 0.4)" }}
              data-active={active}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-200"
                style={active ? { background: "rgba(99, 102, 241, 0.12)" } : { background: "rgb(var(--gray-800) / 0.6)" }}
              >
                <Icon className={`w-5 h-5 transition-all duration-200 ${
                  active ? "text-plutus-400 scale-110" : "text-gray-600"
                }`} />
              </div>
              <div className="text-center">
                <span className={`text-xs font-medium block transition-colors ${active ? "text-gray-100" : "text-gray-400"}`}>
                  {opt.label}
                </span>
                <span className="text-[10px] text-gray-500 mt-0.5 block">{opt.description}</span>
              </div>
              {active && (
                <div className="absolute top-2 right-2 w-4 h-4 rounded-full flex items-center justify-center" style={{ background: "rgba(99, 102, 241, 0.2)" }}>
                  <Check className="w-2.5 h-2.5 text-plutus-400" />
                </div>
              )}
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
      <div className="rounded-2xl p-4" style={{ background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}>
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
      className="rounded-2xl p-4 transition-all duration-200"
    style={hasUpdate ? { background: "rgba(99, 102, 241, 0.06)", border: "1px solid rgba(99, 102, 241, 0.2)" } : { background: "rgb(var(--surface-alt))", border: "1px solid rgb(var(--gray-700) / 0.4)" }}
    >
      {/* Version row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200"
          style={hasUpdate ? { background: "rgba(99, 102, 241, 0.12)", border: "1px solid rgba(99, 102, 241, 0.15)" } : { background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgba(255,255,255,0.07)" }}
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
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition-all duration-200"
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
                  className="text-xs text-gray-400 hover:text-gray-200 px-2.5 py-1.5 rounded-lg hover:bg-gray-800/50 transition-all duration-200"
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
                  className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800/50 transition-all duration-200"
                  title="View on GitHub"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}

              {/* Dismiss */}
              <button
                onClick={handleDismiss}
                className="p-1.5 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-gray-800/50 transition-all duration-200"
                title="Dismiss this update"
              >
                <X className="w-4 h-4" />
              </button>

              {/* Update button */}
              <button
                onClick={handleUpdate}
                disabled={updating}
                className="flex items-center gap-1.5 text-xs font-medium px-4 py-1.5 rounded-lg bg-plutus-500 text-white hover:bg-plutus-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm shadow-plutus-500/20 active:scale-[0.97]"
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
        <div className="mt-3 pt-3 animate-fade-in" style={{ borderTop: "1px solid rgb(var(--gray-700) / 0.3)" }}>
          <pre className="text-xs text-gray-400 whitespace-pre-wrap font-mono leading-relaxed max-h-60 overflow-y-auto">
            {info.release_notes}
          </pre>
        </div>
      )}

      {/* Update result */}
      {updateResult && (
        <div
          className={`mt-3 pt-3 border-t border-gray-800/40 text-xs animate-fade-in ${
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

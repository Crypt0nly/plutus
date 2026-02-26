import { useEffect, useState, useCallback } from "react";
import { Bot, Server, Database, Info } from "lucide-react";
import { api } from "../../lib/api";
import { ModelConfig } from "./ModelConfig";
import { HeartbeatConfig } from "./HeartbeatConfig";
import { WSLSetup } from "./WSLSetup";
import { useAppStore } from "../../stores/appStore";

export function SettingsView() {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});

  const fetchKeyStatus = useCallback(() => {
    api.getKeyStatus().then((data) => {
      setKeyStatus(data.providers || {});
      useAppStore.getState().setKeyConfigured(data.current_provider_configured);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => {});
    fetchKeyStatus();
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

        {/* Coordinator Model + API Keys */}
        <ModelConfig
          config={config.model || {}}
          onSave={(model) => handleSave({ model })}
          saving={saving}
          keyStatus={keyStatus}
          onKeyStatusChange={fetchKeyStatus}
        />

        {/* Heartbeat */}
        <HeartbeatConfig
          config={config.heartbeat || {}}
          onSave={handleSave}
          saving={saving}
        />

        {/* WSL / Linux Superpowers */}
        <WSLSetup />

        {/* Agent Behavior */}
        <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
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
          </div>
        </div>

        {/* Network & Storage */}
        <div className="grid grid-cols-2 gap-4">
          {/* Gateway */}
          <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
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
          <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
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

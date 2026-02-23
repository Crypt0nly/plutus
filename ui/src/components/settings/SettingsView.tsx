import { useEffect, useState, useCallback } from "react";
import { Save, Key, Brain, Server, Database, Bot, Cpu, Calendar } from "lucide-react";
import { api } from "../../lib/api";
import { ModelConfig } from "./ModelConfig";
import { HeartbeatConfig } from "./HeartbeatConfig";
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
      // Refresh config
      const updated = await api.getConfig();
      setConfig(updated);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error("Failed to save:", e);
    } finally {
      setSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-gray-500">Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-100 mb-1">Settings</h2>
          <p className="text-sm text-gray-500">
            Configure your LLM provider, API key, and system settings
          </p>
        </div>
        {saved && (
          <span className="text-sm text-emerald-400 animate-fade-in">
            Settings saved
          </span>
        )}
      </div>

      {/* Model + API Key Configuration */}
      <ModelConfig
        config={config.model || {}}
        onSave={(model) => handleSave({ model })}
        saving={saving}
        keyStatus={keyStatus}
        onKeyStatusChange={fetchKeyStatus}
      />

      {/* Heartbeat Configuration */}
      <HeartbeatConfig
        config={config.heartbeat || {}}
        onSave={handleSave}
        saving={saving}
      />

      {/* Workers & Automation */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-plutus-400" />
          Workers & Automation
        </h3>
        <div className="space-y-5">
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">
              Max Concurrent Workers ({config.workers?.max_concurrent_workers || 3})
            </label>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              className="w-full accent-plutus-500"
              defaultValue={config.workers?.max_concurrent_workers || 3}
              onChange={(e) => {
                handleSave({
                  workers: { max_concurrent_workers: parseInt(e.target.value) || 3 },
                });
                api.updateWorkerConfig({ max_concurrent_workers: parseInt(e.target.value) || 3 }).catch(() => {});
              }}
            />
            <div className="flex justify-between text-[10px] text-gray-600 mt-1">
              <span>1</span>
              <span>3</span>
              <span>5</span>
              <span>7</span>
              <span>10</span>
            </div>
            <p className="text-[10px] text-gray-600 mt-2">
              Maximum number of AI workers that can run simultaneously. Higher values
              allow more parallel tasks but increase API costs. Each worker uses its own
              LLM context.
            </p>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-300">Scheduler Enabled</p>
              <p className="text-[10px] text-gray-500">Allow Plutus to create and run scheduled (cron) jobs</p>
            </div>
            <button
              onClick={() => handleSave({ scheduler: { enabled: !(config.scheduler?.enabled ?? true) } })}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                config.scheduler?.enabled !== false ? "bg-plutus-500" : "bg-gray-700"
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                config.scheduler?.enabled !== false ? "translate-x-5" : "translate-x-0.5"
              }`} />
            </button>
          </div>
        </div>
      </div>

      {/* Agent settings */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Bot className="w-4 h-4 text-plutus-400" />
          Agent
        </h3>
        <div>
          <label className="text-xs text-gray-500 mb-1.5 block">
            Max tool rounds per message ({config.agent?.max_tool_rounds || 25})
          </label>
          <input
            type="range"
            min="5"
            max="100"
            step="5"
            className="w-full accent-plutus-500"
            defaultValue={config.agent?.max_tool_rounds || 25}
            onChange={(e) =>
              handleSave({
                agent: { max_tool_rounds: parseInt(e.target.value) || 25 },
              })
            }
          />
          <div className="flex justify-between text-[10px] text-gray-600 mt-1">
            <span>5</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100</span>
          </div>
          <p className="text-[10px] text-gray-600 mt-2">
            How many external tool calls (browser, shell, etc.) the agent can
            make before stopping. Plan tool calls don't count toward this limit.
          </p>
        </div>
      </div>

      {/* Gateway settings */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Server className="w-4 h-4 text-plutus-400" />
          Gateway
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Host</label>
            <input
              type="text"
              className="input"
              defaultValue={config.gateway?.host || "127.0.0.1"}
              readOnly
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Port</label>
            <input
              type="number"
              className="input"
              defaultValue={config.gateway?.port || 7777}
              readOnly
            />
          </div>
        </div>
        <p className="text-xs text-gray-600 mt-2">
          Restart Plutus to change gateway settings.
        </p>
      </div>

      {/* Memory settings */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Database className="w-4 h-4 text-plutus-400" />
          Memory
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">
              Context Window (messages)
            </label>
            <input
              type="number"
              className="input"
              defaultValue={config.memory?.context_window_messages || 20}
              onChange={(e) =>
                handleSave({
                  memory: {
                    context_window_messages: parseInt(e.target.value) || 20,
                  },
                })
              }
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">
              Max History
            </label>
            <input
              type="number"
              className="input"
              defaultValue={config.memory?.max_conversation_history || 100}
              onChange={(e) =>
                handleSave({
                  memory: {
                    max_conversation_history: parseInt(e.target.value) || 100,
                  },
                })
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState, useCallback } from "react";
import { Save, Key, Brain, Server, Database } from "lucide-react";
import { api } from "../../lib/api";
import { ModelConfig } from "./ModelConfig";
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

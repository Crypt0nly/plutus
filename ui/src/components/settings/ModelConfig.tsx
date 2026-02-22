import { useState } from "react";
import { Brain, Save, Key, Eye, EyeOff, CheckCircle2, AlertTriangle, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

interface Props {
  config: Record<string, any>;
  onSave: (model: Record<string, any>) => void;
  saving: boolean;
  keyStatus: Record<string, boolean>;
  onKeyStatusChange: () => void;
}

const providers = [
  { id: "anthropic", label: "Anthropic (Claude)", envVar: "ANTHROPIC_API_KEY" },
  { id: "openai", label: "OpenAI (GPT)", envVar: "OPENAI_API_KEY" },
  { id: "ollama", label: "Ollama (Local)", envVar: "" },
  { id: "custom", label: "Custom Endpoint", envVar: "API_KEY" },
];

const defaultModels: Record<string, string[]> = {
  anthropic: [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
  ],
  openai: [
    "gpt-5.2",
    "gpt-5",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o3",
    "o4-mini",
    "o3-mini",
  ],
  ollama: ["llama3.2", "mistral", "codellama", "phi3"],
};

export function ModelConfig({ config, onSave, saving, keyStatus, onKeyStatusChange }: Props) {
  const [provider, setProvider] = useState(config.provider || "anthropic");
  const [model, setModel] = useState(config.model || "");
  const [baseUrl, setBaseUrl] = useState(config.base_url || "");
  const [temperature, setTemperature] = useState(config.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens ?? 4096);

  // API key state
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [keySaved, setKeySaved] = useState(false);

  const hasKey = keyStatus[provider] ?? false;
  const needsKey = provider !== "ollama";

  const handleSave = () => {
    const providerInfo = providers.find((p) => p.id === provider);
    onSave({
      provider,
      model,
      api_key_env: providerInfo?.envVar || config.api_key_env,
      base_url: baseUrl || null,
      temperature,
      max_tokens: maxTokens,
    });
  };

  const handleSaveKey = async () => {
    if (!apiKey.trim()) return;
    setSavingKey(true);
    setKeySaved(false);
    try {
      const result = await api.setKey(provider, apiKey.trim());
      setKeySaved(true);
      setApiKey("");
      setShowKey(false);
      onKeyStatusChange();
      if (result.key_configured) {
        useAppStore.getState().setKeyConfigured(true);
      }
      setTimeout(() => setKeySaved(false), 3000);
    } catch (e) {
      console.error("Failed to save key:", e);
    } finally {
      setSavingKey(false);
    }
  };

  const handleDeleteKey = async () => {
    try {
      await api.deleteKey(provider);
      onKeyStatusChange();
    } catch (e) {
      console.error("Failed to delete key:", e);
    }
  };

  const models = defaultModels[provider] || [];

  return (
    <div className="space-y-4">
      {/* Model settings card */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Brain className="w-4 h-4 text-plutus-400" />
          LLM Model
        </h3>

        <div className="space-y-4">
          {/* Provider */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                const defaults = defaultModels[e.target.value];
                if (defaults?.length) setModel(defaults[0]);
                setApiKey("");
                setKeySaved(false);
              }}
              className="input"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          {/* Model */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">Model</label>
            {models.length > 0 ? (
              <select value={model} onChange={(e) => setModel(e.target.value)} className="input">
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
                <option value="">Custom...</option>
              </select>
            ) : (
              <input
                type="text"
                className="input"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="Enter model name"
              />
            )}
            {model === "" && models.length > 0 && (
              <input
                type="text"
                className="input mt-2"
                placeholder="Custom model name"
                onChange={(e) => setModel(e.target.value)}
              />
            )}
          </div>

          {/* Base URL (for custom/ollama) */}
          {(provider === "custom" || provider === "ollama") && (
            <div>
              <label className="text-xs text-gray-500 mb-1.5 block">Base URL</label>
              <input
                type="text"
                className="input"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={
                  provider === "ollama"
                    ? "http://localhost:11434"
                    : "https://your-api-endpoint.com/v1"
                }
              />
            </div>
          )}

          {/* Temperature and Max Tokens */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-500 mb-1.5 block">
                Temperature ({temperature})
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-plutus-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1.5 block">
                Max Tokens
              </label>
              <input
                type="number"
                className="input"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
              />
            </div>
          </div>

          {/* Save model settings */}
          <button onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2">
            <Save className="w-4 h-4" />
            {saving ? "Saving..." : "Save Model Settings"}
          </button>
        </div>
      </div>

      {/* API Key card */}
      {needsKey && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <Key className="w-4 h-4 text-plutus-400" />
            API Key
            {hasKey ? (
              <span className="flex items-center gap-1 text-xs text-emerald-400 font-normal ml-auto">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Configured
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-amber-400 font-normal ml-auto">
                <AlertTriangle className="w-3.5 h-3.5" />
                Not set
              </span>
            )}
          </h3>

          <div className="space-y-3">
            {/* Key input */}
            <div>
              <label className="text-xs text-gray-500 mb-1.5 block">
                {hasKey ? "Update API key" : "Enter your API key"}
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showKey ? "text" : "password"}
                    className="input pr-10"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={hasKey ? "Enter new key to update..." : "sk-..."}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveKey();
                    }}
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 p-1"
                  >
                    {showKey ? (
                      <EyeOff className="w-4 h-4" />
                    ) : (
                      <Eye className="w-4 h-4" />
                    )}
                  </button>
                </div>
                <button
                  onClick={handleSaveKey}
                  disabled={savingKey || !apiKey.trim()}
                  className="btn-primary flex items-center gap-1.5 whitespace-nowrap"
                >
                  <Key className="w-4 h-4" />
                  {savingKey ? "Saving..." : "Save Key"}
                </button>
              </div>
            </div>

            {/* Success message */}
            {keySaved && (
              <p className="text-xs text-emerald-400 animate-fade-in flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                API key saved securely
              </p>
            )}

            {/* Delete key button */}
            {hasKey && (
              <button
                onClick={handleDeleteKey}
                className="btn-danger flex items-center gap-1.5 text-xs py-1.5 px-3"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Remove stored key
              </button>
            )}

            {/* Help text */}
            <p className="text-xs text-gray-600">
              Your API key is stored locally in ~/.plutus/.secrets.json and never leaves your machine.
              You can also set the environment variable instead.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { Brain, Save, Key, Eye, EyeOff, CheckCircle2, AlertTriangle, Trash2, Check, Minus, Plus } from "lucide-react";
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
  { id: "anthropic", label: "Anthropic", sublabel: "Claude", icon: "A", color: "from-orange-500 to-amber-600" },
  { id: "openai", label: "OpenAI", sublabel: "GPT", icon: "O", color: "from-emerald-500 to-teal-600" },
  { id: "ollama", label: "Ollama", sublabel: "Local", icon: "L", color: "from-blue-500 to-indigo-600" },
  { id: "custom", label: "Custom", sublabel: "Endpoint", icon: "C", color: "from-gray-500 to-gray-600" },
];

const providerEnvVars: Record<string, string> = {
  anthropic: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  ollama: "",
  custom: "API_KEY",
};

const defaultModels: Record<string, { id: string; label: string; desc: string }[]> = {
  anthropic: [
    { id: "claude-opus-4-6", label: "Claude Opus 4-6", desc: "Most capable — complex reasoning & analysis" },
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4-6", desc: "Balanced — great for most tasks" },
    { id: "claude-haiku-4-5", label: "Claude Haiku 4-5", desc: "Fast & efficient — simple tasks" },
  ],
  openai: [
    { id: "gpt-5.4", label: "GPT-5.4", desc: "Latest — native computer use support" },
    { id: "gpt-5.2", label: "GPT-5.2", desc: "Flagship model" },
    { id: "gpt-5", label: "GPT-5", desc: "Previous generation flagship" },
    { id: "gpt-4.1", label: "GPT-4.1", desc: "Reliable general purpose" },
    { id: "gpt-4.1-mini", label: "GPT-4.1 Mini", desc: "Fast & affordable" },
    { id: "o3", label: "o3", desc: "Advanced reasoning" },
    { id: "o4-mini", label: "o4-mini", desc: "Fast reasoning" },
  ],
  ollama: [
    { id: "llama3.2", label: "Llama 3.2", desc: "Meta's open model" },
    { id: "mistral", label: "Mistral", desc: "Efficient open model" },
    { id: "codellama", label: "Code Llama", desc: "Optimized for code" },
    { id: "phi3", label: "Phi-3", desc: "Microsoft's compact model" },
  ],
};

export function ModelConfig({ config, onSave, saving, keyStatus, onKeyStatusChange }: Props) {
  const [provider, setProvider] = useState(config.provider || "anthropic");
  const [model, setModel] = useState(config.model || "");
  const [baseUrl, setBaseUrl] = useState(config.base_url || "");
  const [temperature, setTemperature] = useState(config.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens ?? 4096);
  const [customModel, setCustomModel] = useState("");

  // API key state
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [keySaved, setKeySaved] = useState(false);

  const hasKey = keyStatus[provider] ?? false;
  const needsKey = provider !== "ollama";
  const models = defaultModels[provider] || [];
  const selectedModel = models.find(m => m.id === model);
  const tempFill = (temperature / 1) * 100;

  const handleSave = () => {
    const envVar = providerEnvVars[provider] || "API_KEY";
    onSave({
      provider,
      model: model || customModel,
      api_key_env: envVar,
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

  return (
    <div className="space-y-4">
      {/* Main Model Card */}
      <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded-lg bg-plutus-500/10 flex items-center justify-center">
            <Brain className="w-5 h-5 text-plutus-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-gray-200">Coordinator Model</h3>
            <p className="text-xs text-gray-500">The main AI brain that talks to you and orchestrates workers</p>
          </div>
          {hasKey && needsKey && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full">
              <CheckCircle2 className="w-3 h-3" />
              Connected
            </span>
          )}
          {!hasKey && needsKey && (
            <span className="flex items-center gap-1.5 text-xs text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full">
              <AlertTriangle className="w-3 h-3" />
              Key needed
            </span>
          )}
        </div>

        {/* Provider Selection — selector cards */}
        <div className="mb-5">
          <label className="text-xs text-gray-500 mb-2 block">Provider</label>
          <div className="grid grid-cols-4 gap-2">
            {providers.map((p) => {
              const active = provider === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    setProvider(p.id);
                    const defaults = defaultModels[p.id];
                    if (defaults?.length) setModel(defaults[0].id);
                    setApiKey("");
                    setKeySaved(false);
                  }}
                  className={`selector-card relative flex flex-col items-center gap-1.5 p-3 rounded-xl border-2 ${
                    active
                      ? "border-plutus-500/50 bg-plutus-500/5 shadow-lg shadow-plutus-500/5"
                      : "border-gray-800/60 bg-gray-800/20 hover:border-gray-700/60 hover:bg-gray-800/40"
                  }`}
                  data-active={active}
                >
                  <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${p.color} flex items-center justify-center text-white text-xs font-bold shadow-sm transition-transform duration-200 ${
                    active ? "scale-110" : ""
                  }`}>
                    {p.icon}
                  </div>
                  <span className={`text-xs font-medium transition-colors ${active ? "text-gray-100" : "text-gray-300"}`}>{p.label}</span>
                  <span className="text-[10px] text-gray-500">{p.sublabel}</span>
                  {active && (
                    <div className="absolute top-1.5 right-1.5 w-4 h-4 bg-plutus-500/20 rounded-full flex items-center justify-center">
                      <Check className="w-2.5 h-2.5 text-plutus-400" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Model Selection */}
        <div className="mb-5">
          <label className="text-xs text-gray-500 mb-2 block">Model</label>
          {models.length > 0 ? (
            <div className="space-y-1.5">
              {models.map((m) => {
                const active = model === m.id;
                return (
                  <button
                    key={m.id}
                    onClick={() => { setModel(m.id); setCustomModel(""); }}
                    className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all duration-200 text-left ${
                      active
                        ? "border-plutus-500/40 bg-plutus-500/5 shadow-sm shadow-plutus-500/5"
                        : "border-gray-800/40 bg-gray-800/20 hover:border-gray-700/40 hover:bg-gray-800/30"
                    }`}
                  >
                    <div className={`w-2.5 h-2.5 rounded-full shrink-0 transition-all duration-200 ${
                      active ? "bg-plutus-400 shadow-sm shadow-plutus-400/50" : "bg-gray-600"
                    }`} />
                    <div className="flex-1 min-w-0">
                      <span className={`text-sm font-medium transition-colors ${active ? "text-gray-100" : "text-gray-200"}`}>{m.label}</span>
                      <span className="text-xs text-gray-500 ml-2">{m.desc}</span>
                    </div>
                    <span className="text-[10px] text-gray-600 font-mono shrink-0">{m.id}</span>
                  </button>
                );
              })}
              {/* Custom model option */}
              <button
                onClick={() => { setModel(""); }}
                className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all duration-200 text-left ${
                  model === "" ? "border-plutus-500/40 bg-plutus-500/5" : "border-gray-800/40 bg-gray-800/20 hover:border-gray-700/40"
                }`}
              >
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${model === "" ? "bg-plutus-400" : "bg-gray-600"}`} />
                <span className="text-sm text-gray-400">Custom model...</span>
              </button>
              {model === "" && (
                <input
                  type="text"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 ml-5 transition-all duration-200"
                  value={customModel}
                  onChange={(e) => setCustomModel(e.target.value)}
                  placeholder="Enter custom model name"
                />
              )}
            </div>
          ) : (
            <input
              type="text"
              className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 transition-all duration-200"
              value={model || customModel}
              onChange={(e) => { setModel(e.target.value); setCustomModel(e.target.value); }}
              placeholder="Enter model name"
            />
          )}
        </div>

        {/* Base URL (for custom/ollama) */}
        {(provider === "custom" || provider === "ollama") && (
          <div className="mb-5">
            <label className="text-xs text-gray-500 mb-1.5 block">Base URL</label>
            <input
              type="text"
              className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 transition-all duration-200"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={provider === "ollama" ? "http://localhost:11434" : "https://your-api-endpoint.com/v1"}
            />
          </div>
        )}

        {/* Temperature and Max Tokens */}
        <div className="grid grid-cols-2 gap-4 mb-5">
          {/* Temperature — custom slider */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-gray-400">Temperature</label>
              <span className="text-xs font-mono text-plutus-400 bg-plutus-500/10 px-2 py-0.5 rounded-md min-w-[2.5rem] text-center">
                {temperature}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="plutus-slider w-full"
              style={{ "--slider-fill": `${tempFill}%` } as React.CSSProperties}
            />
            <div className="flex justify-between text-[9px] text-gray-600 mt-1.5">
              <span>Precise</span>
              <span>Creative</span>
            </div>
          </div>

          {/* Max Tokens — number stepper */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">Max Tokens</label>
            <div className="number-input-group h-10">
              <button
                onClick={() => setMaxTokens(Math.max(256, maxTokens - 1024))}
                className="px-2"
              >
                <Minus className="w-3.5 h-3.5" />
              </button>
              <input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
                className="text-sm text-gray-200 py-2 w-24"
                min={256}
                step={1024}
              />
              <button
                onClick={() => setMaxTokens(maxTokens + 1024)}
                className="px-2"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 disabled:opacity-50 text-white text-sm font-medium transition-all duration-200 shadow-sm shadow-plutus-600/20 active:scale-[0.98]"
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving..." : "Save Model Settings"}
        </button>
      </div>

      {/* API Key Card */}
      {needsKey && (
        <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <Key className="w-5 h-5 text-amber-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-gray-200">API Key</h3>
              <p className="text-xs text-gray-500">
                {hasKey ? "Your key is securely stored" : `Required for ${providers.find(p => p.id === provider)?.label}`}
              </p>
            </div>
            {hasKey && (
              <button
                onClick={handleDeleteKey}
                className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 px-2.5 py-1.5 rounded-lg transition-all duration-200 active:scale-[0.97]"
              >
                <Trash2 className="w-3 h-3" />
                Remove
              </button>
            )}
          </div>

          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type={showKey ? "text" : "password"}
                className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 pr-10 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 transition-all duration-200"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasKey ? "Enter new key to update..." : "sk-..."}
                onKeyDown={(e) => { if (e.key === "Enter") handleSaveKey(); }}
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 p-0.5 transition-colors"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <button
              onClick={handleSaveKey}
              disabled={savingKey || !apiKey.trim()}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:hover:bg-amber-600 text-white text-sm font-medium transition-all duration-200 whitespace-nowrap shadow-sm shadow-amber-600/20 active:scale-[0.97]"
            >
              <Key className="w-4 h-4" />
              {savingKey ? "..." : "Save"}
            </button>
          </div>

          {keySaved && (
            <p className="text-xs text-emerald-400 mt-2 flex items-center gap-1.5 animate-fade-in">
              <CheckCircle2 className="w-3.5 h-3.5" />
              API key saved securely
            </p>
          )}

          <p className="text-[10px] text-gray-600 mt-3">
            Stored locally at ~/.plutus/.secrets.json — never leaves your machine.
          </p>
        </div>
      )}
    </div>
  );
}

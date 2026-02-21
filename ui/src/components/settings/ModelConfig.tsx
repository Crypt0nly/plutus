import { useState } from "react";
import { Brain, Save } from "lucide-react";

interface Props {
  config: Record<string, any>;
  onSave: (model: Record<string, any>) => void;
  saving: boolean;
}

const providers = [
  { id: "anthropic", label: "Anthropic (Claude)", envVar: "ANTHROPIC_API_KEY" },
  { id: "openai", label: "OpenAI (GPT)", envVar: "OPENAI_API_KEY" },
  { id: "ollama", label: "Ollama (Local)", envVar: "" },
  { id: "custom", label: "Custom Endpoint", envVar: "API_KEY" },
];

const defaultModels: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
  openai: ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
  ollama: ["llama3.2", "mistral", "codellama", "phi3"],
};

export function ModelConfig({ config, onSave, saving }: Props) {
  const [provider, setProvider] = useState(config.provider || "anthropic");
  const [model, setModel] = useState(config.model || "");
  const [baseUrl, setBaseUrl] = useState(config.base_url || "");
  const [temperature, setTemperature] = useState(config.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(config.max_tokens ?? 4096);

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

  const models = defaultModels[provider] || [];

  return (
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

        {/* Save button */}
        <button onClick={handleSave} disabled={saving} className="btn-primary flex items-center gap-2">
          <Save className="w-4 h-4" />
          {saving ? "Saving..." : "Save Model Settings"}
        </button>
      </div>
    </div>
  );
}

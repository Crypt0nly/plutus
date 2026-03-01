import { useState, useEffect, useRef, useCallback } from "react";
import {
  Settings,
  X,
  Brain,
  Shield,
  Heart,
  Play,
  Square,
  Sliders,
  ChevronDown,
  CheckCircle2,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import type { Tier } from "../../lib/types";

const providers = [
  { id: "anthropic", label: "Anthropic", icon: "A", color: "from-orange-500 to-amber-600" },
  { id: "openai", label: "OpenAI", icon: "O", color: "from-emerald-500 to-teal-600" },
  { id: "ollama", label: "Ollama", icon: "L", color: "from-blue-500 to-indigo-600" },
];

const defaultModels: Record<string, { id: string; label: string }[]> = {
  anthropic: [
    { id: "claude-opus-4-6", label: "Opus 4-6" },
    { id: "claude-sonnet-4-6", label: "Sonnet 4-6" },
    { id: "claude-haiku-4-5", label: "Haiku 4-5" },
  ],
  openai: [
    { id: "gpt-5.2", label: "GPT-5.2" },
    { id: "gpt-5", label: "GPT-5" },
    { id: "gpt-4.1", label: "GPT-4.1" },
    { id: "gpt-4.1-mini", label: "GPT-4.1 Mini" },
    { id: "o3", label: "o3" },
    { id: "o4-mini", label: "o4-mini" },
  ],
  ollama: [
    { id: "llama3.2", label: "Llama 3.2" },
    { id: "mistral", label: "Mistral" },
  ],
};

const tiers: { id: Tier; label: string; color: string }[] = [
  { id: "observer", label: "Observer", color: "text-gray-400 bg-gray-500/10 border-gray-500/30" },
  { id: "assistant", label: "Assistant", color: "text-blue-400 bg-blue-500/10 border-blue-500/30" },
  { id: "operator", label: "Operator", color: "text-amber-400 bg-amber-500/10 border-amber-500/30" },
  { id: "autonomous", label: "Autonomous", color: "text-red-400 bg-red-500/10 border-red-500/30" },
];

interface HeartbeatStatus {
  enabled: boolean;
  running: boolean;
  paused: boolean;
  interval_seconds: number;
  consecutive_beats: number;
  max_consecutive: number;
}

export function CommandCenter() {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [heartbeat, setHeartbeat] = useState<HeartbeatStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const { currentTier, setCurrentTier } = useAppStore();

  const fetchAll = useCallback(() => {
    api.getConfig().then(setConfig).catch(() => {});
    api.getHeartbeatStatus().then((s) => setHeartbeat(s as HeartbeatStatus)).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) {
      fetchAll();
      const timer = window.setInterval(() => {
        api.getHeartbeatStatus().then((s) => setHeartbeat(s as HeartbeatStatus)).catch(() => {});
      }, 5000);
      return () => window.clearInterval(timer);
    }
  }, [open, fetchAll]);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const handleSave = async (patch: Record<string, any>) => {
    setSaving(true);
    setSaved(false);
    try {
      await api.updateConfig(patch);
      setSaved(true);
      const updated = await api.getConfig();
      setConfig(updated);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error("Failed to save:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleTierChange = async (tier: Tier) => {
    try {
      await api.setTier(tier);
      setCurrentTier(tier);
    } catch (e) {
      console.error("Failed to set tier:", e);
    }
  };

  const handleHeartbeatToggle = async () => {
    try {
      if (heartbeat?.running) {
        const s = await api.stopHeartbeat();
        setHeartbeat(s as HeartbeatStatus);
      } else {
        const s = await api.startHeartbeat();
        setHeartbeat(s as HeartbeatStatus);
      }
    } catch (e) {
      console.error("Failed to toggle heartbeat:", e);
    }
  };

  const provider = config?.model?.provider || "anthropic";
  const model = config?.model?.model || "";
  const temperature = config?.model?.temperature ?? 0.7;
  const maxToolRounds = config?.agent?.max_tool_rounds || 25;
  const models = defaultModels[provider] || [];

  return (
    <div className="relative" ref={panelRef}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(!open)}
        className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
          open
            ? "bg-plutus-600 text-white"
            : "bg-gray-700/50 hover:bg-gray-700 text-gray-400 hover:text-gray-200"
        }`}
        title="Command Center"
      >
        <Settings className="w-4 h-4" />
      </button>

      {/* Panel */}
      {open && config && (
        <div className="absolute bottom-12 left-0 w-[380px] bg-surface-alt border border-gray-800/80 rounded-2xl shadow-2xl shadow-black/40 overflow-hidden z-50 animate-fade-in">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800/60">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-plutus-400" />
              <span className="text-sm font-semibold text-gray-200">Command Center</span>
            </div>
            <div className="flex items-center gap-2">
              {saved && (
                <span className="text-xs text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" />
                  Saved
                </span>
              )}
              <button
                onClick={() => setOpen(false)}
                className="text-gray-500 hover:text-gray-300 p-0.5 rounded transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="max-h-[480px] overflow-y-auto p-4 space-y-4">
            {/* Model Section */}
            <Section icon={Brain} iconColor="text-plutus-400 bg-plutus-500/10" title="Model">
              {/* Provider pills */}
              <div className="flex gap-1.5 mb-3">
                {providers.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      const newModels = defaultModels[p.id];
                      const newModel = newModels?.[0]?.id || model;
                      handleSave({ model: { provider: p.id, model: newModel } });
                    }}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      provider === p.id
                        ? "bg-plutus-500/15 text-plutus-300 border border-plutus-500/30"
                        : "bg-gray-800/40 text-gray-400 border border-gray-800/40 hover:border-gray-700/60 hover:text-gray-300"
                    }`}
                  >
                    <span className={`w-4 h-4 rounded text-[9px] font-bold bg-gradient-to-br ${p.color} text-white flex items-center justify-center`}>
                      {p.icon}
                    </span>
                    {p.label}
                  </button>
                ))}
              </div>

              {/* Model dropdown */}
              <div className="relative mb-3">
                <select
                  value={model}
                  onChange={(e) => handleSave({ model: { model: e.target.value } })}
                  className="w-full appearance-none bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 pr-8 text-sm text-gray-200 focus:outline-none focus:border-plutus-500/50 cursor-pointer"
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-gray-500 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>

              {/* Temperature */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-gray-500">Temperature</span>
                  <span className="text-xs font-mono text-plutus-400 bg-plutus-500/10 px-2 py-0.5 rounded">
                    {temperature}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => handleSave({ model: { temperature: parseFloat(e.target.value) } })}
                  className="w-full accent-plutus-500 h-1.5 rounded-full"
                />
                <div className="flex justify-between text-[9px] text-gray-600 mt-1">
                  <span>Precise</span>
                  <span>Creative</span>
                </div>
              </div>
            </Section>

            {/* Guardrails Tier */}
            <Section icon={Shield} iconColor="text-amber-400 bg-amber-500/10" title="Guardrails">
              <div className="grid grid-cols-4 gap-1.5">
                {tiers.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => handleTierChange(t.id)}
                    className={`px-2 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                      currentTier === t.id
                        ? t.color
                        : "text-gray-500 bg-gray-800/30 border-gray-800/40 hover:border-gray-700/50 hover:text-gray-400"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </Section>

            {/* Heartbeat */}
            <Section icon={Heart} iconColor="text-rose-400 bg-rose-500/10" title="Heartbeat">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {heartbeat?.running && !heartbeat?.paused && (
                    <span className="flex items-center gap-1 text-xs text-emerald-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Active
                      <span className="text-gray-500 ml-1">
                        {heartbeat.consecutive_beats}/{heartbeat.max_consecutive}
                      </span>
                    </span>
                  )}
                  {heartbeat?.paused && (
                    <span className="text-xs text-amber-400">Paused</span>
                  )}
                  {heartbeat && !heartbeat.running && !heartbeat.paused && (
                    <span className="text-xs text-gray-500">Off</span>
                  )}
                </div>
                <button
                  onClick={handleHeartbeatToggle}
                  className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    heartbeat?.running
                      ? "border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20"
                      : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                  }`}
                >
                  {heartbeat?.running ? (
                    <><Square className="w-3 h-3" /> Stop</>
                  ) : (
                    <><Play className="w-3 h-3" /> Start</>
                  )}
                </button>
              </div>
            </Section>

            {/* Agent */}
            <Section icon={Sliders} iconColor="text-blue-400 bg-blue-500/10" title="Agent">
              {/* Max Tool Rounds */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-gray-300">Max Tool Rounds</span>
                  <span className="text-xs font-mono text-plutus-400 bg-plutus-500/10 px-2 py-0.5 rounded">
                    {maxToolRounds}
                  </span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="100"
                  step="5"
                  value={maxToolRounds}
                  onChange={(e) =>
                    handleSave({ agent: { max_tool_rounds: parseInt(e.target.value) || 25 } })
                  }
                  className="w-full accent-plutus-500 h-1.5 rounded-full"
                />
                <div className="flex justify-between text-[9px] text-gray-600 mt-1">
                  <span>5</span>
                  <span>50</span>
                  <span>100</span>
                </div>
              </div>
            </Section>
          </div>

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-gray-800/60 flex items-center justify-between">
            <button
              onClick={() => {
                setOpen(false);
                useAppStore.getState().setView("settings");
              }}
              className="text-xs text-gray-500 hover:text-plutus-400 transition-colors"
            >
              Open full settings
            </button>
            {saving && (
              <span className="text-xs text-gray-500">Saving...</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Section({
  icon: Icon,
  iconColor,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  title: string;
  children: React.ReactNode;
}) {
  const [iconBg, iconText] = iconColor.split(" ").length >= 2
    ? [iconColor.split(" ")[1], iconColor.split(" ")[0]]
    : ["bg-gray-500/10", "text-gray-400"];

  return (
    <div className="bg-gray-800/20 rounded-xl border border-gray-800/40 p-3">
      <div className="flex items-center gap-2 mb-3">
        <div className={`w-6 h-6 rounded-md ${iconBg} flex items-center justify-center`}>
          <Icon className={`w-3.5 h-3.5 ${iconText}`} />
        </div>
        <span className="text-xs font-semibold text-gray-300">{title}</span>
      </div>
      {children}
    </div>
  );
}

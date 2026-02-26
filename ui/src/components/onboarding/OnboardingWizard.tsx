import { useState, useEffect } from "react";
import {
  ChevronRight,
  ChevronLeft,
  Key,
  Eye,
  EyeOff,
  CheckCircle2,
  Shield,
  Zap,
  Terminal,
  Globe,
  Brain,
  Cpu,
  Wrench,
  Monitor,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

const TOTAL_STEPS = 4;

const providers = [
  {
    id: "anthropic",
    label: "Anthropic",
    sublabel: "Claude models",
    icon: "A",
    color: "from-orange-500 to-amber-600",
    keyPlaceholder: "sk-ant-...",
    keyUrl: "https://console.anthropic.com/settings/keys",
    keyLabel: "Anthropic Console",
  },
  {
    id: "openai",
    label: "OpenAI",
    sublabel: "GPT models",
    icon: "O",
    color: "from-emerald-500 to-teal-600",
    keyPlaceholder: "sk-...",
    keyUrl: "https://platform.openai.com/api-keys",
    keyLabel: "OpenAI Dashboard",
  },
  {
    id: "ollama",
    label: "Ollama",
    sublabel: "Free, local models",
    icon: "L",
    color: "from-blue-500 to-indigo-600",
    keyPlaceholder: "",
    keyUrl: "",
    keyLabel: "",
  },
  {
    id: "custom",
    label: "Custom",
    sublabel: "Any endpoint",
    icon: "C",
    color: "from-gray-500 to-gray-600",
    keyPlaceholder: "your-api-key",
    keyUrl: "",
    keyLabel: "",
  },
];

const tiers = [
  {
    id: "observer",
    label: "Observer",
    desc: "Read-only. Plutus can look but not touch anything.",
    icon: Eye,
    color: "text-gray-400",
    bg: "bg-gray-500/10 border-gray-700/60",
    activeBg: "bg-gray-500/20 border-gray-400/40",
  },
  {
    id: "assistant",
    label: "Assistant",
    desc: "Every action requires your explicit approval first.",
    icon: Shield,
    label2: "Recommended for new users",
    color: "text-blue-400",
    bg: "bg-blue-500/10 border-blue-700/40",
    activeBg: "bg-blue-500/20 border-blue-400/40",
  },
  {
    id: "operator",
    label: "Operator",
    desc: "Pre-approved safe actions run automatically. Risky ones still ask.",
    icon: Wrench,
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-700/40",
    activeBg: "bg-amber-500/20 border-amber-400/40",
  },
  {
    id: "autonomous",
    label: "Autonomous",
    desc: "Full system control. No restrictions. For advanced users only.",
    icon: Zap,
    color: "text-red-400",
    bg: "bg-red-500/10 border-red-700/40",
    activeBg: "bg-red-500/20 border-red-400/40",
  },
];

const capabilities = [
  { icon: Terminal, label: "Run shell commands", desc: "Execute anything in your terminal" },
  { icon: Globe, label: "Browse the web", desc: "Search, scrape, and interact with sites" },
  { icon: Brain, label: "Long-term memory", desc: "Remembers facts across conversations" },
  { icon: Cpu, label: "Parallel workers", desc: "Spawn sub-agents for complex tasks" },
  { icon: Monitor, label: "Desktop control", desc: "Click, type, and see your screen" },
  { icon: Wrench, label: "Custom tools", desc: "Build your own tools with Python" },
];

export function OnboardingWizard() {
  const [step, setStep] = useState(0);
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [keySaved, setKeySaved] = useState(false);
  const [keyError, setKeyError] = useState("");
  const [tier, setTier] = useState("assistant");
  const [finishing, setFinishing] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");

  const selectedProvider = providers.find((p) => p.id === provider)!;
  const needsKey = provider !== "ollama";

  // Check if key is already configured for selected provider
  const [existingKey, setExistingKey] = useState(false);
  useEffect(() => {
    api.getKeyStatus().then((data) => {
      setExistingKey(data.providers?.[provider] ?? false);
    }).catch(() => {});
  }, [provider]);

  const canAdvance = () => {
    if (step === 1) {
      // Provider step — always fine, provider is selected
      return true;
    }
    if (step === 2) {
      // API key step — need key configured or not needed
      return !needsKey || keySaved || existingKey;
    }
    return true;
  };

  const handleSaveKey = async () => {
    if (!apiKey.trim()) return;
    setSavingKey(true);
    setKeyError("");
    try {
      const result = await api.setKey(provider, apiKey.trim());
      setKeySaved(true);
      setExistingKey(true);
      setApiKey("");
      setShowKey(false);
      if (result.key_configured) {
        useAppStore.getState().setKeyConfigured(true);
      }
    } catch {
      setKeyError("Failed to save key. Please try again.");
    } finally {
      setSavingKey(false);
    }
  };

  const handleFinish = async () => {
    setFinishing(true);
    try {
      // Save model config
      const defaultModels: Record<string, string> = {
        anthropic: "claude-sonnet-4-6",
        openai: "gpt-4.1",
        ollama: "llama3.2",
        custom: "gpt-4.1",
      };
      await api.updateConfig({
        model: {
          provider,
          model: defaultModels[provider] || "claude-sonnet-4-6",
          base_url: baseUrl || null,
        },
        guardrails: { tier },
      });
      // Mark onboarding completed
      await api.completeSetup();
      useAppStore.getState().setOnboardingCompleted(true);
      useAppStore.getState().setView("chat");
    } catch {
      // Still proceed — worst case they can reconfigure in settings
      useAppStore.getState().setOnboardingCompleted(true);
      useAppStore.getState().setView("chat");
    }
  };

  const next = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <div className="fixed inset-0 bg-gray-950 z-50 flex items-center justify-center overflow-y-auto">
      {/* Background gradient effect */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -left-1/4 w-[800px] h-[800px] rounded-full bg-plutus-600/5 blur-[120px]" />
        <div className="absolute -bottom-1/2 -right-1/4 w-[600px] h-[600px] rounded-full bg-indigo-600/5 blur-[100px]" />
      </div>

      <div className="relative w-full max-w-2xl mx-auto px-6 py-12">
        {/* Progress bar */}
        <div className="flex items-center gap-2 mb-10">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-all duration-500 ${
                i <= step ? "bg-plutus-500" : "bg-gray-800"
              }`}
            />
          ))}
        </div>

        {/* Step content with transition */}
        <div className="min-h-[480px]">
          {step === 0 && <StepWelcome />}
          {step === 1 && (
            <StepProvider
              provider={provider}
              setProvider={(p) => {
                setProvider(p);
                setKeySaved(false);
                setApiKey("");
                setKeyError("");
              }}
              baseUrl={baseUrl}
              setBaseUrl={setBaseUrl}
            />
          )}
          {step === 2 && (
            <StepApiKey
              provider={selectedProvider}
              needsKey={needsKey}
              apiKey={apiKey}
              setApiKey={setApiKey}
              showKey={showKey}
              setShowKey={setShowKey}
              savingKey={savingKey}
              keySaved={keySaved || existingKey}
              keyError={keyError}
              onSaveKey={handleSaveKey}
            />
          )}
          {step === 3 && (
            <StepTier tier={tier} setTier={setTier} />
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8">
          <div>
            {step > 0 && (
              <button
                onClick={prev}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 transition-all"
              >
                <ChevronLeft className="w-4 h-4" />
                Back
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-600">
              {step + 1} of {TOTAL_STEPS}
            </span>

            {step < TOTAL_STEPS - 1 ? (
              <button
                onClick={next}
                disabled={!canAdvance()}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 disabled:opacity-40 disabled:hover:bg-plutus-600 text-white text-sm font-medium transition-all shadow-lg shadow-plutus-600/20 hover:shadow-plutus-500/30"
              >
                Continue
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={finishing}
                className="flex items-center gap-2 px-8 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 disabled:opacity-60 text-white text-sm font-medium transition-all shadow-lg shadow-plutus-600/20 hover:shadow-plutus-500/30"
              >
                {finishing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Setting up...
                  </>
                ) : (
                  <>
                    Launch Plutus
                    <Zap className="w-4 h-4" />
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Step 0: Welcome ────────────────────────────────────── */

function StepWelcome() {
  return (
    <div className="animate-onboard-in">
      <div className="flex items-center gap-4 mb-2">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-plutus-500 to-plutus-700 flex items-center justify-center text-2xl font-bold shadow-xl shadow-plutus-600/30 ring-1 ring-white/10">
          P
        </div>
        <div>
          <h1 className="text-3xl font-bold text-gray-100">Welcome to Plutus</h1>
          <p className="text-sm text-gray-500 mt-0.5">Your autonomous AI agent</p>
        </div>
      </div>

      <p className="text-gray-400 mt-6 text-[15px] leading-relaxed max-w-xl">
        Plutus is an AI assistant that can control your computer, run commands,
        browse the web, manage files, and automate complex tasks — all from a
        single chat interface.
      </p>

      <p className="text-gray-500 mt-3 text-sm leading-relaxed max-w-xl">
        This setup takes about 60 seconds. We'll connect an AI provider, set
        your safety preferences, and you'll be ready to go.
      </p>

      {/* Capability grid */}
      <div className="grid grid-cols-2 gap-3 mt-8">
        {capabilities.map((cap) => {
          const Icon = cap.icon;
          return (
            <div
              key={cap.label}
              className="flex items-start gap-3 p-3.5 rounded-xl bg-gray-900/60 border border-gray-800/50"
            >
              <div className="w-8 h-8 rounded-lg bg-plutus-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <Icon className="w-4 h-4 text-plutus-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-200">{cap.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{cap.desc}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Step 1: Provider Selection ─────────────────────────── */

function StepProvider({
  provider,
  setProvider,
  baseUrl,
  setBaseUrl,
}: {
  provider: string;
  setProvider: (id: string) => void;
  baseUrl: string;
  setBaseUrl: (url: string) => void;
}) {
  return (
    <div className="animate-onboard-in">
      <h2 className="text-2xl font-bold text-gray-100">Choose your AI provider</h2>
      <p className="text-sm text-gray-500 mt-2 mb-8">
        Select which AI service will power Plutus. You can change this later in Settings.
      </p>

      <div className="grid grid-cols-2 gap-3">
        {providers.map((p) => {
          const active = provider === p.id;
          return (
            <button
              key={p.id}
              onClick={() => setProvider(p.id)}
              className={`relative flex items-center gap-4 p-5 rounded-xl border-2 transition-all text-left ${
                active
                  ? "border-plutus-500/60 bg-plutus-500/5 shadow-lg shadow-plutus-500/10"
                  : "border-gray-800/60 bg-gray-900/40 hover:border-gray-700/60 hover:bg-gray-900/60"
              }`}
            >
              <div
                className={`w-12 h-12 rounded-xl bg-gradient-to-br ${p.color} flex items-center justify-center text-white text-lg font-bold shadow-md`}
              >
                {p.icon}
              </div>
              <div>
                <p className="text-base font-semibold text-gray-200">{p.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{p.sublabel}</p>
              </div>
              {active && (
                <div className="absolute top-3 right-3">
                  <CheckCircle2 className="w-5 h-5 text-plutus-400" />
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Base URL for custom/ollama */}
      {(provider === "custom" || provider === "ollama") && (
        <div className="mt-6">
          <label className="text-sm text-gray-400 mb-2 block">Base URL</label>
          <input
            type="text"
            className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-3 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder={
              provider === "ollama"
                ? "http://localhost:11434"
                : "https://your-api-endpoint.com/v1"
            }
          />
          {provider === "ollama" && (
            <p className="text-xs text-gray-600 mt-2">
              Make sure Ollama is running locally. Default: http://localhost:11434
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Step 2: API Key ────────────────────────────────────── */

function StepApiKey({
  provider,
  needsKey,
  apiKey,
  setApiKey,
  showKey,
  setShowKey,
  savingKey,
  keySaved,
  keyError,
  onSaveKey,
}: {
  provider: (typeof providers)[number];
  needsKey: boolean;
  apiKey: string;
  setApiKey: (v: string) => void;
  showKey: boolean;
  setShowKey: (v: boolean) => void;
  savingKey: boolean;
  keySaved: boolean;
  keyError: string;
  onSaveKey: () => void;
}) {
  if (!needsKey) {
    return (
      <div className="animate-onboard-in">
        <h2 className="text-2xl font-bold text-gray-100">No API key needed</h2>
        <p className="text-sm text-gray-500 mt-2 mb-8">
          Ollama runs locally on your machine — no API key or account required.
          Just make sure Ollama is installed and running.
        </p>
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <p className="text-sm text-emerald-300">
            You're all set! Click Continue to pick your safety tier.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-onboard-in">
      <h2 className="text-2xl font-bold text-gray-100">Connect your {provider.label} key</h2>
      <p className="text-sm text-gray-500 mt-2 mb-2">
        Plutus needs an API key to communicate with {provider.label}.
        Your key is stored locally and never sent anywhere except {provider.label}'s API.
      </p>

      {provider.keyUrl && (
        <p className="text-sm text-gray-500 mb-8">
          Don't have one?{" "}
          <a
            href={provider.keyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-plutus-400 hover:text-plutus-300 underline underline-offset-2"
          >
            Get a key from {provider.keyLabel}
          </a>
        </p>
      )}

      {keySaved ? (
        <div className="flex items-center gap-3 p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 mb-4">
          <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-emerald-300">API key configured</p>
            <p className="text-xs text-emerald-400/60 mt-0.5">
              Stored securely at ~/.plutus/.secrets.json
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 mb-2 block">
              <Key className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />
              API Key
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? "text" : "password"}
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-3.5 pr-11 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 font-mono"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={provider.keyPlaceholder}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSaveKey();
                  }}
                  autoFocus
                />
                <button
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 p-1"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                onClick={onSaveKey}
                disabled={savingKey || !apiKey.trim()}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-plutus-600 hover:bg-plutus-500 disabled:opacity-40 disabled:hover:bg-plutus-600 text-white text-sm font-medium transition-all whitespace-nowrap"
              >
                {savingKey ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Key className="w-4 h-4" />
                )}
                {savingKey ? "Saving..." : "Save Key"}
              </button>
            </div>
          </div>

          {keyError && (
            <p className="text-xs text-red-400">{keyError}</p>
          )}
        </div>
      )}

      <div className="mt-8 p-4 rounded-xl bg-gray-900/60 border border-gray-800/50">
        <p className="text-xs text-gray-500 leading-relaxed">
          <span className="text-gray-400 font-medium">Privacy:</span> Your API key
          is stored in <code className="text-gray-400 bg-gray-800 px-1.5 py-0.5 rounded text-[11px]">~/.plutus/.secrets.json</code> with
          restricted file permissions (owner-only). It is never included in config files
          or sent to any service other than your chosen provider.
        </p>
      </div>
    </div>
  );
}

/* ─── Step 3: Safety Tier ────────────────────────────────── */

function StepTier({
  tier,
  setTier,
}: {
  tier: string;
  setTier: (t: string) => void;
}) {
  return (
    <div className="animate-onboard-in">
      <h2 className="text-2xl font-bold text-gray-100">Set your safety level</h2>
      <p className="text-sm text-gray-500 mt-2 mb-8">
        Guardrails control what Plutus can do without asking. You can change this
        anytime from the Guardrails page.
      </p>

      <div className="space-y-3">
        {tiers.map((t) => {
          const Icon = t.icon;
          const active = tier === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTier(t.id)}
              className={`w-full flex items-start gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                active ? t.activeBg : `${t.bg} hover:brightness-110`
              }`}
            >
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                  active ? "bg-white/10" : "bg-white/5"
                }`}
              >
                <Icon className={`w-5 h-5 ${t.color}`} />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-gray-200">{t.label}</p>
                  {t.label2 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 font-medium">
                      {t.label2}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-1">{t.desc}</p>
              </div>
              {active && (
                <CheckCircle2 className={`w-5 h-5 shrink-0 mt-1 ${t.color}`} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

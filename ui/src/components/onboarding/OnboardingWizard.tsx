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
  AlertTriangle,
  ExternalLink,
  ArrowRight,
  Box,
  Package,
  Server,
  Code2,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

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

  // Platform detection for WSL step
  const [isWindows, setIsWindows] = useState<boolean | null>(null);
  const [wslDetected, setWslDetected] = useState(false);
  const [wslSetupDone, setWslSetupDone] = useState(false);

  const selectedProvider = providers.find((p) => p.id === provider)!;
  const needsKey = provider !== "ollama";

  // Steps: 0=Welcome, 1=Provider, 2=ApiKey, 3=Tier, 4=WSL (Windows only)
  // On non-Windows, step 4 is skipped — the "Launch" button appears on step 3.
  const totalSteps = isWindows ? 5 : 4;
  const lastStep = totalSteps - 1;

  // Check if key is already configured for selected provider
  const [existingKey, setExistingKey] = useState(false);
  useEffect(() => {
    api.getKeyStatus().then((data) => {
      setExistingKey(data.providers?.[provider] ?? false);
    }).catch(() => {});
  }, [provider]);

  // Detect platform on mount
  useEffect(() => {
    api.getWSLStatus().then((status) => {
      setIsWindows(status.is_windows);
      setWslDetected(status.wsl_installed);
      setWslSetupDone(status.setup_completed);
    }).catch(() => {
      setIsWindows(false); // default to non-Windows on error
    });
  }, []);

  const canAdvance = () => {
    if (step === 1) return true;
    if (step === 2) return !needsKey || keySaved || existingKey;
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
      await api.completeSetup();
      useAppStore.getState().setOnboardingCompleted(true);
      useAppStore.getState().setView("chat");
    } catch {
      useAppStore.getState().setOnboardingCompleted(true);
      useAppStore.getState().setView("chat");
    }
  };

  const next = () => setStep((s) => Math.min(s + 1, lastStep));
  const prev = () => setStep((s) => Math.max(s - 1, 0));

  // Still loading platform detection
  if (isWindows === null) {
    return (
      <div className="fixed inset-0 bg-gray-950 z-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-plutus-500 to-plutus-700 flex items-center justify-center font-bold text-lg shadow-lg shadow-plutus-600/20 ring-1 ring-white/10">
            P
          </div>
          <div className="w-6 h-6 border-2 border-plutus-500/30 border-t-plutus-500 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

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
          {Array.from({ length: totalSteps }).map((_, i) => (
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
          {step === 3 && !isWindows && (
            <StepTier tier={tier} setTier={setTier} />
          )}
          {step === 3 && isWindows && (
            <StepTier tier={tier} setTier={setTier} />
          )}
          {step === 4 && isWindows && (
            <StepWSL
              wslDetected={wslDetected}
              wslSetupDone={wslSetupDone}
              onSetupComplete={() => setWslSetupDone(true)}
            />
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
              {step + 1} of {totalSteps}
            </span>

            {step < lastStep ? (
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

/* ─── Step 4 (Windows only): WSL Setup ──────────────────── */

const wslBenefits = [
  { icon: Package, label: "Package managers", desc: "apt, pip, npm, cargo — install anything in seconds" },
  { icon: Code2, label: "Dev tools", desc: "GCC, Python, Node.js, Rust, Go, and more" },
  { icon: Server, label: "Server tools", desc: "Docker, nginx, PostgreSQL, Redis, SSH" },
  { icon: Box, label: "Shell scripting", desc: "Full Bash with grep, sed, awk, and thousands of CLI tools" },
];

function StepWSL({
  wslDetected,
  wslSetupDone,
  onSetupComplete,
}: {
  wslDetected: boolean;
  wslSetupDone: boolean;
  onSetupComplete: () => void;
}) {
  const [showFullGuide, setShowFullGuide] = useState(false);
  const [settingUp, setSettingUp] = useState(false);

  const handleMarkComplete = async () => {
    setSettingUp(true);
    try {
      await api.completeWSLSetup();
      onSetupComplete();
    } catch {
      // still mark done locally
      onSetupComplete();
    } finally {
      setSettingUp(false);
    }
  };

  // Already set up — show success state
  if (wslSetupDone) {
    return (
      <div className="animate-onboard-in">
        <h2 className="text-2xl font-bold text-gray-100">Linux Superpowers</h2>
        <p className="text-sm text-gray-500 mt-2 mb-6">
          WSL is configured and ready to go.
        </p>

        <div className="flex items-center gap-4 p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 mb-6">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/20 flex items-center justify-center">
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
          </div>
          <div>
            <p className="text-base font-semibold text-emerald-300">WSL is active</p>
            <p className="text-sm text-emerald-400/60 mt-0.5">
              Plutus has full access to Linux tools on your Windows machine.
            </p>
          </div>
        </div>

        <p className="text-sm text-gray-500">
          Click <span className="text-gray-300">Launch Plutus</span> to start using your AI agent.
        </p>
      </div>
    );
  }

  // Full inline setup guide
  if (showFullGuide) {
    return (
      <OnboardingWSLGuide
        wslDetected={wslDetected}
        onComplete={handleMarkComplete}
        onBack={() => setShowFullGuide(false)}
      />
    );
  }

  // Main WSL pitch screen
  return (
    <div className="animate-onboard-in">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-600/20">
          <Terminal className="w-6 h-6 text-white" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gray-100">Unlock Linux Superpowers</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Recommended for the full Plutus experience
          </p>
        </div>
      </div>

      <div className="mt-5 p-4 rounded-xl bg-orange-500/5 border border-orange-500/15">
        <p className="text-sm text-gray-300 leading-relaxed">
          <span className="text-orange-400 font-semibold">WSL (Windows Subsystem for Linux)</span> gives
          Plutus access to the entire Linux ecosystem directly on your Windows PC — no virtual machine,
          no dual-boot, no complexity. It's like giving your AI agent a second brain.
        </p>
      </div>

      {/* Benefits grid */}
      <div className="grid grid-cols-2 gap-3 mt-5">
        {wslBenefits.map((b) => {
          const Icon = b.icon;
          return (
            <div
              key={b.label}
              className="flex items-start gap-3 p-3.5 rounded-xl bg-gray-900/60 border border-gray-800/50"
            >
              <div className="w-8 h-8 rounded-lg bg-orange-500/10 flex items-center justify-center shrink-0 mt-0.5">
                <Icon className="w-4 h-4 text-orange-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-200">{b.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{b.desc}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* WSL detected banner */}
      {wslDetected && (
        <div className="mt-5 flex items-center gap-3 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <div>
            <p className="text-sm text-emerald-300 font-medium">WSL is already installed</p>
            <p className="text-xs text-emerald-400/60 mt-0.5">
              We detected WSL on your system. You can activate it right away.
            </p>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="mt-6 space-y-3">
        {wslDetected ? (
          <button
            onClick={handleMarkComplete}
            disabled={settingUp}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 disabled:opacity-60 text-white text-sm font-semibold transition-all shadow-lg shadow-orange-500/20"
          >
            {settingUp ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {settingUp ? "Activating..." : "Activate Linux Superpowers"}
          </button>
        ) : (
          <button
            onClick={() => setShowFullGuide(true)}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white text-sm font-semibold transition-all shadow-lg shadow-orange-500/20"
          >
            <Terminal className="w-4 h-4" />
            Set up WSL now
            <ArrowRight className="w-4 h-4" />
          </button>
        )}

        <p className="text-center text-xs text-gray-600">
          You can also set this up later from Settings. It takes about 10 minutes.
        </p>
      </div>
    </div>
  );
}

/* ─── Inline WSL guide for onboarding ──────────────────── */

function OnboardingWSLGuide({
  wslDetected,
  onComplete,
  onBack,
}: {
  wslDetected: boolean;
  onComplete: () => void;
  onBack: () => void;
}) {
  interface GuideStep {
    id: string;
    title: string;
    description: string;
    substeps?: string[];
    command: string | null;
    command_verify?: string;
    note: string;
    warning?: string | null;
  }

  const [steps, setSteps] = useState<GuideStep[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const [showTroubleshooting, setShowTroubleshooting] = useState(false);
  const [troubleshooting, setTroubleshooting] = useState<
    { id: string; problem: string; solution: string }[]
  >([]);

  useEffect(() => {
    api
      .getWSLSetupGuide()
      .then((guide) => {
        if (!guide.needed) {
          onComplete();
          return;
        }
        setSteps(guide.steps);
        setTroubleshooting(guide.troubleshooting || []);
        if (wslDetected && guide.steps.length > 0) {
          // Skip install + reboot steps
          const autoComplete = new Set<string>();
          for (const s of guide.steps) {
            if (s.id === "open_terminal" || s.id === "install_wsl" || s.id === "reboot") {
              autoComplete.add(s.id);
            }
          }
          setCompletedSteps(autoComplete);
          const verifyIdx = guide.steps.findIndex((s) => s.id === "verify");
          const createIdx = guide.steps.findIndex((s) => s.id === "create_user");
          setCurrentStep(createIdx >= 0 ? createIdx : verifyIdx >= 0 ? verifyIdx : 0);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [wslDetected, onComplete]);

  const copyCommand = (cmd: string) => {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopiedCmd(cmd);
      setTimeout(() => setCopiedCmd(null), 2000);
    });
  };

  const markStepDone = (stepId: string) => {
    setCompletedSteps((prev) => new Set([...prev, stepId]));
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const allDone = steps.length > 0 && steps.every((s) => completedSteps.has(s.id));
  const step = steps[currentStep];

  if (loading) {
    return (
      <div className="animate-onboard-in flex items-center justify-center min-h-[400px]">
        <div className="w-8 h-8 border-2 border-orange-500/30 border-t-orange-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (allDone) {
    return (
      <div className="animate-onboard-in">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-green-600 flex items-center justify-center shadow-xl shadow-emerald-600/20">
            <CheckCircle2 className="w-7 h-7 text-white" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-gray-100">All set!</h2>
            <p className="text-sm text-gray-500 mt-0.5">WSL is installed and ready to go.</p>
          </div>
        </div>

        <p className="text-sm text-gray-400 mb-6">
          Plutus can now use Linux tools like apt, Docker, SSH, compilers, and thousands more —
          all running natively on your Windows machine.
        </p>

        <button
          onClick={onComplete}
          className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-400 hover:to-amber-400 text-white text-sm font-semibold transition-all shadow-lg shadow-orange-500/20"
        >
          <Zap className="w-4 h-4" />
          Activate Linux Superpowers
        </button>
      </div>
    );
  }

  return (
    <div className="animate-onboard-in">
      {/* Header with progress */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" />
          Back to overview
        </button>
        <span className="text-xs text-orange-400/80 font-medium px-2.5 py-1 bg-orange-500/10 rounded-lg">
          Step {currentStep + 1} of {steps.length}
        </span>
      </div>

      {/* Step progress dots */}
      <div className="flex items-center gap-1.5 mb-6">
        {steps.map((s, i) => (
          <button
            key={s.id}
            onClick={() => setCurrentStep(i)}
            className={`h-1.5 flex-1 rounded-full transition-all duration-300 cursor-pointer ${
              completedSteps.has(s.id)
                ? "bg-orange-500"
                : i === currentStep
                ? "bg-orange-500/40"
                : "bg-gray-800 hover:bg-gray-700"
            }`}
          />
        ))}
      </div>

      {step && (
        <>
          {/* Step title + completed badge */}
          <div className="flex items-start gap-3 mb-3">
            <div className="w-8 h-8 rounded-lg bg-orange-500/15 flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-sm font-bold text-orange-400">{currentStep + 1}</span>
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-bold text-gray-100">{step.title}</h3>
              {completedSteps.has(step.id) && (
                <span className="text-xs text-emerald-400 flex items-center gap-1 mt-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Completed
                </span>
              )}
            </div>
          </div>

          {/* Description */}
          <p className="text-sm text-gray-400 leading-relaxed mb-4">{step.description}</p>

          {/* Sub-steps */}
          {step.substeps && step.substeps.length > 0 && (
            <div className="space-y-2 mb-4">
              {step.substeps.map((sub, i) => (
                <div key={i} className="flex items-start gap-2.5 text-sm">
                  <div className="w-5 h-5 rounded-full bg-gray-800 flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-[10px] font-bold text-gray-400">{i + 1}</span>
                  </div>
                  <span className="text-gray-400">{sub}</span>
                </div>
              ))}
            </div>
          )}

          {/* Command box */}
          {step.command && (
            <div className="relative group mb-4">
              <div className="bg-gray-900 rounded-lg border border-gray-800/60 p-4 font-mono text-sm text-orange-300 overflow-x-auto">
                {step.command}
              </div>
              <button
                onClick={() => copyCommand(step.command!)}
                className="absolute top-2 right-2 p-2 rounded-lg bg-gray-800/80 hover:bg-gray-700/80 text-gray-400 hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-all"
              >
                {copiedCmd === step.command ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <span className="text-xs font-medium">Copy</span>
                )}
              </button>
            </div>
          )}

          {/* Verify command */}
          {step.command_verify && (
            <div className="relative group mb-4">
              <p className="text-xs text-gray-500 mb-1.5">Then run this to verify:</p>
              <div className="bg-gray-900 rounded-lg border border-gray-800/60 p-4 font-mono text-sm text-orange-300/80 overflow-x-auto">
                {step.command_verify}
              </div>
              <button
                onClick={() => copyCommand(step.command_verify!)}
                className="absolute top-8 right-2 p-2 rounded-lg bg-gray-800/80 hover:bg-gray-700/80 text-gray-400 hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-all"
              >
                {copiedCmd === step.command_verify ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <span className="text-xs font-medium">Copy</span>
                )}
              </button>
            </div>
          )}

          {/* Warning */}
          {step.warning && (
            <div className="flex items-start gap-3 p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20 mb-4">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-300/80 leading-relaxed">{step.warning}</p>
            </div>
          )}

          {/* Tip */}
          <div className="bg-gray-900/40 rounded-lg p-3 border border-gray-800/30 mb-4">
            <p className="text-xs text-gray-500 leading-relaxed">
              <span className="text-gray-400 font-medium">Tip:</span> {step.note}
            </p>
          </div>

          {/* Mark done + navigation */}
          <div className="flex items-center justify-between">
            {!completedSteps.has(step.id) ? (
              <button
                onClick={() => markStepDone(step.id)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 text-orange-400 text-sm font-medium transition-all"
              >
                <CheckCircle2 className="w-4 h-4" />
                I've done this step
              </button>
            ) : (
              <div />
            )}

            <div className="flex items-center gap-2">
              {currentStep > 0 && (
                <button
                  onClick={() => setCurrentStep(currentStep - 1)}
                  className="px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 transition-all"
                >
                  Prev
                </button>
              )}
              {currentStep < steps.length - 1 && (
                <button
                  onClick={() => setCurrentStep(currentStep + 1)}
                  className="flex items-center gap-1 px-3 py-2 rounded-xl text-sm text-gray-300 hover:text-white bg-gray-800/60 hover:bg-gray-700/60 transition-all"
                >
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </>
      )}

      {/* Troubleshooting toggle */}
      {troubleshooting.length > 0 && (
        <div className="mt-6 border-t border-gray-800/40 pt-4">
          <button
            onClick={() => setShowTroubleshooting(!showTroubleshooting)}
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            {showTroubleshooting ? "Hide troubleshooting" : "Having problems? Click here"}
            <ChevronRight
              className={`w-3.5 h-3.5 transition-transform ${showTroubleshooting ? "rotate-90" : ""}`}
            />
          </button>

          {showTroubleshooting && (
            <div className="mt-3 space-y-3 max-h-[200px] overflow-y-auto pr-1">
              {troubleshooting.map((t) => (
                <div key={t.id} className="bg-gray-900/40 rounded-lg p-3 border border-gray-800/30">
                  <p className="text-xs font-medium text-gray-300 mb-1">{t.problem}</p>
                  <p className="text-xs text-gray-500 leading-relaxed whitespace-pre-line">
                    {t.solution}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import { useState, useEffect } from "react";
import {
  Terminal,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  Copy,
  RotateCcw,
  Zap,
  Monitor,
  AlertTriangle,
  ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";

interface WSLStatus {
  platform: string;
  is_windows: boolean;
  wsl_installed: boolean;
  enabled: boolean;
  setup_completed: boolean;
  preferred_distro: string;
}

interface SetupStep {
  id: string;
  title: string;
  description: string;
  command: string | null;
  note: string;
}

/** WSL toggle + guided setup for Settings page. */
export function WSLSetup() {
  const [status, setStatus] = useState<WSLStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showGuide, setShowGuide] = useState(false);
  const [toggling, setToggling] = useState(false);

  const fetchStatus = () => {
    setLoading(true);
    api
      .getWSLStatus()
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleToggle = async () => {
    if (!status) return;
    setToggling(true);
    try {
      const newEnabled = !status.enabled;
      await api.enableWSL(newEnabled);
      setStatus({ ...status, enabled: newEnabled });
      // If user just enabled and hasn't done setup yet, open guide
      if (newEnabled && !status.setup_completed && status.is_windows) {
        setShowGuide(true);
      }
    } catch {
      // ignore
    } finally {
      setToggling(false);
    }
  };

  if (loading || !status) {
    return (
      <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-orange-500/10 flex items-center justify-center">
            <Terminal className="w-5 h-5 text-orange-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Linux Superpowers (WSL)</h3>
            <p className="text-xs text-gray-500">Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  // Not on Windows — show native info
  if (!status.is_windows) {
    return (
      <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
            <Terminal className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Linux Superpowers</h3>
            <p className="text-xs text-gray-500">Native Linux/macOS detected</p>
          </div>
          <div className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">Active</span>
          </div>
        </div>
        <p className="text-xs text-gray-500 leading-relaxed">
          You're running on {status.platform} — Plutus already has full access to Linux tools
          like package managers, compilers, Docker, SSH, and everything else.
          No extra setup needed.
        </p>
      </div>
    );
  }

  // Windows — show toggle + setup
  return (
    <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-orange-500/10 flex items-center justify-center">
          <Terminal className="w-5 h-5 text-orange-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-200">Linux Superpowers (WSL)</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Give Plutus access to a full Linux toolbox on Windows
          </p>
        </div>
        {/* Status badge */}
        {status.setup_completed && status.enabled ? (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">Active</span>
          </div>
        ) : status.enabled && !status.setup_completed ? (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span className="text-xs text-amber-400 font-medium">Setup needed</span>
          </div>
        ) : null}
      </div>

      {/* What is WSL — simple explanation */}
      <div className="bg-gray-900/60 rounded-lg p-4 mb-4 border border-gray-800/40">
        <p className="text-xs text-gray-400 leading-relaxed">
          <span className="text-gray-300 font-medium">What is this?</span>{" "}
          WSL (Windows Subsystem for Linux) lets Plutus run Linux programs right on your
          Windows PC — no virtual machine or dual-boot needed. Think of it as giving your
          computer a second brain that speaks Linux.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {[
            { label: "Package managers", desc: "apt, pip, npm" },
            { label: "Dev tools", desc: "Docker, Git, compilers" },
            { label: "Shell scripting", desc: "Bash, Python, Node" },
            { label: "Server tools", desc: "SSH, nginx, databases" },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center gap-2 text-[11px] text-gray-500"
            >
              <Zap className="w-3 h-3 text-orange-400/60 shrink-0" />
              <span>
                <span className="text-gray-400">{item.label}</span> — {item.desc}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Toggle */}
      <div className="flex items-center justify-between py-3 border-t border-gray-800/40">
        <div>
          <p className="text-sm text-gray-300">Enable WSL integration</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {status.enabled
              ? "Plutus can use Linux tools via WSL"
              : "Turn this on to unlock Linux capabilities"}
          </p>
        </div>
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-200 ${
            status.enabled ? "bg-orange-500" : "bg-gray-700"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
              status.enabled ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>

      {/* Setup button — only show if enabled but not set up */}
      {status.enabled && !status.setup_completed && (
        <div className="mt-3">
          <button
            onClick={() => setShowGuide(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 hover:border-orange-500/30 text-orange-400 text-sm font-medium transition-all"
          >
            <Monitor className="w-4 h-4" />
            Set up WSL — takes about 10 minutes
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* WSL already installed indicator */}
      {status.wsl_installed && !status.setup_completed && status.enabled && (
        <p className="text-xs text-emerald-400/80 mt-3 flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" />
          WSL is already installed on your system. You can skip most of the setup.
        </p>
      )}

      {/* Setup guide modal */}
      {showGuide && (
        <WSLSetupGuide
          wslAlreadyInstalled={status.wsl_installed}
          onClose={() => {
            setShowGuide(false);
            fetchStatus();
          }}
        />
      )}
    </div>
  );
}

/* ─── Step-by-step setup guide (modal overlay) ─────────── */

function WSLSetupGuide({
  wslAlreadyInstalled,
  onClose,
}: {
  wslAlreadyInstalled: boolean;
  onClose: () => void;
}) {
  const [steps, setSteps] = useState<SetupStep[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const [finishing, setFinishing] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  useEffect(() => {
    api
      .getWSLSetupGuide()
      .then((guide) => {
        if (!guide.needed) {
          // Not needed — close
          onClose();
          return;
        }
        setSteps(guide.steps);
        // If WSL already installed, auto-complete the first step
        if (wslAlreadyInstalled && guide.steps.length > 0) {
          setCompletedSteps(new Set([guide.steps[0].id, guide.steps[1]?.id].filter(Boolean)));
          // Jump to verify step
          const verifyIdx = guide.steps.findIndex((s) => s.id === "verify");
          if (verifyIdx >= 0) setCurrentStep(verifyIdx);
          else setCurrentStep(guide.steps.length - 1);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [wslAlreadyInstalled, onClose]);

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

  const handleFinish = async () => {
    setFinishing(true);
    try {
      await api.completeWSLSetup();
    } catch {
      // still close
    } finally {
      setFinishing(false);
      onClose();
    }
  };

  const allDone = steps.length > 0 && steps.every((s) => completedSteps.has(s.id));
  const step = steps[currentStep];

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6">
      <div className="bg-gray-950 border border-gray-800/60 rounded-2xl w-full max-w-xl shadow-2xl">
        {/* Header */}
        <div className="p-6 border-b border-gray-800/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-600/20">
              <Terminal className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-100">
                Setting up Linux Superpowers
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Follow these steps to give Plutus full Linux access
              </p>
            </div>
          </div>

          {/* Progress dots */}
          {steps.length > 0 && (
            <div className="flex items-center gap-2 mt-4">
              {steps.map((s, i) => (
                <div
                  key={s.id}
                  className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
                    completedSteps.has(s.id)
                      ? "bg-orange-500"
                      : i === currentStep
                      ? "bg-orange-500/40"
                      : "bg-gray-800"
                  }`}
                />
              ))}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="p-6 min-h-[280px]">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-8 h-8 border-2 border-orange-500/30 border-t-orange-500 rounded-full animate-spin" />
            </div>
          ) : step ? (
            <div className="animate-onboard-in">
              {/* Step indicator */}
              <div className="flex items-center gap-2 mb-4">
                <span className="text-xs text-orange-400/80 font-medium px-2 py-0.5 bg-orange-500/10 rounded-md">
                  Step {currentStep + 1} of {steps.length}
                </span>
                {completedSteps.has(step.id) && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Done
                  </span>
                )}
              </div>

              {/* Step title */}
              <h3 className="text-xl font-bold text-gray-100 mb-2">{step.title}</h3>

              {/* Description */}
              <p className="text-sm text-gray-400 leading-relaxed mb-4">
                {step.description}
              </p>

              {/* Command box */}
              {step.command && (
                <div className="relative group mb-4">
                  <div className="bg-gray-900 rounded-lg border border-gray-800/60 p-4 font-mono text-sm text-orange-300">
                    {step.command}
                  </div>
                  <button
                    onClick={() => copyCommand(step.command!)}
                    className="absolute top-2 right-2 p-2 rounded-lg bg-gray-800/80 hover:bg-gray-700/80 text-gray-400 hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-all"
                    title="Copy command"
                  >
                    {copiedCmd === step.command ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                </div>
              )}

              {/* Reboot step — special visual */}
              {step.id === "reboot" && (
                <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20 mb-4">
                  <RotateCcw className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-amber-300 font-medium">Restart required</p>
                    <p className="text-xs text-amber-400/60 mt-1">
                      After restarting, come back to Plutus and continue from where you left off.
                      Your progress is saved automatically.
                    </p>
                  </div>
                </div>
              )}

              {/* Note */}
              <div className="bg-gray-900/40 rounded-lg p-3 border border-gray-800/30">
                <p className="text-xs text-gray-500 leading-relaxed">
                  <span className="text-gray-400 font-medium">Tip:</span> {step.note}
                </p>
              </div>

              {/* Mark done button */}
              {!completedSteps.has(step.id) && (
                <button
                  onClick={() => markStepDone(step.id)}
                  className="mt-5 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 text-orange-400 text-sm font-medium transition-all"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  I've done this step
                </button>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer navigation */}
        <div className="p-6 border-t border-gray-800/60 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {currentStep > 0 && (
              <button
                onClick={() => setCurrentStep(currentStep - 1)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 transition-all"
              >
                <ChevronLeft className="w-4 h-4" />
                Previous
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-sm text-gray-500 hover:text-gray-300 hover:bg-gray-800/60 transition-all"
            >
              {allDone ? "Close" : "I'll do this later"}
            </button>

            {allDone ? (
              <button
                onClick={handleFinish}
                disabled={finishing}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-orange-500 hover:bg-orange-400 disabled:opacity-60 text-white text-sm font-medium transition-all shadow-lg shadow-orange-500/20"
              >
                {finishing ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                {finishing ? "Finishing..." : "Activate Superpowers"}
              </button>
            ) : currentStep < steps.length - 1 ? (
              <button
                onClick={() => setCurrentStep(currentStep + 1)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm font-medium transition-all"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

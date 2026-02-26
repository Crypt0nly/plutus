import { useState, useEffect } from "react";
import {
  Terminal,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  CheckCircle2,
  Copy,
  RotateCcw,
  Zap,
  Monitor,
  AlertTriangle,
  ExternalLink,
  Package,
  Code2,
  Server,
  Box,
  HelpCircle,
  Info,
  ShieldCheck,
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
  substeps?: string[];
  command: string | null;
  command_verify?: string;
  note: string;
  warning?: string | null;
}

interface Prerequisite {
  id: string;
  label: string;
  detail: string;
}

interface TroubleshootItem {
  id: string;
  problem: string;
  solution: string;
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
            { icon: Package, label: "Package managers", desc: "apt, pip, npm" },
            { icon: Code2, label: "Dev tools", desc: "Docker, Git, compilers" },
            { icon: Box, label: "Shell scripting", desc: "Bash, Python, Node" },
            { icon: Server, label: "Server tools", desc: "SSH, nginx, databases" },
          ].map((item) => (
            <div
              key={item.label}
              className="flex items-center gap-2 text-[11px] text-gray-500"
            >
              <item.icon className="w-3 h-3 text-orange-400/60 shrink-0" />
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
  const [prerequisites, setPrerequisites] = useState<Prerequisite[]>([]);
  const [troubleshooting, setTroubleshooting] = useState<TroubleshootItem[]>([]);
  const [currentStep, setCurrentStep] = useState(-1); // -1 = prereqs screen
  const [loading, setLoading] = useState(true);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const [finishing, setFinishing] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);
  const [prereqsChecked, setPrereqsChecked] = useState(false);
  const [showTroubleshooting, setShowTroubleshooting] = useState(false);
  const [expandedTroubleshoot, setExpandedTroubleshoot] = useState<string | null>(null);

  useEffect(() => {
    api
      .getWSLSetupGuide()
      .then((guide) => {
        if (!guide.needed) {
          onClose();
          return;
        }
        setSteps(guide.steps);
        setPrerequisites(guide.prerequisites || []);
        setTroubleshooting(guide.troubleshooting || []);

        if (wslAlreadyInstalled && guide.steps.length > 0) {
          const autoComplete = new Set<string>();
          for (const s of guide.steps) {
            if (s.id === "open_terminal" || s.id === "install_wsl" || s.id === "reboot") {
              autoComplete.add(s.id);
            }
          }
          setCompletedSteps(autoComplete);
          setPrereqsChecked(true);
          // Jump to first incomplete step
          const firstIncomplete = guide.steps.findIndex((s) => !autoComplete.has(s.id));
          setCurrentStep(firstIncomplete >= 0 ? firstIncomplete : guide.steps.length - 1);
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
  const step = currentStep >= 0 ? steps[currentStep] : null;
  const totalScreens = steps.length + 1; // +1 for prereqs
  const currentScreen = currentStep + 1; // 0 = prereqs

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6">
      <div className="bg-gray-950 border border-gray-800/60 rounded-2xl w-full max-w-2xl shadow-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-800/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500 to-amber-600 flex items-center justify-center shadow-lg shadow-orange-600/20">
              <Terminal className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-bold text-gray-100">
                WSL Setup Guide
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {currentStep < 0
                  ? "Before we start, check these requirements"
                  : `Step ${currentStep + 1} of ${steps.length} — ${step?.title || ""}`}
              </p>
            </div>
            {wslAlreadyInstalled && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-[10px] text-emerald-400 font-medium">WSL detected</span>
              </div>
            )}
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-1.5 mt-4">
            {/* Prereqs dot */}
            <div
              className={`h-1.5 w-8 rounded-full transition-all duration-300 ${
                prereqsChecked ? "bg-orange-500" : currentStep < 0 ? "bg-orange-500/40" : "bg-gray-800"
              }`}
            />
            {/* Step dots */}
            {steps.map((s, i) => (
              <div
                key={s.id}
                className={`h-1.5 flex-1 rounded-full transition-all duration-300 cursor-pointer ${
                  completedSteps.has(s.id)
                    ? "bg-orange-500"
                    : i === currentStep
                    ? "bg-orange-500/40"
                    : "bg-gray-800"
                }`}
                onClick={() => {
                  if (prereqsChecked) setCurrentStep(i);
                }}
              />
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-8 h-8 border-2 border-orange-500/30 border-t-orange-500 rounded-full animate-spin" />
            </div>
          ) : currentStep < 0 ? (
            /* ─── Prerequisites screen ──────────────────── */
            <div className="animate-onboard-in">
              <div className="flex items-center gap-2 mb-5">
                <ShieldCheck className="w-5 h-5 text-orange-400" />
                <h3 className="text-lg font-bold text-gray-100">Before you start</h3>
              </div>
              <p className="text-sm text-gray-400 mb-5">
                Make sure your system meets these requirements. Most modern Windows PCs will be fine.
              </p>

              <div className="space-y-3">
                {prerequisites.map((p) => (
                  <PrereqItem key={p.id} prereq={p} />
                ))}
              </div>

              <div className="mt-6 p-4 rounded-xl bg-blue-500/5 border border-blue-500/15">
                <div className="flex items-start gap-2.5">
                  <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-xs text-blue-300 font-medium">How long does this take?</p>
                    <p className="text-xs text-blue-400/60 mt-1 leading-relaxed">
                      The entire setup takes about 10-15 minutes, including a required restart.
                      Most of that time is waiting for downloads. You'll need to interact
                      for about 2 minutes total.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : step ? (
            /* ─── Step content ──────────────────────────── */
            <div className="animate-onboard-in">
              {/* Step indicator */}
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg bg-orange-500/15 flex items-center justify-center">
                  <span className="text-sm font-bold text-orange-400">{currentStep + 1}</span>
                </div>
                <h3 className="text-lg font-bold text-gray-100 flex-1">{step.title}</h3>
                {completedSteps.has(step.id) && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Done
                  </span>
                )}
              </div>

              {/* Description */}
              <p className="text-sm text-gray-400 leading-relaxed mb-4">
                {step.description}
              </p>

              {/* Sub-steps */}
              {step.substeps && step.substeps.length > 0 && (
                <div className="space-y-2 mb-4 bg-gray-900/40 rounded-xl p-4 border border-gray-800/30">
                  {step.substeps.map((sub, i) => (
                    <div key={i} className="flex items-start gap-3 text-sm">
                      <div className="w-5 h-5 rounded-full bg-orange-500/10 flex items-center justify-center shrink-0 mt-0.5">
                        <span className="text-[10px] font-bold text-orange-400">{i + 1}</span>
                      </div>
                      <span className="text-gray-400 leading-relaxed">{sub}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Command box */}
              {step.command && (
                <div className="relative group mb-4">
                  <div className="bg-gray-900 rounded-xl border border-gray-800/60 p-4 font-mono text-sm text-orange-300 overflow-x-auto">
                    <span className="text-gray-600 select-none mr-2">&gt;</span>
                    {step.command}
                  </div>
                  <button
                    onClick={() => copyCommand(step.command!)}
                    className="absolute top-2.5 right-2.5 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-800/90 hover:bg-gray-700/90 text-gray-400 hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-all border border-gray-700/50"
                  >
                    {copiedCmd === step.command ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-[11px] text-emerald-400 font-medium">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span className="text-[11px] font-medium">Copy</span>
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Verify command */}
              {step.command_verify && (
                <div className="relative group mb-4">
                  <p className="text-xs text-gray-500 mb-2">Then verify with this command:</p>
                  <div className="bg-gray-900 rounded-xl border border-gray-800/60 p-4 font-mono text-sm text-orange-300/80 overflow-x-auto">
                    <span className="text-gray-600 select-none mr-2">&gt;</span>
                    {step.command_verify}
                  </div>
                  <button
                    onClick={() => copyCommand(step.command_verify!)}
                    className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gray-800/90 hover:bg-gray-700/90 text-gray-400 hover:text-gray-200 opacity-0 group-hover:opacity-100 transition-all border border-gray-700/50"
                  >
                    {copiedCmd === step.command_verify ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-[11px] text-emerald-400 font-medium">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span className="text-[11px] font-medium">Copy</span>
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Reboot step — special visual */}
              {step.id === "reboot" && (
                <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20 mb-4">
                  <RotateCcw className="w-5 h-5 text-amber-400 shrink-0 mt-0.5 animate-pulse" />
                  <div>
                    <p className="text-sm text-amber-300 font-medium">Restart required</p>
                    <p className="text-xs text-amber-400/60 mt-1 leading-relaxed">
                      After restarting, come back to Plutus and continue from where you left off.
                      Your progress is saved automatically.
                    </p>
                  </div>
                </div>
              )}

              {/* Warning */}
              {step.warning && (
                <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20 mb-4">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-amber-300/80 leading-relaxed">{step.warning}</p>
                </div>
              )}

              {/* Tip */}
              <div className="bg-gray-900/40 rounded-xl p-4 border border-gray-800/30">
                <div className="flex items-start gap-2.5">
                  <Info className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-gray-500 leading-relaxed">
                    <span className="text-gray-400 font-medium">Tip:</span> {step.note}
                  </p>
                </div>
              </div>

              {/* Mark done button */}
              {!completedSteps.has(step.id) && (
                <button
                  onClick={() => markStepDone(step.id)}
                  className="mt-5 flex items-center gap-2 px-5 py-3 rounded-xl bg-orange-500/10 hover:bg-orange-500/20 border border-orange-500/20 text-orange-400 text-sm font-medium transition-all"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  I've completed this step
                </button>
              )}
            </div>
          ) : null}

          {/* ─── Troubleshooting section ──────────────── */}
          {currentStep >= 0 && troubleshooting.length > 0 && (
            <div className="mt-6 border-t border-gray-800/40 pt-4">
              <button
                onClick={() => setShowTroubleshooting(!showTroubleshooting)}
                className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors w-full"
              >
                <HelpCircle className="w-4 h-4" />
                <span className="flex-1 text-left">
                  {showTroubleshooting ? "Hide troubleshooting" : "Having issues? Click for common fixes"}
                </span>
                <ChevronDown
                  className={`w-4 h-4 transition-transform ${showTroubleshooting ? "rotate-180" : ""}`}
                />
              </button>

              {showTroubleshooting && (
                <div className="mt-3 space-y-2">
                  {troubleshooting.map((t) => (
                    <div
                      key={t.id}
                      className="bg-gray-900/50 rounded-xl border border-gray-800/40 overflow-hidden"
                    >
                      <button
                        onClick={() =>
                          setExpandedTroubleshoot(expandedTroubleshoot === t.id ? null : t.id)
                        }
                        className="w-full flex items-center gap-2.5 p-3.5 text-left hover:bg-gray-800/30 transition-colors"
                      >
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400/60 shrink-0" />
                        <span className="text-xs font-medium text-gray-300 flex-1">
                          {t.problem}
                        </span>
                        <ChevronRight
                          className={`w-3.5 h-3.5 text-gray-600 transition-transform ${
                            expandedTroubleshoot === t.id ? "rotate-90" : ""
                          }`}
                        />
                      </button>
                      {expandedTroubleshoot === t.id && (
                        <div className="px-3.5 pb-3.5 pt-0">
                          <p className="text-xs text-gray-500 leading-relaxed whitespace-pre-line border-t border-gray-800/40 pt-3">
                            {t.solution}
                          </p>
                        </div>
                      )}
                    </div>
                  ))}

                  <a
                    href="https://learn.microsoft.com/en-us/windows/wsl/troubleshooting"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors mt-2 pl-1"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    Microsoft's official WSL troubleshooting guide
                  </a>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer navigation */}
        <div className="p-6 border-t border-gray-800/60 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            {currentStep >= 0 && (
              <button
                onClick={() => setCurrentStep(currentStep > 0 ? currentStep - 1 : -1)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 transition-all"
              >
                <ChevronLeft className="w-4 h-4" />
                {currentStep === 0 ? "Requirements" : "Previous"}
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

            {currentStep < 0 ? (
              /* Prereqs screen -> start setup */
              <button
                onClick={() => {
                  setPrereqsChecked(true);
                  setCurrentStep(0);
                }}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-orange-500 hover:bg-orange-400 text-white text-sm font-medium transition-all shadow-lg shadow-orange-500/20"
              >
                Start Setup
                <ChevronRight className="w-4 h-4" />
              </button>
            ) : allDone ? (
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

/* ─── Prerequisite checklist item ──────────────────────── */

function PrereqItem({ prereq }: { prereq: Prerequisite }) {
  const [checked, setChecked] = useState(false);
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-xl border transition-all ${
        checked
          ? "bg-emerald-500/5 border-emerald-500/20"
          : "bg-gray-900/40 border-gray-800/40"
      }`}
    >
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={() => setChecked(!checked)}
          className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-all ${
            checked
              ? "bg-emerald-500 border-emerald-500"
              : "border-gray-600 hover:border-gray-400"
          }`}
        >
          {checked && <CheckCircle2 className="w-3 h-3 text-white" />}
        </button>
        <span
          className={`text-sm flex-1 ${
            checked ? "text-emerald-300" : "text-gray-300"
          }`}
        >
          {prereq.label}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-600 hover:text-gray-400 transition-colors p-1"
        >
          <ChevronRight
            className={`w-4 h-4 transition-transform ${expanded ? "rotate-90" : ""}`}
          />
        </button>
      </div>
      {expanded && (
        <div className="px-4 pb-4 pt-0 pl-12">
          <p className="text-xs text-gray-500 leading-relaxed">{prereq.detail}</p>
        </div>
      )}
    </div>
  );
}

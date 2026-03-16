import React, { useEffect, useState, useCallback } from "react";
import { Zap, Globe, EyeOff, RefreshCw, CheckCircle, AlertCircle, ExternalLink, FolderOpen } from "lucide-react";
import { api } from "../../lib/api";

interface BrowserInfo {
  kind: string;
  name: string;
  path: string;
  version: string;
  is_default: boolean;
}

interface BrowserConfigData {
  mode: string;
  executable_path: string;
  cdp_port: number;
  use_profile: boolean;
}

// ── Inline SVG browser logos ──────────────────────────────────────────────────

function ChromeIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" fill="#fff" />
      <circle cx="12" cy="12" r="4.2" fill="#4285F4" />
      <path d="M12 7.8h8.66A10 10 0 0 0 3.34 7.8z" fill="#EA4335" />
      <path d="M3.34 7.8 7.8 15.6A10 10 0 0 1 3.34 7.8z" fill="#FBBC05" />
      <path d="M7.8 15.6 12 7.8H3.34A10 10 0 0 0 7.8 15.6z" fill="#FBBC05" />
      <path d="M12 16.2 7.8 15.6A10 10 0 0 0 20.66 7.8H12z" fill="#34A853" />
      <path d="M16.2 12a4.2 4.2 0 0 1-4.2 4.2V16.2A10 10 0 0 0 20.66 7.8H12v.6a4.2 4.2 0 0 1 4.2 3.6z" fill="#34A853" />
    </svg>
  );
}

function BraveIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M12 2L4 5.5l1.2 9.8L12 22l6.8-6.7L20 5.5 12 2z" fill="#FB542B" />
      <path d="M15.5 9.5c.3.6.2 1.3-.2 1.8l-1.1 1.4c-.2.3-.2.7 0 1l.8 1c.4.5.3 1.2-.2 1.6l-2.8 2.2-2.8-2.2c-.5-.4-.6-1.1-.2-1.6l.8-1c.2-.3.2-.7 0-1L8.7 11.3c-.4-.5-.5-1.2-.2-1.8l.5-1c.3-.6 1-.9 1.6-.6l1.4.6 1.4-.6c.6-.3 1.3 0 1.6.6l.5 1z" fill="white" />
    </svg>
  );
}

function EdgeIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M21.9 13.6c-.3 3.7-3.1 6.8-6.7 7.8-1.1.3-2.3.4-3.4.2-1.2-.2-2.3-.7-3.2-1.5-.9-.7-1.6-1.7-2-2.8-.4-1.1-.5-2.3-.2-3.4.3-1.2.9-2.2 1.8-3 .9-.8 2-1.3 3.2-1.5 1.2-.2 2.4 0 3.5.5 1.1.5 2 1.3 2.6 2.3.6 1 .9 2.2.7 3.4-.2 1.2-.8 2.3-1.7 3.1-.9.8-2 1.2-3.2 1.2H12c-1.7 0-3.3-.7-4.5-1.9C6.3 17 5.6 15.4 5.6 13.7c0-.6.1-1.2.2-1.8C6.5 8.4 9.3 5.8 12.8 5c1.7-.4 3.5-.3 5.2.3 1.6.6 3 1.7 4 3.1.9 1.4 1.3 3 1.2 4.6l-.3.6z" fill="url(#edge-grad)" />
      <defs>
        <linearGradient id="edge-grad" x1="4" y1="4" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0078D4" />
          <stop offset="1" stopColor="#50E6FF" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function ChromiumIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" fill="#e8e8e8" />
      <circle cx="12" cy="12" r="4.2" fill="#9AA0A6" />
      <path d="M12 7.8h8.66A10 10 0 0 0 3.34 7.8z" fill="#BDBDBD" />
      <path d="M3.34 7.8 7.8 15.6A10 10 0 0 1 3.34 7.8z" fill="#9AA0A6" />
      <path d="M7.8 15.6 12 7.8H3.34A10 10 0 0 0 7.8 15.6z" fill="#9AA0A6" />
    </svg>
  );
}

function VivaldiIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" fill="#EF3939" />
      <path d="M12 16.5c-2.5-2.5-5-5.5-5-8.5h10c0 3-2.5 6-5 8.5z" fill="white" opacity="0.9" />
    </svg>
  );
}

function OperaIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" fill="#FF1B2D" />
      <ellipse cx="12" cy="12" rx="4" ry="6.5" fill="none" stroke="white" strokeWidth="2" />
    </svg>
  );
}

function ArcIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <defs>
        <linearGradient id="arc-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF6B6B" />
          <stop offset="0.5" stopColor="#A855F7" />
          <stop offset="1" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="10" fill="url(#arc-grad)" />
      <path d="M8 16 12 7l4 9" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M9.5 13h5" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function GenericBrowserIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="#6B7280" strokeWidth="1.5" fill="none" />
      <path d="M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20M2 12h20" stroke="#6B7280" strokeWidth="1.5" />
    </svg>
  );
}

function BrowserIcon({ kind, size = 20 }: { kind: string; size?: number }) {
  switch (kind) {
    case "chrome":   return <ChromeIcon size={size} />;
    case "canary":   return <ChromeIcon size={size} />;
    case "brave":    return <BraveIcon size={size} />;
    case "edge":     return <EdgeIcon size={size} />;
    case "chromium": return <ChromiumIcon size={size} />;
    case "vivaldi":  return <VivaldiIcon size={size} />;
    case "opera":    return <OperaIcon size={size} />;
    case "arc":      return <ArcIcon size={size} />;
    default:         return <GenericBrowserIcon size={size} />;
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

export function BrowserConfig({
  config,
  onUpdate,
}: {
  config: BrowserConfigData;
  onUpdate: (patch: Record<string, unknown>) => void;
}) {
  const [browsers, setBrowsers] = useState<BrowserInfo[]>([]);
  const [scanning, setScanning] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launchStatus, setLaunchStatus] = useState<"idle" | "ok" | "error">("idle");
  const [launchMsg, setLaunchMsg] = useState("");
  const [scanned, setScanned] = useState(false);
  const [customPath, setCustomPath] = useState("");
  const [customPathError, setCustomPathError] = useState("");

  const scanBrowsers = useCallback(async () => {
    setScanning(true);
    try {
      const result = await api.detectBrowsers();
      setBrowsers(result.browsers || []);
      setScanned(true);
    } catch {
      setBrowsers([]);
      setScanned(true);
    } finally {
      setScanning(false);
    }
  }, []);

  useEffect(() => {
    if (!scanned && config.mode === "user") {
      scanBrowsers();
    }
  }, [scanned, config.mode, scanBrowsers]);

  // Auto-scan when switching to user mode
  const handleModeChange = (mode: string) => {
    onUpdate({ browser: { ...config, mode } });
    if (mode === "user" && !scanned) {
      scanBrowsers();
    }
  };

  const handleBrowserSelect = (path: string) => {
    onUpdate({ browser: { ...config, executable_path: path } });
  };

  const handleUseProfileToggle = () => {
    onUpdate({ browser: { ...config, use_profile: !config.use_profile } });
  };

  const handleLaunch = async () => {
    if (!config.executable_path) return;
    setLaunching(true);
    setLaunchStatus("idle");
    try {
      const res = await api.launchBrowserForCDP({
        executable_path: config.executable_path,
        cdp_port: config.cdp_port || 9222,
        use_profile: config.use_profile,
      });
      setLaunchStatus("ok");
      setLaunchMsg(res.message || "Browser launched successfully");
    } catch (e: any) {
      setLaunchStatus("error");
      setLaunchMsg(e?.message || "Failed to launch browser");
    } finally {
      setLaunching(false);
    }
  };

  const selectedBrowser = browsers.find((b) => b.path === config.executable_path);
  // If the configured path isn't in the detected list, it's a custom path
  const isCustomPath = config.executable_path && !selectedBrowser;

  const handleCustomPathApply = () => {
    const p = customPath.trim();
    if (!p) return;
    if (!p.includes("/") && !p.includes("\\")) {
      setCustomPathError("Please enter a full path to the executable");
      return;
    }
    setCustomPathError("");
    handleBrowserSelect(p);
    setCustomPath("");
  };

  const modes = [
    {
      id: "auto",
      label: "Auto",
      icon: <Zap size={15} />,
      desc: "Connect to existing browser or launch Chromium",
      color: "rgba(251, 191, 36, 0.9)",
      bg: "rgba(251, 191, 36, 0.08)",
      border: "rgba(251, 191, 36, 0.2)",
    },
    {
      id: "user",
      label: "My Browser",
      icon: <Globe size={15} />,
      desc: "Use your real browser — inherits all logins & cookies",
      color: "rgba(99, 179, 237, 0.9)",
      bg: "rgba(99, 179, 237, 0.08)",
      border: "rgba(99, 179, 237, 0.2)",
    },
    {
      id: "headless",
      label: "Headless",
      icon: <EyeOff size={15} />,
      desc: "Invisible Chromium — fastest, no UI shown",
      color: "rgba(156, 163, 175, 0.9)",
      bg: "rgba(156, 163, 175, 0.08)",
      border: "rgba(156, 163, 175, 0.2)",
    },
  ];

  return (
    <div className="space-y-6">

      {/* Mode selector */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider mb-3"
           style={{ color: "rgb(var(--text-secondary))" }}>
          Browser Mode
        </p>
        <div className="grid grid-cols-3 gap-2">
          {modes.map((opt) => {
            const active = config.mode === opt.id;
            return (
              <button
                key={opt.id}
                onClick={() => handleModeChange(opt.id)}
                className="relative flex flex-col gap-2 p-3.5 rounded-xl text-left transition-all duration-150"
                style={{
                  background: active ? opt.bg : "rgb(var(--surface))",
                  border: `1px solid ${active ? opt.border : "rgb(var(--border))"}`,
                  boxShadow: active ? `0 0 0 1px ${opt.border}` : "none",
                }}
              >
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center"
                  style={{
                    background: active ? opt.bg : "rgb(var(--surface-alt))",
                    border: `1px solid ${active ? opt.border : "rgb(var(--border))"}`,
                    color: active ? opt.color : "rgb(var(--text-secondary))",
                  }}
                >
                  {opt.icon}
                </div>
                <div>
                  <p className="text-sm font-semibold leading-tight"
                     style={{ color: active ? "rgb(var(--text-primary))" : "rgb(var(--text-secondary))" }}>
                    {opt.label}
                  </p>
                  <p className="text-xs leading-snug mt-0.5"
                     style={{ color: "rgb(var(--text-secondary))", opacity: 0.75 }}>
                    {opt.desc}
                  </p>
                </div>
                {active && (
                  <div
                    className="absolute top-2.5 right-2.5 w-1.5 h-1.5 rounded-full"
                    style={{ background: opt.color }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Browser picker */}
      {config.mode === "user" && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-wider"
               style={{ color: "rgb(var(--text-secondary))" }}>
              Select Browser
            </p>
            <button
              onClick={scanBrowsers}
              disabled={scanning}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-colors"
              style={{
                background: "rgb(var(--surface))",
                color: "rgb(var(--text-secondary))",
                border: "1px solid rgb(var(--border))",
              }}
            >
              <RefreshCw size={11} className={scanning ? "animate-spin" : ""} />
              {scanning ? "Scanning…" : "Rescan"}
            </button>
          </div>

          {scanning && (
            <div className="flex items-center justify-center gap-2 py-6 rounded-xl"
                 style={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--border))" }}>
              <RefreshCw size={14} className="animate-spin" style={{ color: "rgb(var(--text-secondary))" }} />
              <span className="text-sm" style={{ color: "rgb(var(--text-secondary))" }}>
                Scanning for installed browsers…
              </span>
            </div>
          )}

          {!scanning && scanned && browsers.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-5 rounded-xl text-center"
                 style={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--border))" }}>
              <Globe size={20} style={{ color: "rgb(var(--text-secondary))", opacity: 0.4 }} />
              <p className="text-sm" style={{ color: "rgb(var(--text-secondary))" }}>
                No browsers detected automatically
              </p>
              <p className="text-xs" style={{ color: "rgb(var(--text-secondary))", opacity: 0.6 }}>
                Use the custom path field below to add your browser
              </p>
            </div>
          )}

          {!scanning && browsers.length > 0 && (
            <div className="space-y-2">
              {/* Show custom path entry at top if current selection isn't in detected list */}
              {isCustomPath && (
                <div
                  className="flex items-center gap-3 px-4 py-3 rounded-xl"
                  style={{
                    background: "rgba(99, 179, 237, 0.08)",
                    border: "1px solid rgba(99, 179, 237, 0.35)",
                  }}
                >
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: "rgba(99,179,237,0.1)", border: "1px solid rgba(99,179,237,0.2)" }}
                  >
                    <GenericBrowserIcon size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold" style={{ color: "rgb(var(--text-primary))" }}>
                      Custom Browser
                    </p>
                    <p className="text-xs truncate font-mono mt-0.5" style={{ color: "rgb(var(--text-secondary))", opacity: 0.6 }}>
                      {config.executable_path}
                    </p>
                  </div>
                  <CheckCircle size={16} style={{ color: "rgba(99,179,237,0.9)", flexShrink: 0 }} />
                </div>
              )}
              {browsers.map((b) => {
                const isSelected = config.executable_path === b.path;
                return (
                  <button
                    key={b.path}
                    onClick={() => handleBrowserSelect(b.path)}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all duration-150"
                    style={{
                      background: isSelected
                        ? "rgba(99, 179, 237, 0.08)"
                        : "rgb(var(--surface))",
                      border: `1px solid ${isSelected
                        ? "rgba(99, 179, 237, 0.35)"
                        : "rgb(var(--border))"}`,
                    }}
                  >
                    {/* Browser logo */}
                    <div
                      className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{
                        background: isSelected ? "rgba(99,179,237,0.1)" : "rgb(var(--surface-alt))",
                        border: `1px solid ${isSelected ? "rgba(99,179,237,0.2)" : "rgb(var(--border))"}`,
                      }}
                    >
                      <BrowserIcon kind={b.kind} size={20} />
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold"
                              style={{ color: "rgb(var(--text-primary))" }}>
                          {b.name}
                        </span>
                        {b.is_default && (
                          <span
                            className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                            style={{
                              background: "rgba(99,179,237,0.12)",
                              color: "rgba(99,179,237,0.9)",
                              border: "1px solid rgba(99,179,237,0.2)",
                            }}
                          >
                            Default
                          </span>
                        )}
                        {b.version && (
                          <span className="text-xs font-mono"
                                style={{ color: "rgb(var(--text-secondary))", opacity: 0.7 }}>
                            v{b.version}
                          </span>
                        )}
                      </div>
                      <p className="text-xs truncate mt-0.5 font-mono"
                         style={{ color: "rgb(var(--text-secondary))", opacity: 0.5 }}>
                        {b.path}
                      </p>
                    </div>

                    {/* Selected indicator */}
                    {isSelected
                      ? <CheckCircle size={16} style={{ color: "rgba(99,179,237,0.9)", flexShrink: 0 }} />
                      : <div className="w-4 h-4 rounded-full flex-shrink-0"
                             style={{ border: "1.5px solid rgb(var(--border))" }} />
                    }
                  </button>
                );
              })}
            </div>
          )}

          {/* Manual path input */}
          <div className="mt-3">
            <p className="text-xs font-semibold uppercase tracking-wider mb-2"
               style={{ color: "rgb(var(--text-secondary))" }}>
              Or enter path manually
            </p>
            <div className="flex gap-2">
              <div
                className="flex-1 flex items-center gap-2 px-3 py-2.5 rounded-xl"
                style={{
                  background: "rgb(var(--surface))",
                  border: `1px solid ${customPathError ? "rgba(239,68,68,0.5)" : "rgb(var(--border))"}`,
                }}
              >
                <FolderOpen size={13} style={{ color: "rgb(var(--text-secondary))", flexShrink: 0, opacity: 0.6 }} />
                <input
                  type="text"
                  value={customPath}
                  onChange={(e) => { setCustomPath(e.target.value); setCustomPathError(""); }}
                  onKeyDown={(e) => e.key === "Enter" && handleCustomPathApply()}
                  placeholder="C:\Program Files\Comet\Application\comet.exe"
                  className="flex-1 bg-transparent text-xs outline-none font-mono"
                  style={{ color: "rgb(var(--text-primary))" }}
                  spellCheck={false}
                />
              </div>
              <button
                onClick={handleCustomPathApply}
                disabled={!customPath.trim()}
                className="px-3 py-2 rounded-xl text-xs font-semibold transition-all"
                style={{
                  background: customPath.trim() ? "rgba(99,179,237,0.15)" : "rgb(var(--surface))",
                  border: `1px solid ${customPath.trim() ? "rgba(99,179,237,0.3)" : "rgb(var(--border))"}`,
                  color: customPath.trim() ? "rgba(99,179,237,0.9)" : "rgb(var(--text-secondary))",
                  cursor: customPath.trim() ? "pointer" : "not-allowed",
                }}
              >
                Use this
              </button>
            </div>
            {customPathError && (
              <p className="text-xs mt-1.5" style={{ color: "rgba(239,68,68,0.8)" }}>
                {customPathError}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Use profile toggle + Launch */}
      {config.mode === "user" && config.executable_path && (
        <div className="space-y-3">
          {/* Use profile row */}
          <div
            className="flex items-center justify-between px-4 py-3 rounded-xl"
            style={{
              background: "rgb(var(--surface))",
              border: "1px solid rgb(var(--border))",
            }}
          >
            <div>
              <p className="text-sm font-medium" style={{ color: "rgb(var(--text-primary))" }}>
                Use existing profile
              </p>
              <p className="text-xs mt-0.5" style={{ color: "rgb(var(--text-secondary))", opacity: 0.7 }}>
                Inherit your logins, cookies, and saved passwords
              </p>
            </div>
            <button
              onClick={handleUseProfileToggle}
              className="relative w-10 h-5.5 rounded-full transition-colors duration-200 flex-shrink-0"
              style={{
                width: 40,
                height: 22,
                background: config.use_profile
                  ? "rgba(99,179,237,0.8)"
                  : "rgb(var(--surface-alt))",
                border: `1px solid ${config.use_profile ? "rgba(99,179,237,0.5)" : "rgb(var(--border))"}`,
              }}
              role="switch"
              aria-checked={config.use_profile}
            >
              <span
                className="absolute top-0.5 rounded-full transition-transform duration-200"
                style={{
                  width: 18,
                  height: 18,
                  background: "white",
                  left: config.use_profile ? "calc(100% - 20px)" : 2,
                  boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                }}
              />
            </button>
          </div>

          {/* Launch button */}
          <button
            onClick={handleLaunch}
            disabled={launching}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150"
            style={{
              background: launching ? "rgba(99,179,237,0.5)" : "rgba(99,179,237,0.15)",
              border: "1px solid rgba(99,179,237,0.3)",
              color: "rgba(99,179,237,0.95)",
              cursor: launching ? "not-allowed" : "pointer",
            }}
          >
            <ExternalLink size={14} />
            {launching
              ? "Launching…"
              : `Launch ${selectedBrowser?.name ?? "Browser"} for Plutus`}
          </button>

          {launchStatus === "ok" && (
            <div
              className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-medium"
              style={{
                background: "rgba(34,197,94,0.08)",
                border: "1px solid rgba(34,197,94,0.25)",
                color: "rgba(34,197,94,0.9)",
              }}
            >
              <CheckCircle size={13} />
              {launchMsg}
            </div>
          )}
          {launchStatus === "error" && (
            <div
              className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-medium"
              style={{
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.25)",
                color: "rgba(239,68,68,0.9)",
              }}
            >
              <AlertCircle size={13} />
              {launchMsg}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

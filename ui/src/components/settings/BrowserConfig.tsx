import React, { useEffect, useState, useCallback } from "react";
import { Globe, Chrome, RefreshCw, CheckCircle, AlertCircle, Zap, Shield } from "lucide-react";
import { api } from "../../lib/api";

interface BrowserInfo {
  kind: string;
  name: string;
  path: string;
  version: string;
  is_default: boolean;
}

interface BrowserConfigData {
  mode: string;           // "auto" | "user" | "headless"
  executable_path: string;
  cdp_port: number;
  use_profile: boolean;
}

const KIND_ICONS: Record<string, string> = {
  chrome:   "🌐",
  brave:    "🦁",
  edge:     "🔷",
  canary:   "🐤",
  chromium: "⚙️",
  vivaldi:  "🎵",
  opera:    "🔴",
  arc:      "🌈",
  custom:   "🔧",
};

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

  // Auto-scan once when the component mounts
  useEffect(() => {
    if (!scanned) {
      scanBrowsers();
    }
  }, [scanned, scanBrowsers]);

  const handleModeChange = (mode: string) => {
    onUpdate({ browser: { ...config, mode } });
  };

  const handleBrowserSelect = (path: string) => {
    onUpdate({ browser: { ...config, executable_path: path, mode: "user" } });
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
      setLaunchMsg(res.message || "Browser launched");
    } catch (e: any) {
      setLaunchStatus("error");
      setLaunchMsg(e?.message || "Failed to launch browser");
    } finally {
      setLaunching(false);
    }
  };

  const selectedBrowser = browsers.find((b) => b.path === config.executable_path);

  return (
    <div className="space-y-5">
      {/* Mode selector */}
      <div>
        <p className="text-sm font-medium mb-3" style={{ color: "rgb(var(--text-primary))" }}>
          Browser Mode
        </p>
        <div className="grid grid-cols-3 gap-2">
          {[
            {
              id: "auto",
              label: "Auto",
              icon: <Zap size={14} />,
              desc: "Connect to existing browser or launch Chromium",
            },
            {
              id: "user",
              label: "My Browser",
              icon: <Globe size={14} />,
              desc: "Use your real browser — inherits all logins & cookies",
            },
            {
              id: "headless",
              label: "Headless",
              icon: <Shield size={14} />,
              desc: "Invisible Chromium — fastest, no UI shown",
            },
          ].map((opt) => (
            <button
              key={opt.id}
              onClick={() => handleModeChange(opt.id)}
              className="p-3 rounded-lg border text-left transition-all"
              style={{
                background:
                  config.mode === opt.id
                    ? "rgb(var(--accent) / 0.15)"
                    : "rgb(var(--surface-alt))",
                borderColor:
                  config.mode === opt.id
                    ? "rgb(var(--accent) / 0.6)"
                    : "rgb(var(--border))",
                color: "rgb(var(--text-primary))",
              }}
            >
              <div className="flex items-center gap-1.5 mb-1 font-medium text-xs">
                <span style={{ color: config.mode === opt.id ? "rgb(var(--accent))" : "rgb(var(--text-secondary))" }}>
                  {opt.icon}
                </span>
                {opt.label}
              </div>
              <p className="text-xs leading-tight" style={{ color: "rgb(var(--text-secondary))" }}>
                {opt.desc}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Browser picker — only shown in "user" mode */}
      {config.mode === "user" && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium" style={{ color: "rgb(var(--text-primary))" }}>
              Select Browser
            </p>
            <button
              onClick={scanBrowsers}
              disabled={scanning}
              className="flex items-center gap-1.5 text-xs px-2 py-1 rounded transition-colors"
              style={{
                background: "rgb(var(--surface-alt))",
                color: "rgb(var(--text-secondary))",
                border: "1px solid rgb(var(--border))",
              }}
            >
              <RefreshCw size={11} className={scanning ? "animate-spin" : ""} />
              {scanning ? "Scanning…" : "Rescan"}
            </button>
          </div>

          {scanning && (
            <div className="text-xs py-3 text-center" style={{ color: "rgb(var(--text-secondary))" }}>
              Scanning for installed browsers…
            </div>
          )}

          {!scanning && browsers.length === 0 && scanned && (
            <div
              className="text-xs py-3 px-3 rounded-lg text-center"
              style={{
                background: "rgb(var(--surface-alt))",
                color: "rgb(var(--text-secondary))",
                border: "1px solid rgb(var(--border))",
              }}
            >
              No Chromium-based browsers found. Make sure Chrome, Brave, or Edge is installed.
            </div>
          )}

          {!scanning && browsers.length > 0 && (
            <div className="space-y-1.5">
              {browsers.map((b) => {
                const isSelected = config.executable_path === b.path;
                return (
                  <button
                    key={b.path}
                    onClick={() => handleBrowserSelect(b.path)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all"
                    style={{
                      background: isSelected
                        ? "rgb(var(--accent) / 0.12)"
                        : "rgb(var(--surface-alt))",
                      border: `1px solid ${isSelected ? "rgb(var(--accent) / 0.5)" : "rgb(var(--border))"}`,
                    }}
                  >
                    <span className="text-lg leading-none">{KIND_ICONS[b.kind] ?? "🌐"}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className="text-sm font-medium"
                          style={{ color: "rgb(var(--text-primary))" }}
                        >
                          {b.name}
                        </span>
                        {b.is_default && (
                          <span
                            className="text-xs px-1.5 py-0.5 rounded"
                            style={{
                              background: "rgb(var(--accent) / 0.15)",
                              color: "rgb(var(--accent))",
                            }}
                          >
                            Default
                          </span>
                        )}
                        {b.version && (
                          <span className="text-xs" style={{ color: "rgb(var(--text-secondary))" }}>
                            v{b.version}
                          </span>
                        )}
                      </div>
                      <p
                        className="text-xs truncate mt-0.5"
                        style={{ color: "rgb(var(--text-secondary))" }}
                      >
                        {b.path}
                      </p>
                    </div>
                    {isSelected && (
                      <CheckCircle size={16} style={{ color: "rgb(var(--accent))", flexShrink: 0 }} />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Use profile toggle */}
      {config.mode === "user" && config.executable_path && (
        <div
          className="flex items-center justify-between px-3 py-2.5 rounded-lg"
          style={{
            background: "rgb(var(--surface-alt))",
            border: "1px solid rgb(var(--border))",
          }}
        >
          <div>
            <p className="text-sm font-medium" style={{ color: "rgb(var(--text-primary))" }}>
              Use existing profile
            </p>
            <p className="text-xs mt-0.5" style={{ color: "rgb(var(--text-secondary))" }}>
              Inherit your logins, cookies, and saved passwords
            </p>
          </div>
          <button
            onClick={handleUseProfileToggle}
            className="toggle-switch"
            data-state={config.use_profile ? "on" : "off"}
            role="switch"
            aria-checked={config.use_profile}
          >
            <span className="toggle-thumb" />
          </button>
        </div>
      )}

      {/* Launch button */}
      {config.mode === "user" && config.executable_path && (
        <div>
          <button
            onClick={handleLaunch}
            disabled={launching}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: "rgb(var(--accent))",
              color: "#fff",
              opacity: launching ? 0.7 : 1,
            }}
          >
            <Globe size={14} />
            {launching
              ? "Launching…"
              : `Launch ${selectedBrowser?.name ?? "Browser"} for Plutus`}
          </button>
          <p className="text-xs mt-1.5" style={{ color: "rgb(var(--text-secondary))" }}>
            Opens the browser with remote debugging enabled so Plutus can control it.
            You can keep using the browser normally while Plutus works in the background.
          </p>

          {launchStatus === "ok" && (
            <div
              className="flex items-center gap-2 mt-2 px-3 py-2 rounded-lg text-xs"
              style={{
                background: "rgb(34 197 94 / 0.1)",
                border: "1px solid rgb(34 197 94 / 0.3)",
                color: "rgb(34 197 94)",
              }}
            >
              <CheckCircle size={13} />
              {launchMsg}
            </div>
          )}
          {launchStatus === "error" && (
            <div
              className="flex items-center gap-2 mt-2 px-3 py-2 rounded-lg text-xs"
              style={{
                background: "rgb(239 68 68 / 0.1)",
                border: "1px solid rgb(239 68 68 / 0.3)",
                color: "rgb(239 68 68)",
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

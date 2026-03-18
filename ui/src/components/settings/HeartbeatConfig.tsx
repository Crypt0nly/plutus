import { useState, useEffect } from "react";
import { Heart, Play, Square, Clock, Moon, Save, Info, Minus, Plus, ShieldOff } from "lucide-react";
import { api } from "../../lib/api";

// All pc() operations that can be blocked during heartbeat runs.
// Grouped for clarity in the UI.
const OP_GROUPS: { label: string; ops: { id: string; label: string }[] }[] = [
  {
    label: "App & Process Control",
    ops: [
      { id: "open_app",    label: "Open application" },
      { id: "close_app",   label: "Close application" },
      { id: "run_command", label: "Run shell command" },
      { id: "kill_process",label: "Kill process" },
      { id: "open_file",   label: "Open file" },
      { id: "open_folder", label: "Open folder" },
      { id: "open_url",    label: "Open URL in browser" },
    ],
  },
  {
    label: "Desktop Interaction",
    ops: [
      { id: "desktop_click",     label: "Click (by coordinates)" },
      { id: "desktop_click_ref", label: "Click (by element ref)" },
      { id: "desktop_type",      label: "Type text" },
      { id: "desktop_type_ref",  label: "Type text (by ref)" },
      { id: "desktop_key",       label: "Press key" },
      { id: "desktop_scroll",    label: "Scroll" },
      { id: "desktop_snapshot",  label: "Accessibility snapshot" },
    ],
  },
  {
    label: "Screen Capture & Mouse",
    ops: [
      { id: "screenshot",  label: "Take screenshot" },
      { id: "mouse_click", label: "Mouse click" },
      { id: "mouse_scroll",label: "Mouse scroll" },
    ],
  },
];

const ALL_OPS = OP_GROUPS.flatMap((g) => g.ops.map((o) => o.id));

interface HeartbeatStatus {
  enabled: boolean;
  running: boolean;
  paused: boolean;
  interval_seconds: number;
  consecutive_beats: number;
  max_consecutive: number;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  blocked_ops: string[];
}

interface Props {
  config: Record<string, any>;
  onSave: (patch: Record<string, any>) => void;
  saving: boolean;
}

export function HeartbeatConfig({ config, onSave, saving }: Props) {
  const [status, setStatus] = useState<HeartbeatStatus | null>(null);
  const [enabled, setEnabled] = useState(config.enabled ?? false);
  const [interval, setInterval_] = useState(config.interval_seconds ?? 300);
  const [maxConsecutive, setMaxConsecutive] = useState(config.max_consecutive ?? 50);
  const [quietStart, setQuietStart] = useState(config.quiet_hours_start ?? "");
  const [quietEnd, setQuietEnd] = useState(config.quiet_hours_end ?? "");
  const [prompt, setPrompt] = useState(config.prompt ?? "");
  const [blockedOps, setBlockedOps] = useState<string[]>(
    config.blocked_ops ?? ALL_OPS
  );
  const [expanded, setExpanded] = useState(false);

  const fetchStatus = () => {
    api.getHeartbeatStatus().then((s) => {
      const hs = s as HeartbeatStatus;
      setStatus(hs);
      // Keep local blocked_ops in sync with what the server reports
      if (Array.isArray(hs.blocked_ops)) {
        setBlockedOps(hs.blocked_ops);
      }
    }).catch(() => {});
  };

  useEffect(() => {
    fetchStatus();
    const timer = window.setInterval(fetchStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const handleToggle = async () => {
    try {
      if (status?.running) {
        const s = await api.stopHeartbeat();
        setStatus(s as HeartbeatStatus);
        setEnabled(false);
      } else {
        const s = await api.startHeartbeat();
        setStatus(s as HeartbeatStatus);
        setEnabled(true);
      }
    } catch (e) {
      console.error("Failed to toggle heartbeat:", e);
    }
  };

  const toggleOp = (opId: string) => {
    setBlockedOps((prev) =>
      prev.includes(opId) ? prev.filter((o) => o !== opId) : [...prev, opId]
    );
  };

  const handleSave = () => {
    const patch = {
      enabled,
      interval_seconds: interval,
      max_consecutive: maxConsecutive,
      quiet_hours_start: quietStart || null,
      quiet_hours_end: quietEnd || null,
      prompt: prompt || "",
      blocked_ops: blockedOps,
    };
    onSave({ heartbeat: patch });
    api.updateHeartbeat(patch)
      .then((s) => setStatus(s as HeartbeatStatus))
      .catch(() => {});
  };

  const formatInterval = (secs: number) => {
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  };

  const sliderFill = ((interval - 30) / (3600 - 30)) * 100;

  return (
    <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-300 ${
            status?.running && !status?.paused
              ? "bg-rose-500/15 shadow-sm shadow-rose-500/10"
              : "bg-rose-500/10"
          }`}>
            <Heart className={`w-5 h-5 text-rose-400 transition-transform duration-300 ${
              status?.running && !status?.paused ? "scale-110" : ""
            }`} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200 flex items-center gap-2">
              Heartbeat
              {status?.running && !status?.paused && (
                <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-normal bg-emerald-500/10 px-2 py-0.5 rounded-full">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Active
                </span>
              )}
              {status?.paused && (
                <span className="text-xs text-amber-400 font-normal bg-amber-500/10 px-2 py-0.5 rounded-full">Paused</span>
              )}
              {status && !status.running && !status.paused && (
                <span className="text-xs text-gray-500 font-normal bg-gray-500/10 px-2 py-0.5 rounded-full">Off</span>
              )}
            </h3>
            <p className="text-xs text-gray-500">Autonomous wake-up for continuous task execution</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-500 hover:text-gray-300 px-2.5 py-1.5 rounded-lg hover:bg-gray-800/50 transition-all duration-200"
          >
            {expanded ? "Collapse" : "Configure"}
          </button>
          <button
            onClick={handleToggle}
            className={`flex items-center gap-1.5 text-xs font-medium px-3.5 py-1.5 rounded-lg border transition-all duration-200 active:scale-[0.97] ${
              status?.running
                ? "border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20 shadow-sm shadow-red-500/5"
                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 shadow-sm shadow-emerald-500/5"
            }`}
          >
            {status?.running ? (
              <><Square className="w-3 h-3" /> Stop</>
            ) : (
              <><Play className="w-3 h-3" /> Start</>
            )}
          </button>
        </div>
      </div>

      {/* Status bar when running */}
      {status?.running && (
        <div className="mt-4 bg-gray-800/40 rounded-xl p-3.5 flex items-center gap-5 text-xs text-gray-400 animate-fade-in">
          <span>
            Beats: <span className="text-gray-200 font-medium">{status.consecutive_beats}</span>
            <span className="text-gray-600">/{status.max_consecutive}</span>
          </span>
          <span>
            Interval: <span className="text-gray-200 font-medium">{formatInterval(status.interval_seconds)}</span>
          </span>
          {status.quiet_hours_start && status.quiet_hours_end && (
            <span className="flex items-center gap-1">
              <Moon className="w-3 h-3" />
              Quiet: {status.quiet_hours_start} – {status.quiet_hours_end}
            </span>
          )}
          {/* Progress bar */}
          <div className="flex-1 h-1 bg-gray-700/50 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-rose-500/60 to-rose-400/60 rounded-full transition-all duration-500"
              style={{ width: `${(status.consecutive_beats / status.max_consecutive) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Expandable config */}
      {expanded && (
        <div className="mt-5 pt-5 border-t border-gray-800/40 space-y-5 animate-fade-in">
          {/* Info */}
          <div className="bg-gray-800/30 rounded-xl p-3.5 flex gap-2.5">
            <Info className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
            <p className="text-xs text-gray-500 leading-relaxed">
              The heartbeat periodically wakes Plutus so it can continue working on
              tasks autonomously. Each beat sends a check-in that lets the agent
              review its plan and pick up where it left off.
            </p>
          </div>

          {/* Interval — custom slider */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-xs text-gray-400 flex items-center gap-1.5">
                <Clock className="w-3 h-3" />
                Wake-up interval
              </label>
              <span className="text-xs font-mono text-plutus-400 bg-plutus-500/10 px-2.5 py-0.5 rounded-md min-w-[3rem] text-center">
                {formatInterval(interval)}
              </span>
            </div>
            <input
              type="range"
              min="30"
              max="3600"
              step="30"
              value={interval}
              onChange={(e) => setInterval_(parseInt(e.target.value))}
              className="plutus-slider w-full"
              style={{ "--slider-fill": `${sliderFill}%` } as React.CSSProperties}
            />
            <div className="flex justify-between text-[10px] text-gray-600 mt-2 px-0.5">
              <span>30s</span>
              <span>5m</span>
              <span>15m</span>
              <span>30m</span>
              <span>1h</span>
            </div>
          </div>

          {/* Max consecutive — number stepper */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">
              Max consecutive beats (safety limit)
            </label>
            <div className="number-input-group h-10">
              <button
                onClick={() => setMaxConsecutive(Math.max(1, maxConsecutive - 5))}
                className="px-2"
              >
                <Minus className="w-3.5 h-3.5" />
              </button>
              <input
                type="number"
                value={maxConsecutive}
                min={1}
                max={1000}
                onChange={(e) => setMaxConsecutive(parseInt(e.target.value) || 50)}
                className="text-sm text-gray-200 py-2 w-20"
              />
              <span className="text-xs text-gray-500 pr-1">beats</span>
              <button
                onClick={() => setMaxConsecutive(Math.min(1000, maxConsecutive + 5))}
                className="px-2"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-[10px] text-gray-600 mt-1.5">
              Auto-pauses after this many beats with no user interaction.
            </p>
          </div>

          {/* Quiet hours */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block flex items-center gap-1.5">
              <Moon className="w-3 h-3" />
              Quiet hours (optional)
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-gray-600 mb-1 block">Start</label>
                <input
                  type="time"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 transition-all duration-200"
                  value={quietStart}
                  onChange={(e) => setQuietStart(e.target.value)}
                  placeholder="23:00"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-600 mb-1 block">End</label>
                <input
                  type="time"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 transition-all duration-200"
                  value={quietEnd}
                  onChange={(e) => setQuietEnd(e.target.value)}
                  placeholder="07:00"
                />
              </div>
            </div>
          </div>

          {/* Blocked operations */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-gray-400 flex items-center gap-1.5">
                <ShieldOff className="w-3 h-3" />
                Blocked operations during heartbeat
              </label>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setBlockedOps(ALL_OPS)}
                  className="text-[10px] text-gray-500 hover:text-gray-300 px-2 py-0.5 rounded hover:bg-gray-800/50 transition-colors"
                >
                  Block all
                </button>
                <button
                  onClick={() => setBlockedOps([])}
                  className="text-[10px] text-gray-500 hover:text-gray-300 px-2 py-0.5 rounded hover:bg-gray-800/50 transition-colors"
                >
                  Allow all
                </button>
              </div>
            </div>
            <p className="text-[10px] text-gray-600 mb-3 leading-relaxed">
              Checked operations are <span className="text-amber-400/80">blocked</span> when the heartbeat runs unattended.
              Uncheck any operation to let the heartbeat use it freely.
            </p>
            <div className="space-y-3">
              {OP_GROUPS.map((group) => (
                <div key={group.label} className="bg-gray-800/30 rounded-xl p-3">
                  <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    {group.label}
                  </p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {group.ops.map((op) => {
                      const isBlocked = blockedOps.includes(op.id);
                      return (
                        <label
                          key={op.id}
                          className="flex items-center gap-2 cursor-pointer group"
                        >
                          <input
                            type="checkbox"
                            checked={isBlocked}
                            onChange={() => toggleOp(op.id)}
                            className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-amber-500 focus:ring-amber-500/30 focus:ring-1 cursor-pointer"
                          />
                          <span className={`text-[11px] transition-colors ${
                            isBlocked
                              ? "text-gray-400 group-hover:text-gray-300"
                              : "text-gray-600 group-hover:text-gray-500"
                          }`}>
                            {op.label}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Custom prompt */}
          <div>
            <label className="text-xs text-gray-400 mb-1.5 block">
              Custom heartbeat prompt (optional)
            </label>
            <textarea
              className="w-full bg-gray-800/50 border border-gray-700/50 rounded-xl px-3.5 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-2 focus:ring-plutus-500/20 min-h-[60px] resize-y transition-all duration-200"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Leave empty for default: review plan and continue working..."
              rows={2}
            />
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 disabled:opacity-50 text-white text-sm font-medium transition-all duration-200 shadow-sm shadow-plutus-600/20 active:scale-[0.98]"
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving..." : "Save Heartbeat Settings"}
          </button>
        </div>
      )}
    </div>
  );
}

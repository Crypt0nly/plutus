import { useState, useEffect } from "react";
import { Heart, Play, Square, Clock, Moon, Save, Info } from "lucide-react";
import { api } from "../../lib/api";

interface HeartbeatStatus {
  enabled: boolean;
  running: boolean;
  paused: boolean;
  interval_seconds: number;
  consecutive_beats: number;
  max_consecutive: number;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
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
  const [expanded, setExpanded] = useState(false);

  const fetchStatus = () => {
    api.getHeartbeatStatus().then((s) => setStatus(s as HeartbeatStatus)).catch(() => {});
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

  const handleSave = () => {
    onSave({
      heartbeat: {
        enabled,
        interval_seconds: interval,
        max_consecutive: maxConsecutive,
        quiet_hours_start: quietStart || null,
        quiet_hours_end: quietEnd || null,
        prompt: prompt || "",
      },
    });
    api.updateHeartbeat({
      enabled,
      interval_seconds: interval,
      max_consecutive: maxConsecutive,
      quiet_hours_start: quietStart || null,
      quiet_hours_end: quietEnd || null,
      prompt: prompt || "",
    }).then((s) => setStatus(s as HeartbeatStatus)).catch(() => {});
  };

  const formatInterval = (secs: number) => {
    if (secs < 60) return `${secs}s`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m`;
    return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
  };

  return (
    <div className="bg-surface rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-rose-500/10 flex items-center justify-center">
            <Heart className="w-5 h-5 text-rose-400" />
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
            className="text-xs text-gray-500 hover:text-gray-300 px-2 py-1 rounded transition-colors"
          >
            {expanded ? "Collapse" : "Configure"}
          </button>
          <button
            onClick={handleToggle}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              status?.running
                ? "border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20"
                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
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
        <div className="mt-4 bg-gray-800/40 rounded-lg p-3 flex items-center gap-5 text-xs text-gray-400">
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
        </div>
      )}

      {/* Expandable config */}
      {expanded && (
        <div className="mt-5 pt-5 border-t border-gray-800/40 space-y-5">
          {/* Info */}
          <div className="bg-gray-800/30 rounded-lg p-3 flex gap-2.5">
            <Info className="w-4 h-4 text-gray-500 shrink-0 mt-0.5" />
            <p className="text-xs text-gray-500 leading-relaxed">
              The heartbeat periodically wakes Plutus so it can continue working on
              tasks autonomously. Each beat sends a check-in that lets the agent
              review its plan and pick up where it left off.
            </p>
          </div>

          {/* Interval */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-gray-500 flex items-center gap-1.5">
                <Clock className="w-3 h-3" />
                Wake-up interval
              </label>
              <span className="text-xs font-mono text-plutus-400 bg-plutus-500/10 px-2 py-0.5 rounded-md">
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
              className="w-full accent-plutus-500 h-2 rounded-full"
            />
            <div className="flex justify-between text-[10px] text-gray-600 mt-1.5 px-0.5">
              <span>30s</span>
              <span>5m</span>
              <span>15m</span>
              <span>30m</span>
              <span>1h</span>
            </div>
          </div>

          {/* Max consecutive */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">
              Max consecutive beats (safety limit)
            </label>
            <input
              type="number"
              className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
              value={maxConsecutive}
              min={1}
              max={1000}
              onChange={(e) => setMaxConsecutive(parseInt(e.target.value) || 50)}
            />
            <p className="text-[10px] text-gray-600 mt-1">
              Auto-pauses after this many beats with no user interaction.
            </p>
          </div>

          {/* Quiet hours */}
          <div>
            <label className="text-xs text-gray-500 mb-2 block flex items-center gap-1.5">
              <Moon className="w-3 h-3" />
              Quiet hours (optional)
            </label>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-gray-600 mb-1 block">Start</label>
                <input
                  type="time"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                  value={quietStart}
                  onChange={(e) => setQuietStart(e.target.value)}
                  placeholder="23:00"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-600 mb-1 block">End</label>
                <input
                  type="time"
                  className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                  value={quietEnd}
                  onChange={(e) => setQuietEnd(e.target.value)}
                  placeholder="07:00"
                />
              </div>
            </div>
          </div>

          {/* Custom prompt */}
          <div>
            <label className="text-xs text-gray-500 mb-1.5 block">
              Custom heartbeat prompt (optional)
            </label>
            <textarea
              className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 min-h-[60px] resize-y"
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
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-plutus-600 hover:bg-plutus-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving..." : "Save Heartbeat Settings"}
          </button>
        </div>
      )}
    </div>
  );
}

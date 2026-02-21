import { useState, useEffect } from "react";
import { Heart, Play, Pause, Square, Clock, Moon, Save, Info } from "lucide-react";
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

  const handlePauseResume = async () => {
    try {
      const s = await api.updateHeartbeat({
        enabled: true,
      });
      // Use WS control for pause/resume — for now just refetch
      fetchStatus();
    } catch (e) {
      console.error("Failed to pause/resume:", e);
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
    // Also push to heartbeat endpoint so it live-updates
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
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Heart className="w-4 h-4 text-plutus-400" />
          Heartbeat
          {status?.running && !status?.paused && (
            <span className="flex items-center gap-1 text-xs text-emerald-400 font-normal">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-gentle-pulse" />
              Active
            </span>
          )}
          {status?.paused && (
            <span className="text-xs text-amber-400 font-normal">Paused</span>
          )}
          {status && !status.running && !status.paused && (
            <span className="text-xs text-gray-500 font-normal">Off</span>
          )}
        </h3>
        <button
          onClick={handleToggle}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border transition-colors ${
            status?.running
              ? "border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
          }`}
        >
          {status?.running ? (
            <>
              <Square className="w-3 h-3" /> Stop
            </>
          ) : (
            <>
              <Play className="w-3 h-3" /> Start
            </>
          )}
        </button>
      </div>

      {/* Status bar */}
      {status?.running && (
        <div className="bg-gray-800/50 rounded-lg p-3 mb-4 text-xs text-gray-400 flex items-center gap-4">
          <span>
            Beats: <span className="text-gray-200">{status.consecutive_beats}</span>
            /{status.max_consecutive}
          </span>
          <span>
            Interval: <span className="text-gray-200">{formatInterval(status.interval_seconds)}</span>
          </span>
          {status.quiet_hours_start && status.quiet_hours_end && (
            <span className="flex items-center gap-1">
              <Moon className="w-3 h-3" />
              Quiet: {status.quiet_hours_start} - {status.quiet_hours_end}
            </span>
          )}
        </div>
      )}

      {/* Explanation */}
      <div className="bg-gray-800/30 rounded-lg p-3 mb-4 flex gap-2">
        <Info className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-gray-500">
          The heartbeat periodically wakes Plutus so it can continue working on
          tasks autonomously. Each beat sends a check-in that lets the agent
          review its plan and pick up where it left off.
        </p>
      </div>

      <div className="space-y-4">
        {/* Interval */}
        <div>
          <label className="text-xs text-gray-500 mb-1.5 block flex items-center gap-1">
            <Clock className="w-3 h-3" />
            Wake-up interval ({formatInterval(interval)})
          </label>
          <input
            type="range"
            min="30"
            max="3600"
            step="30"
            value={interval}
            onChange={(e) => setInterval_(parseInt(e.target.value))}
            className="w-full accent-plutus-500"
          />
          <div className="flex justify-between text-[10px] text-gray-600 mt-1">
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
            className="input"
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
          <label className="text-xs text-gray-500 mb-1.5 block flex items-center gap-1">
            <Moon className="w-3 h-3" />
            Quiet hours (optional)
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-gray-600 mb-1 block">Start</label>
              <input
                type="time"
                className="input"
                value={quietStart}
                onChange={(e) => setQuietStart(e.target.value)}
                placeholder="23:00"
              />
            </div>
            <div>
              <label className="text-[10px] text-gray-600 mb-1 block">End</label>
              <input
                type="time"
                className="input"
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
            className="input min-h-[60px] resize-y"
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
          className="btn-primary flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving..." : "Save Heartbeat Settings"}
        </button>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  BarChart3,
  Zap,
  Brain,
  Calendar,
  Play,
  Pause,
  Trash2,
  ChevronDown,
  ChevronRight,
  Shield,
  History,
  Layers,
  Settings2,
  ListOrdered,
} from "lucide-react";
import { api } from "../../lib/api";

// ── Shared Components ──────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; bg: string; label: string; pulse?: boolean }> = {
    running:   { color: "text-blue-400",    bg: "bg-blue-500/10 border border-blue-500/20",    label: "Running",    pulse: true },
    completed: { color: "text-emerald-400", bg: "bg-emerald-500/10 border border-emerald-500/20", label: "Completed" },
    failed:    { color: "text-red-400",     bg: "bg-red-500/10 border border-red-500/20",     label: "Failed" },
    cancelled: { color: "text-gray-400",    bg: "bg-gray-500/10 border border-gray-500/20",    label: "Cancelled" },
    queued:    { color: "text-amber-400",   bg: "bg-amber-500/10 border border-amber-500/20",   label: "Queued" },
    timeout:   { color: "text-orange-400",  bg: "bg-orange-500/10 border border-orange-500/20",  label: "Timeout" },
    active:    { color: "text-blue-400",    bg: "bg-blue-500/10 border border-blue-500/20",    label: "Active",     pulse: true },
    paused:    { color: "text-amber-400",   bg: "bg-amber-500/10 border border-amber-500/20",   label: "Paused" },
    idle:      { color: "text-gray-400",    bg: "bg-gray-500/10 border border-gray-500/20",    label: "Idle" },
  };
  const c = config[status] || config.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-lg ${c.bg} ${c.color}`}>
      {c.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {c.label}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: React.ElementType; label: string; value: string | number; color: string;
}) {
  const cm: Record<string, string> = {
    blue:    "bg-blue-500/10 text-blue-400 border-blue-500/20",
    emerald: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    red:     "bg-red-500/10 text-red-400 border-red-500/20",
    purple:  "bg-purple-500/10 text-purple-400 border-purple-500/20",
    amber:   "bg-amber-500/10 text-amber-400 border-amber-500/20",
    cyan:    "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  };
  return (
    <div className="bg-surface-alt border border-gray-800/50 rounded-xl p-4 flex items-center gap-3.5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${cm[color]}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-100 leading-none">{value}</p>
        <p className="text-[11px] text-gray-500 mt-1">{label}</p>
      </div>
    </div>
  );
}

function SectionHeader({ icon: Icon, title, count, pulse, action }: {
  icon: React.ElementType; title: string; count?: number; pulse?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2.5">
        <div className="relative">
          <Icon className="w-4 h-4 text-gray-400" />
          {pulse && count && count > 0 && (
            <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-400 animate-ping" />
          )}
        </div>
        <h2 className="text-sm font-semibold text-gray-300">{title}</h2>
        {count !== undefined && (
          <span className="text-[10px] text-gray-500 bg-gray-800/60 px-2 py-0.5 rounded-full font-medium">{count}</span>
        )}
      </div>
      {action}
    </div>
  );
}

function EmptyState({ icon: Icon, text, sub }: { icon: React.ElementType; text: string; sub?: string }) {
  return (
    <div className="bg-surface-alt border border-gray-800/40 border-dashed rounded-xl text-center py-12">
      <Icon className="w-8 h-8 text-gray-700 mx-auto mb-3" />
      <p className="text-sm text-gray-500">{text}</p>
      {sub && <p className="text-xs text-gray-600 mt-2 max-w-sm mx-auto leading-relaxed">{sub}</p>}
    </div>
  );
}

function LoadingSpinner({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="flex items-center gap-3 text-gray-400">
        <RefreshCw className="w-5 h-5 animate-spin" />
        <span className="text-sm">{text}</span>
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (!seconds || seconds < 0.001) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function formatTime(ts: string | number | null): string {
  if (!ts) return "—";
  const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDate(ts: string | number | null): string {
  if (!ts) return "—";
  const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) return `Today ${formatTime(ts)}`;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${formatTime(ts)}`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + formatTime(ts);
}

function modelDisplayName(key: string | null | undefined): string {
  if (!key) return "Auto";
  const names: Record<string, string> = {
    "claude-opus": "Opus",
    "claude-sonnet": "Sonnet",
    "claude-haiku": "Haiku",
    "gpt-5.2": "GPT-5.2",
  };
  return names[key] || key;
}

function modelColor(key: string | null | undefined): string {
  if (!key) return "text-gray-400";
  if (key.includes("opus")) return "text-purple-400";
  if (key.includes("sonnet")) return "text-blue-400";
  if (key.includes("haiku")) return "text-emerald-400";
  if (key.includes("gpt")) return "text-cyan-400";
  return "text-gray-400";
}

// Tab button — fixed width to prevent layout shifts
function Tab({ active, onClick, icon: Icon, label, badge }: {
  active: boolean; onClick: () => void; icon: React.ElementType; label: string; badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-medium rounded-xl transition-all duration-200 min-w-[160px] ${
        active
          ? "bg-blue-500/15 text-blue-400 border border-blue-500/30 shadow-lg shadow-blue-500/5"
          : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/40 border border-transparent"
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full min-w-[18px] text-center font-bold">
          {badge}
        </span>
      )}
    </button>
  );
}

// ── Workers Tab ────────────────────────────────────────────

function WorkersTab() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [modelData, setModelData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [maxWorkers, setMaxWorkers] = useState(5);
  const [maxToolRounds, setMaxToolRounds] = useState(15);
  const [showSettings, setShowSettings] = useState(false);

  const fetch_ = useCallback(async () => {
    try {
      const [w, m] = await Promise.all([
        api.getWorkers(),
        api.getModelRouting().catch(() => null),
      ]);
      setData(w);
      setModelData(m);
      if (w?.stats?.max_workers) setMaxWorkers(w.stats.max_workers);
      if (w?.stats?.max_tool_rounds) setMaxToolRounds(w.stats.max_tool_rounds);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);
  useEffect(() => {
    if (!autoRefresh) return;
    const iv = setInterval(fetch_, 3000);
    return () => clearInterval(iv);
  }, [autoRefresh, fetch_]);

  const handleCancel = async (id: string) => {
    try { await api.cancelWorker(id); fetch_(); } catch { /* ignore */ }
  };

  const handleMaxWorkersChange = async (val: number) => {
    setMaxWorkers(val);
    try {
      await api.updateWorkerConfig({ max_concurrent_workers: val });
      fetch_();
    } catch { /* ignore */ }
  };

  const handleMaxToolRoundsChange = async (val: number) => {
    setMaxToolRounds(val);
    try {
      await api.updateWorkerConfig({ max_tool_rounds: val });
      fetch_();
    } catch { /* ignore */ }
  };

  const toggleCostConscious = async () => {
    const current = modelData?.routing?.cost_conscious ?? false;
    try {
      await api.updateModelRouting({ cost_conscious: !current });
      fetch_();
    } catch { /* ignore */ }
  };

  if (loading) return <LoadingSpinner text="Loading workers..." />;

  const stats = data?.stats || {};
  const running = Array.isArray(data?.running) ? data.running : [];
  const queued = Array.isArray(data?.queued) ? data.queued : [];
  const completed = Array.isArray(data?.completed) ? data.completed : [];
  const routing = modelData?.routing || {};
  const activeCount = stats.active_count || running.length;
  const queuedCount = stats.queued_count || queued.length;
  const currentMax = stats.max_workers || maxWorkers;
  const usagePercent = currentMax > 0 ? Math.min((activeCount / currentMax) * 100, 100) : 0;

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={Zap} label="Active Workers" value={activeCount} color="blue" />
        <StatCard icon={Clock} label="In Queue" value={queuedCount} color="amber" />
        <StatCard icon={CheckCircle2} label="Completed" value={stats.total_completed || 0} color="emerald" />
        <StatCard icon={XCircle} label="Failed" value={stats.total_failed || 0} color="red" />
      </div>

      {/* Capacity Bar */}
      <div className="bg-surface-alt border border-gray-800/50 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-gray-300 flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-400" />
            Worker Capacity
          </span>
          <div className="flex items-center gap-3">
            <span className="text-sm font-mono text-gray-400">
              {activeCount} <span className="text-gray-600">/</span> {currentMax}
              {queuedCount > 0 && (
                <span className="text-amber-400 ml-2">+{queuedCount} queued</span>
              )}
            </span>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`p-1.5 rounded-lg transition-colors ${
                showSettings ? "bg-blue-500/15 text-blue-400" : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"
              }`}
              title="Worker settings"
            >
              <Settings2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className="w-full bg-gray-800/80 rounded-full h-3 overflow-hidden">
          <div
            className={`rounded-full h-3 transition-all duration-700 ease-out ${
              usagePercent > 80
                ? "bg-gradient-to-r from-red-500 to-orange-500"
                : usagePercent > 50
                ? "bg-gradient-to-r from-amber-500 to-yellow-500"
                : "bg-gradient-to-r from-blue-500 to-cyan-500"
            }`}
            style={{ width: `${Math.max(usagePercent, usagePercent > 0 ? 4 : 0)}%` }}
          />
        </div>

        {/* Settings Panel (collapsible) */}
        {showSettings && (
          <div className="mt-5 pt-5 border-t border-gray-800/60 space-y-5">
            {/* Max Workers Slider */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm text-gray-300">Maximum Concurrent Workers</label>
                <span className="text-sm font-mono font-bold text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-lg">
                  {maxWorkers}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={20}
                value={maxWorkers}
                onChange={(e) => handleMaxWorkersChange(Number(e.target.value))}
                className="w-full h-2 bg-gray-800 rounded-full appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
                  [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500
                  [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-blue-500/30
                  [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:transition-all
                  [&::-webkit-slider-thumb]:hover:bg-blue-400 [&::-webkit-slider-thumb]:hover:scale-110"
              />
              <div className="flex justify-between text-[10px] text-gray-600 mt-1.5 px-0.5">
                <span>1</span>
                <span>5</span>
                <span>10</span>
                <span>15</span>
                <span>20</span>
              </div>
              <p className="text-[11px] text-gray-600 mt-2">
                Controls the maximum number of workers that can run simultaneously. Tasks beyond this limit are automatically queued.
              </p>
            </div>

            {/* Max Tool Rounds Slider */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm text-gray-300">Max Tool Rounds per Worker</label>
                <span className="text-sm font-mono font-bold text-purple-400 bg-purple-500/10 px-2.5 py-1 rounded-lg">
                  {maxToolRounds}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={50}
                value={maxToolRounds}
                onChange={(e) => handleMaxToolRoundsChange(Number(e.target.value))}
                className="w-full h-2 bg-gray-800 rounded-full appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
                  [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-purple-500
                  [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-purple-500/30
                  [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:transition-all
                  [&::-webkit-slider-thumb]:hover:bg-purple-400 [&::-webkit-slider-thumb]:hover:scale-110"
              />
              <div className="flex justify-between text-[10px] text-gray-600 mt-1.5 px-0.5">
                <span>1</span>
                <span>10</span>
                <span>25</span>
                <span>40</span>
                <span>50</span>
              </div>
              <p className="text-[11px] text-gray-600 mt-2">
                Maximum number of LLM tool-call rounds each worker can perform. Higher values let workers handle more complex tasks but use more tokens.
              </p>
            </div>

            {/* Cost-Conscious Toggle */}
            <div className="flex items-center justify-between bg-surface-deep rounded-xl p-4 border border-gray-800/40">
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  routing.cost_conscious
                    ? "bg-emerald-500/10 border border-emerald-500/20"
                    : "bg-gray-800/50 border border-gray-700/30"
                }`}>
                  <Shield className={`w-4 h-4 ${routing.cost_conscious ? "text-emerald-400" : "text-gray-500"}`} />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-200">Cost-Conscious Mode</p>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    {routing.cost_conscious
                      ? "Workers prefer cheaper, faster models to save costs"
                      : "Workers use the best model for each task regardless of cost"
                    }
                  </p>
                </div>
              </div>
              <button
                onClick={toggleCostConscious}
                className={`relative inline-flex items-center h-6 w-11 rounded-full transition-colors duration-300 shrink-0 ml-4 ${
                  routing.cost_conscious ? "bg-emerald-500" : "bg-gray-700"
                }`}
              >
                <span className={`inline-block w-4 h-4 rounded-full bg-white shadow-md transition-transform duration-300 ${
                  routing.cost_conscious ? "translate-x-6" : "translate-x-1"
                }`} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Active Tasks Box */}
      <div>
        <SectionHeader icon={Activity} title="Active Tasks" count={activeCount} pulse={activeCount > 0} />
        {running.length === 0 ? (
          <div className="bg-surface-alt border border-gray-800/40 border-dashed rounded-xl py-8 text-center">
            <Activity className="w-6 h-6 text-gray-700 mx-auto mb-2" />
            <p className="text-sm text-gray-500">No active tasks</p>
            <p className="text-[11px] text-gray-600 mt-1">Workers will appear here when Plutus assigns tasks</p>
          </div>
        ) : (
          <div className="space-y-2">
            {running.map((w: any) => (
              <ActiveTaskCard key={w.task_id || w.id} worker={w} onCancel={handleCancel} />
            ))}
          </div>
        )}
      </div>

      {/* Job Queue */}
      {queued.length > 0 && (
        <div>
          <SectionHeader icon={ListOrdered} title="Job Queue" count={queuedCount} />
          <div className="bg-surface-alt border border-amber-500/10 rounded-xl overflow-hidden divide-y divide-gray-800/40">
            {queued.map((w: any, i: number) => (
              <div key={w.task_id || w.id || i} className="flex items-center gap-3 py-3 px-4">
                <span className="text-[11px] font-mono text-gray-600 w-6 text-center">{i + 1}</span>
                <Clock className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-300 truncate">{w.name || w.task || w.prompt || w.task_id}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {w.model_key && (
                      <span className={`text-[10px] font-medium ${modelColor(w.model_key)}`}>
                        {modelDisplayName(w.model_key)}
                      </span>
                    )}
                    {w.created_at && (
                      <span className="text-[10px] text-gray-600">Queued {formatDate(w.created_at)}</span>
                    )}
                  </div>
                </div>
                <StatusBadge status="queued" />
                <button
                  onClick={() => handleCancel(w.task_id || w.id)}
                  className="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
                  title="Remove from queue"
                >
                  <XCircle className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Task History */}
      <div>
        <SectionHeader icon={History} title="Task History" count={completed.length} />
        {completed.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            text="No completed tasks yet"
            sub="Completed worker tasks will appear here with their results, model used, and duration"
          />
        ) : (
          <div className="bg-surface-alt border border-gray-800/50 rounded-xl overflow-hidden divide-y divide-gray-800/40">
            {completed.slice(0, 25).map((w: any, i: number) => (
              <HistoryRow key={w.task_id || i} task={w} />
            ))}
          </div>
        )}
      </div>

      {/* Auto-refresh toggle */}
      <div className="flex justify-center pt-2 pb-4">
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className={`text-xs px-4 py-2 rounded-xl flex items-center gap-2 transition-all duration-200 ${
            autoRefresh
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              : "bg-gray-800/50 text-gray-500 border border-gray-700/50 hover:text-gray-400"
          }`}
        >
          <Activity className={`w-3.5 h-3.5 ${autoRefresh ? "animate-pulse" : ""}`} />
          {autoRefresh ? "Live Updates On" : "Live Updates Paused"}
        </button>
      </div>
    </div>
  );
}

function ActiveTaskCard({ worker, onCancel }: { worker: any; onCancel: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const id = worker.task_id || worker.id;
  const progress = worker.progress_pct || 0;

  return (
    <div className="bg-surface-alt border border-blue-500/20 rounded-xl p-4 shadow-lg shadow-blue-500/5">
      <div className="flex items-center gap-3">
        {/* Pulsing indicator */}
        <div className="relative shrink-0">
          <div className="w-3 h-3 rounded-full bg-blue-400 animate-pulse" />
          <div className="absolute inset-0 w-3 h-3 rounded-full bg-blue-400 animate-ping opacity-20" />
        </div>

        {/* Task info */}
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">
              {worker.name || worker.task || worker.prompt || id?.slice(0, 20)}
            </span>
            <StatusBadge status="running" />
          </div>
          <div className="flex items-center gap-3 mt-1.5 text-[11px] text-gray-500">
            {worker.model_used && (
              <span className={`flex items-center gap-1 font-medium ${modelColor(worker.model_used)}`}>
                <Brain className="w-3 h-3" />
                {modelDisplayName(worker.model_used)}
              </span>
            )}
            {worker.current_step && (
              <span className="text-gray-400 truncate max-w-[200px]">{worker.current_step}</span>
            )}
            {worker.started_at && <span>Started {formatDate(worker.started_at)}</span>}
            {worker.steps_completed > 0 && <span>{worker.steps_completed} steps</span>}
          </div>
        </div>

        {/* Cancel button */}
        <button
          onClick={() => onCancel(id)}
          className="p-2 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
          title="Cancel worker"
        >
          <XCircle className="w-4 h-4" />
        </button>
      </div>

      {/* Progress bar */}
      {progress > 0 && (
        <div className="mt-3">
          <div className="w-full bg-gray-800/80 rounded-full h-1.5 overflow-hidden">
            <div
              className="rounded-full h-1.5 bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-gray-600">{worker.current_step || "Processing..."}</span>
            <span className="text-[10px] text-blue-400 font-mono">{progress.toFixed(0)}%</span>
          </div>
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-800/60 text-xs text-gray-400 space-y-1.5">
          <p><span className="text-gray-600">Task ID:</span> {id}</p>
          {worker.prompt && <p><span className="text-gray-600">Prompt:</span> {worker.prompt}</p>}
          {worker.model_key && <p><span className="text-gray-600">Assigned Model:</span> {worker.model_key}</p>}
          {worker.started_at && <p><span className="text-gray-600">Started:</span> {formatDate(worker.started_at)}</p>}
        </div>
      )}
    </div>
  );
}

function HistoryRow({ task }: { task: any }) {
  const [expanded, setExpanded] = useState(false);
  const state = task.state || task.status || "completed";

  return (
    <div className={`transition-colors ${expanded ? "bg-gray-800/20" : "hover:bg-gray-800/10"}`}>
      <div
        className="flex items-center gap-3 py-3 px-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown className="w-3.5 h-3.5 text-gray-600 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-600 shrink-0" />}
        <StatusBadge status={state} />
        <div className="flex-1 min-w-0">
          <span className="text-sm text-gray-300 truncate block">
            {task.name || task.task || task.prompt || task.task_id?.slice(0, 20)}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[11px] text-gray-600 shrink-0">
          {task.model_used && (
            <span className={`flex items-center gap-1 font-medium ${modelColor(task.model_used)}`}>
              <Brain className="w-3 h-3" />
              {modelDisplayName(task.model_used)}
            </span>
          )}
          <span className="font-mono">{formatDuration(task.duration || 0)}</span>
          <span>{formatDate(task.completed_at || task.started_at)}</span>
        </div>
      </div>
      {expanded && (
        <div className="px-4 pb-3 space-y-2">
          {task.result && (
            <div className="bg-gray-900/50 rounded-lg p-3">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Result</p>
              <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto leading-relaxed">
                {typeof task.result === "string" ? task.result : JSON.stringify(task.result, null, 2)}
              </pre>
            </div>
          )}
          {task.error && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-3">
              <p className="text-xs text-red-400 font-mono whitespace-pre-wrap">{task.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Scheduler Tab ──────────────────────────────────────────

function SchedulerTab() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(false);

  const fetch_ = useCallback(async () => {
    try {
      const [sched, hist] = await Promise.all([
        api.getScheduler(),
        api.getSchedulerHistory(20),
      ]);
      setData(sched);
      setHistory(hist?.executions || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);
  useEffect(() => {
    const iv = setInterval(fetch_, 5000);
    return () => clearInterval(iv);
  }, [fetch_]);

  const handlePause = async (id: string) => {
    try { await api.pauseJob(id); fetch_(); } catch { /* ignore */ }
  };
  const handleResume = async (id: string) => {
    try { await api.resumeJob(id); fetch_(); } catch { /* ignore */ }
  };
  const handleDelete = async (id: string) => {
    if (!confirm("Delete this scheduled job?")) return;
    try { await api.deleteJob(id); fetch_(); } catch { /* ignore */ }
  };

  if (loading) return <LoadingSpinner text="Loading scheduler..." />;

  const jobs = data?.jobs || [];
  const stats = data?.stats || {};
  const activeJobs = jobs.filter((j: any) => j.status === "active");
  const pausedJobs = jobs.filter((j: any) => j.status === "paused");

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={Calendar} label="Total Jobs" value={stats.total_jobs || jobs.length} color="purple" />
        <StatCard icon={Play} label="Active" value={stats.active_jobs || activeJobs.length} color="emerald" />
        <StatCard icon={Pause} label="Paused" value={stats.paused_jobs || pausedJobs.length} color="amber" />
        <StatCard icon={History} label="Executions" value={stats.total_executions || history.length} color="cyan" />
      </div>

      {/* Jobs List */}
      <div>
        <SectionHeader icon={Calendar} title="Scheduled Jobs" count={jobs.length} />
        {jobs.length === 0 ? (
          <EmptyState
            icon={Calendar}
            text="No scheduled jobs"
            sub='Tell Plutus something like "Every day at 6 AM, write a blog post" and it will create a scheduled job'
          />
        ) : (
          <div className="space-y-2">
            {jobs.map((job: any) => (
              <JobCard
                key={job.id || job.job_id}
                job={job}
                onPause={handlePause}
                onResume={handleResume}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      {/* Execution History */}
      <div>
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-300 mb-3 transition-colors"
        >
          {showHistory ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          <History className="w-4 h-4" />
          Execution History
          <span className="text-[10px] text-gray-500 bg-gray-800/50 px-2 py-0.5 rounded-full">{history.length}</span>
        </button>
        {showHistory && (
          history.length === 0 ? (
            <EmptyState icon={History} text="No executions yet" sub="History will appear after scheduled jobs run" />
          ) : (
            <div className="bg-surface-alt border border-gray-800/50 rounded-xl overflow-hidden divide-y divide-gray-800/40">
              {history.map((ex: any, i: number) => (
                <div key={i} className="flex items-center gap-3 py-3 px-4 hover:bg-gray-800/10 transition-colors">
                  <StatusBadge status={ex.status || "completed"} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-300 truncate">{ex.job_name || ex.job_id}</p>
                  </div>
                  <div className="text-[11px] text-gray-600 flex items-center gap-4">
                    <span className="font-mono">{formatDuration(ex.duration || 0)}</span>
                    <span>{formatDate(ex.executed_at || ex.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
}

function JobCard({ job, onPause, onResume, onDelete }: {
  job: any; onPause: (id: string) => void; onResume: (id: string) => void; onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const id = job.id || job.job_id;
  const isPaused = job.status === "paused";
  const isActive = job.status === "active";

  return (
    <div className={`bg-surface-alt border rounded-xl p-4 transition-colors ${
      isActive ? "border-emerald-500/20" : isPaused ? "border-amber-500/20 opacity-75" : "border-gray-800/50"
    }`}>
      <div className="flex items-center gap-3">
        <Calendar className={`w-4 h-4 shrink-0 ${isActive ? "text-emerald-400" : "text-gray-500"}`} />
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">
              {job.name || job.task || id}
            </span>
            <StatusBadge status={job.status} />
          </div>
          <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-500">
            {job.schedule && <span className="font-mono bg-gray-800/50 px-1.5 py-0.5 rounded">{job.schedule}</span>}
            {job.cron && <span className="font-mono bg-gray-800/50 px-1.5 py-0.5 rounded">{job.cron}</span>}
            {job.interval && <span>Every {formatDuration(job.interval)}</span>}
            {job.next_run && <span>Next: {formatDate(job.next_run)}</span>}
            {job.last_run && <span>Last: {formatDate(job.last_run)}</span>}
            {job.run_count !== undefined && <span>Runs: {job.run_count}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {isActive ? (
            <button
              onClick={() => onPause(id)}
              className="p-2 rounded-lg text-amber-400 hover:bg-amber-500/10 transition-colors"
              title="Pause"
            >
              <Pause className="w-4 h-4" />
            </button>
          ) : isPaused ? (
            <button
              onClick={() => onResume(id)}
              className="p-2 rounded-lg text-emerald-400 hover:bg-emerald-500/10 transition-colors"
              title="Resume"
            >
              <Play className="w-4 h-4" />
            </button>
          ) : null}
          <button
            onClick={() => onDelete(id)}
            className="p-2 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-800/60 text-xs text-gray-400 space-y-1.5">
          {job.task && <p><span className="text-gray-600">Task:</span> {job.task}</p>}
          {job.description && <p><span className="text-gray-600">Description:</span> {job.description}</p>}
          {job.model && <p><span className="text-gray-600">Model:</span> {job.model}</p>}
          {job.created_at && <p><span className="text-gray-600">Created:</span> {formatDate(job.created_at)}</p>}
        </div>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────

export function WorkersView() {
  const [tab, setTab] = useState<"workers" | "scheduler">("workers");
  const [workerCount, setWorkerCount] = useState(0);
  const [jobCount, setJobCount] = useState(0);

  useEffect(() => {
    const fetchCounts = async () => {
      try {
        const [w, s] = await Promise.all([
          api.getWorkers().catch(() => null),
          api.getScheduler().catch(() => null),
        ]);
        setWorkerCount(w?.stats?.active_count || 0);
        setJobCount(s?.stats?.active_jobs || s?.jobs?.length || 0);
      } catch { /* ignore */ }
    };
    fetchCounts();
    const iv = setInterval(fetchCounts, 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-1">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-100">Workers & Automation</h1>
          <p className="text-sm text-gray-500 mt-1">
            Monitor active workers, job queue, scheduled tasks, and task history.
          </p>
        </div>

        {/* Tabs — fixed layout */}
        <div className="flex items-center gap-2 mb-6">
          <Tab active={tab === "workers"} onClick={() => setTab("workers")} icon={Cpu} label="Workers" badge={workerCount} />
          <Tab active={tab === "scheduler"} onClick={() => setTab("scheduler")} icon={Calendar} label="Scheduler" badge={jobCount} />
        </div>

        {/* Tab Content — min height prevents layout jump */}
        <div className="min-h-[500px]">
          {tab === "workers" && <WorkersTab />}
          {tab === "scheduler" && <SchedulerTab />}
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  RefreshCw,
  StopCircle,
  BarChart3,
  Zap,
  Timer,
  Hash,
  ArrowUpDown,
} from "lucide-react";
import { api } from "../../lib/api";

// Status badge component
function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ElementType; color: string; bg: string; label: string }> = {
    completed: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10", label: "Completed" },
    failed: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", label: "Failed" },
    running: { icon: Activity, color: "text-blue-400", bg: "bg-blue-500/10", label: "Running" },
    timeout: { icon: Clock, color: "text-amber-400", bg: "bg-amber-500/10", label: "Timed Out" },
    cancelled: { icon: StopCircle, color: "text-gray-400", bg: "bg-gray-500/10", label: "Cancelled" },
    idle: { icon: Clock, color: "text-gray-400", bg: "bg-gray-500/10", label: "Idle" },
  };

  const c = config[status] || config.idle;
  const Icon = c.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${c.bg} ${c.color}`}>
      <Icon className="w-3 h-3" />
      {c.label}
    </span>
  );
}

// Stat card
function StatCard({
  icon: Icon,
  label,
  value,
  color,
  subtext,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
  subtext?: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-400",
    emerald: "bg-emerald-500/10 text-emerald-400",
    red: "bg-red-500/10 text-red-400",
    purple: "bg-purple-500/10 text-purple-400",
    amber: "bg-amber-500/10 text-amber-400",
  };

  return (
    <div className="card flex items-center gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colorMap[color]}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-lg font-bold text-gray-200">{value}</p>
        <p className="text-xs text-gray-500">{label}</p>
        {subtext && <p className="text-[10px] text-gray-600">{subtext}</p>}
      </div>
    </div>
  );
}

// Duration formatter
function formatDuration(seconds: number): string {
  if (seconds < 0.001) return "< 1ms";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

// Active worker row with pulse animation
function ActiveWorkerRow({
  worker,
  onCancel,
}: {
  worker: Record<string, any>;
  onCancel: (id: string) => void;
}) {
  return (
    <div className="flex items-center gap-4 py-3 px-4 bg-blue-500/5 border border-blue-500/20 rounded-lg animate-fade-in">
      <div className="relative">
        <div className="w-3 h-3 rounded-full bg-blue-400 animate-pulse" />
        <div className="absolute inset-0 w-3 h-3 rounded-full bg-blue-400 animate-ping opacity-30" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">
            Worker {worker.id?.slice(0, 8)}
          </span>
          <StatusBadge status="running" />
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Hash className="w-3 h-3" />
            PID: {worker.pid || "—"}
          </span>
          <span className="flex items-center gap-1">
            <Timer className="w-3 h-3" />
            {formatDuration(worker.elapsed || 0)}
          </span>
        </div>
      </div>
      <button
        onClick={() => onCancel(worker.id)}
        className="btn-danger text-xs py-1.5 px-3 flex items-center gap-1.5"
      >
        <StopCircle className="w-3.5 h-3.5" />
        Stop
      </button>
    </div>
  );
}

// Recent task row
function TaskRow({ task }: { task: Record<string, any> }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`border-b border-gray-800 last:border-b-0 cursor-pointer hover:bg-gray-800/30 transition-colors ${
        expanded ? "bg-gray-800/20" : ""
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-4 py-3 px-4">
        <StatusBadge status={task.status} />
        <div className="flex-1 min-w-0">
          <span className="text-sm text-gray-300 font-mono">
            {task.task_id?.slice(0, 12) || "—"}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          {task.pid && (
            <span className="flex items-center gap-1">
              <Hash className="w-3 h-3" />
              {task.pid}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Timer className="w-3 h-3" />
            {formatDuration(task.duration || 0)}
          </span>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-3 animate-fade-in">
          {task.error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-2">
              <p className="text-xs text-red-400 font-mono whitespace-pre-wrap">
                {task.error}
              </p>
            </div>
          )}
          {task.output && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
                Output
              </p>
              <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap max-h-40 overflow-y-auto">
                {typeof task.output === "string"
                  ? task.output
                  : JSON.stringify(task.output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function WorkersView() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"recent" | "duration">("recent");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const result = await api.getWorkers();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load workers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 2 seconds when enabled
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  const handleCancel = async (taskId: string) => {
    try {
      await api.cancelWorker(taskId);
      fetchData();
    } catch (e) {
      console.error("Failed to cancel worker:", e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-gray-400">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>Loading workers...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card text-center py-8">
        <p className="text-red-400 mb-2">Failed to load workers</p>
        <p className="text-xs text-gray-500">{error}</p>
        <button onClick={fetchData} className="btn-primary mt-4 text-sm">
          Retry
        </button>
      </div>
    );
  }

  const stats = data?.stats || {};
  const active = data?.active || [];
  const recent = data?.recent || [];

  // Sort recent tasks
  const sortedRecent = [...recent].sort((a, b) => {
    if (sortBy === "duration") return (b.duration || 0) - (a.duration || 0);
    return 0; // already sorted by recency from API
  });

  return (
    <div className="h-full overflow-y-auto space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Workers</h1>
          <p className="text-sm text-gray-400 mt-1">
            Monitor subprocess activity in real-time. Workers are isolated processes
            that handle tasks like editing files, analyzing code, and running commands.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-colors ${
              autoRefresh
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                : "bg-gray-800 text-gray-400 border border-gray-700"
            }`}
          >
            <Activity className={`w-3 h-3 ${autoRefresh ? "animate-pulse" : ""}`} />
            {autoRefresh ? "Live" : "Paused"}
          </button>
          <button
            onClick={fetchData}
            className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <StatCard
          icon={Zap}
          label="Active Now"
          value={stats.active_count || 0}
          color="blue"
        />
        <StatCard
          icon={BarChart3}
          label="Total Tasks"
          value={stats.total_tasks || 0}
          color="purple"
        />
        <StatCard
          icon={CheckCircle2}
          label="Completed"
          value={stats.completed || 0}
          color="emerald"
        />
        <StatCard
          icon={XCircle}
          label="Failed"
          value={stats.failed || 0}
          color="red"
        />
        <StatCard
          icon={Timer}
          label="Avg Duration"
          value={formatDuration(stats.avg_duration || 0)}
          color="amber"
          subtext={`Max ${stats.max_workers || 5} workers`}
        />
      </div>

      {/* Active Workers */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <div className="relative">
            <Activity className="w-4 h-4 text-blue-400" />
            {active.length > 0 && (
              <div className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-blue-400 animate-ping" />
            )}
          </div>
          <h2 className="text-sm font-semibold text-gray-300">
            Active Workers
          </h2>
          <span className="text-xs text-gray-500">
            {active.length} running
          </span>
        </div>

        {active.length === 0 ? (
          <div className="card text-center py-8">
            <Cpu className="w-8 h-8 text-gray-700 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No workers running</p>
            <p className="text-xs text-gray-600 mt-1">
              Workers will appear here when the AI is processing tasks
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {active.map((worker: any) => (
              <ActiveWorkerRow
                key={worker.id}
                worker={worker}
                onCancel={handleCancel}
              />
            ))}
          </div>
        )}
      </div>

      {/* Recent Tasks */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-300">
              Recent Tasks
            </h2>
            <span className="text-xs text-gray-500">
              {recent.length} tasks
            </span>
          </div>
          <button
            onClick={() => setSortBy(sortBy === "recent" ? "duration" : "recent")}
            className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
          >
            <ArrowUpDown className="w-3 h-3" />
            Sort by {sortBy === "recent" ? "duration" : "recent"}
          </button>
        </div>

        {sortedRecent.length === 0 ? (
          <div className="card text-center py-8">
            <BarChart3 className="w-8 h-8 text-gray-700 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No tasks yet</p>
            <p className="text-xs text-gray-600 mt-1">
              Start a conversation and ask the AI to do something — tasks will appear here
            </p>
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            {sortedRecent.map((task: any, i: number) => (
              <TaskRow key={task.task_id || i} task={task} />
            ))}
          </div>
        )}
      </div>

      {/* Capacity bar */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-400">Worker Capacity</span>
          <span className="text-xs text-gray-500">
            {active.length} / {stats.max_workers || 5} slots used
          </span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2.5">
          <div
            className="bg-gradient-to-r from-blue-500 to-purple-500 rounded-full h-2.5 transition-all duration-500"
            style={{
              width: `${Math.min(
                ((active.length || 0) / (stats.max_workers || 5)) * 100,
                100
              )}%`,
            }}
          />
        </div>
        <p className="text-[10px] text-gray-600 mt-2">
          The AI can run up to {stats.max_workers || 5} tasks simultaneously.
          Each task runs in its own isolated process for safety.
        </p>
      </div>
    </div>
  );
}

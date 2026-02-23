import { useState, useEffect, useCallback } from "react";
import {
  Cpu,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  StopCircle,
  BarChart3,
  Zap,
  Timer,
  Brain,
  Calendar,
  Play,
  Pause,
  Trash2,
  ChevronDown,
  ChevronRight,
  Settings2,
  Sparkles,
  AlertTriangle,
  History,
  Layers,
} from "lucide-react";
import { api } from "../../lib/api";

// ── Shared Components ──────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; bg: string; label: string; pulse?: boolean }> = {
    running:   { color: "text-blue-400",    bg: "bg-blue-500/10",    label: "Running",    pulse: true },
    completed: { color: "text-emerald-400", bg: "bg-emerald-500/10", label: "Completed" },
    failed:    { color: "text-red-400",     bg: "bg-red-500/10",     label: "Failed" },
    cancelled: { color: "text-gray-400",    bg: "bg-gray-500/10",    label: "Cancelled" },
    queued:    { color: "text-amber-400",   bg: "bg-amber-500/10",   label: "Queued" },
    waiting:   { color: "text-amber-400",   bg: "bg-amber-500/10",   label: "Waiting" },
    active:    { color: "text-blue-400",    bg: "bg-blue-500/10",    label: "Active",     pulse: true },
    paused:    { color: "text-amber-400",   bg: "bg-amber-500/10",   label: "Paused" },
    idle:      { color: "text-gray-400",    bg: "bg-gray-500/10",    label: "Idle" },
  };
  const c = config[status] || config.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full ${c.bg} ${c.color}`}>
      {c.pulse && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {c.label}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, color, sub }: {
  icon: React.ElementType; label: string; value: string | number; color: string; sub?: string;
}) {
  const cm: Record<string, string> = {
    blue: "bg-blue-500/10 text-blue-400", emerald: "bg-emerald-500/10 text-emerald-400",
    red: "bg-red-500/10 text-red-400", purple: "bg-purple-500/10 text-purple-400",
    amber: "bg-amber-500/10 text-amber-400", cyan: "bg-cyan-500/10 text-cyan-400",
  };
  return (
    <div className="card flex items-center gap-3 py-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${cm[color]}`}>
        <Icon className="w-4.5 h-4.5" />
      </div>
      <div>
        <p className="text-base font-bold text-gray-200">{value}</p>
        <p className="text-[11px] text-gray-500">{label}</p>
        {sub && <p className="text-[10px] text-gray-600">{sub}</p>}
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

// Tab button
function Tab({ active, onClick, icon: Icon, label, badge }: {
  active: boolean; onClick: () => void; icon: React.ElementType; label: string; badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
        active
          ? "bg-blue-500/10 text-blue-400 border border-blue-500/30"
          : "text-gray-400 hover:text-gray-300 hover:bg-gray-800/50"
      }`}
    >
      <Icon className="w-4 h-4" />
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
          {badge}
        </span>
      )}
    </button>
  );
}

// ── Workers Tab ────────────────────────────────────────────

function WorkersTab() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetch_ = useCallback(async () => {
    try {
      const r = await api.getWorkers();
      setData(r);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);
  useEffect(() => {
    if (!autoRefresh) return;
    const iv = setInterval(fetch_, 2000);
    return () => clearInterval(iv);
  }, [autoRefresh, fetch_]);

  const handleCancel = async (id: string) => {
    try { await api.cancelWorker(id); fetch_(); } catch { /* ignore */ }
  };

  if (loading) return <LoadingSpinner text="Loading workers..." />;

  const stats = data?.stats || {};
  const workers = data?.workers || [];
  const active = workers.filter((w: any) => w.state === "running" || w.status === "running");
  const queued = workers.filter((w: any) => w.state === "queued" || w.status === "queued");
  const recent = workers.filter((w: any) =>
    w.state === "completed" || w.state === "failed" || w.state === "cancelled" ||
    w.status === "completed" || w.status === "failed" || w.status === "cancelled"
  );

  return (
    <div className="space-y-5">
      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard icon={Zap} label="Active" value={stats.active || active.length} color="blue" />
        <StatCard icon={Clock} label="Queued" value={stats.queued || queued.length} color="amber" />
        <StatCard icon={CheckCircle2} label="Completed" value={stats.completed || 0} color="emerald" />
        <StatCard icon={XCircle} label="Failed" value={stats.failed || 0} color="red" />
      </div>

      {/* Capacity Bar */}
      <div className="card py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-400 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5" />
            Worker Capacity
          </span>
          <span className="text-xs text-gray-500">
            {active.length} / {stats.max_concurrent || stats.max_workers || 3} slots
          </span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div
            className="bg-gradient-to-r from-blue-500 to-purple-500 rounded-full h-2 transition-all duration-500"
            style={{ width: `${Math.min((active.length / (stats.max_concurrent || stats.max_workers || 3)) * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Active Workers */}
      {active.length > 0 && (
        <div>
          <SectionHeader icon={Activity} title="Active Workers" count={active.length} pulse />
          <div className="space-y-2">
            {active.map((w: any) => (
              <WorkerCard key={w.task_id || w.id} worker={w} onCancel={handleCancel} />
            ))}
          </div>
        </div>
      )}

      {/* Queued */}
      {queued.length > 0 && (
        <div>
          <SectionHeader icon={Clock} title="Queued" count={queued.length} />
          <div className="space-y-2">
            {queued.map((w: any) => (
              <div key={w.task_id || w.id} className="card py-3 flex items-center gap-3">
                <Clock className="w-4 h-4 text-amber-400" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-300 truncate">{w.task || w.description || w.task_id}</p>
                  {w.model && <p className="text-[10px] text-gray-500 mt-0.5">Model: {w.model}</p>}
                </div>
                <StatusBadge status="queued" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent */}
      <div>
        <SectionHeader icon={History} title="Recent Tasks" count={recent.length} />
        {recent.length === 0 ? (
          <EmptyState icon={BarChart3} text="No tasks yet" sub="Workers will appear here when Plutus spawns parallel tasks" />
        ) : (
          <div className="card p-0 overflow-hidden divide-y divide-gray-800">
            {recent.slice(0, 20).map((w: any, i: number) => (
              <RecentTaskRow key={w.task_id || i} task={w} />
            ))}
          </div>
        )}
      </div>

      {/* Auto-refresh toggle */}
      <div className="flex justify-center">
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-colors ${
            autoRefresh
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              : "bg-gray-800 text-gray-400 border border-gray-700"
          }`}
        >
          <Activity className={`w-3 h-3 ${autoRefresh ? "animate-pulse" : ""}`} />
          {autoRefresh ? "Live Updates" : "Paused"}
        </button>
      </div>
    </div>
  );
}

function WorkerCard({ worker, onCancel }: { worker: any; onCancel: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const id = worker.task_id || worker.id;
  return (
    <div className="card border-blue-500/20 bg-blue-500/5">
      <div className="flex items-center gap-3">
        <div className="relative">
          <div className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-pulse" />
          <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-blue-400 animate-ping opacity-30" />
        </div>
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">
              {worker.task || worker.description || id?.slice(0, 12)}
            </span>
            <StatusBadge status="running" />
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[10px] text-gray-500">
            {worker.model && <span>Model: {worker.model}</span>}
            <span>{formatDuration(worker.elapsed || 0)}</span>
            {worker.steps_completed !== undefined && <span>Steps: {worker.steps_completed}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setExpanded(!expanded)} className="text-gray-500 hover:text-gray-300">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
          <button
            onClick={() => onCancel(id)}
            className="text-xs py-1 px-2.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors flex items-center gap-1"
          >
            <StopCircle className="w-3 h-3" />
            Stop
          </button>
        </div>
      </div>
      {expanded && worker.progress && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="text-xs text-gray-400 space-y-1">
            {worker.progress.map((p: string, i: number) => (
              <p key={i} className="flex items-start gap-2">
                <span className="text-gray-600 shrink-0">{i + 1}.</span>
                <span>{p}</span>
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RecentTaskRow({ task }: { task: any }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={`hover:bg-gray-800/30 transition-colors ${expanded ? "bg-gray-800/20" : ""}`}>
      <div
        className="flex items-center gap-3 py-2.5 px-4 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <StatusBadge status={task.state || task.status} />
        <div className="flex-1 min-w-0">
          <span className="text-sm text-gray-300 truncate block">
            {task.task || task.description || task.task_id?.slice(0, 16)}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-gray-500 shrink-0">
          {task.model && <span>{task.model}</span>}
          <span>{formatDuration(task.duration || task.elapsed || 0)}</span>
          <span>{formatDate(task.completed_at || task.started_at)}</span>
        </div>
      </div>
      {expanded && (
        <div className="px-4 pb-3 space-y-2">
          {task.result && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Result</p>
              <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                {typeof task.result === "string" ? task.result : JSON.stringify(task.result, null, 2)}
              </pre>
            </div>
          )}
          {task.error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
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
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-300 mb-3"
        >
          {showHistory ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          <History className="w-4 h-4" />
          Execution History
          <span className="text-xs text-gray-600">({history.length})</span>
        </button>
        {showHistory && (
          history.length === 0 ? (
            <EmptyState icon={History} text="No executions yet" sub="History will appear after scheduled jobs run" />
          ) : (
            <div className="card p-0 overflow-hidden divide-y divide-gray-800">
              {history.map((ex: any, i: number) => (
                <div key={i} className="flex items-center gap-3 py-2.5 px-4">
                  <StatusBadge status={ex.status || "completed"} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-300 truncate">{ex.job_name || ex.job_id}</p>
                  </div>
                  <div className="text-[10px] text-gray-500 flex items-center gap-3">
                    <span>{formatDuration(ex.duration || 0)}</span>
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
    <div className={`card ${isActive ? "border-emerald-500/20" : isPaused ? "border-amber-500/20 opacity-75" : ""}`}>
      <div className="flex items-center gap-3">
        <Calendar className={`w-4 h-4 shrink-0 ${isActive ? "text-emerald-400" : "text-gray-500"}`} />
        <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpanded(!expanded)}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">
              {job.name || job.task || id}
            </span>
            <StatusBadge status={job.status} />
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[10px] text-gray-500">
            {job.schedule && <span className="font-mono">{job.schedule}</span>}
            {job.cron && <span className="font-mono">{job.cron}</span>}
            {job.interval && <span>Every {formatDuration(job.interval)}</span>}
            {job.next_run && <span>Next: {formatDate(job.next_run)}</span>}
            {job.last_run && <span>Last: {formatDate(job.last_run)}</span>}
            {job.run_count !== undefined && <span>Runs: {job.run_count}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {isActive ? (
            <button
              onClick={() => onPause(id)}
              className="p-1.5 rounded-lg text-amber-400 hover:bg-amber-500/10 transition-colors"
              title="Pause"
            >
              <Pause className="w-3.5 h-3.5" />
            </button>
          ) : isPaused ? (
            <button
              onClick={() => onResume(id)}
              className="p-1.5 rounded-lg text-emerald-400 hover:bg-emerald-500/10 transition-colors"
              title="Resume"
            >
              <Play className="w-3.5 h-3.5" />
            </button>
          ) : null}
          <button
            onClick={() => onDelete(id)}
            className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-800 text-xs text-gray-400 space-y-1">
          {job.task && <p><span className="text-gray-500">Task:</span> {job.task}</p>}
          {job.description && <p><span className="text-gray-500">Description:</span> {job.description}</p>}
          {job.model && <p><span className="text-gray-500">Model:</span> {job.model}</p>}
          {job.created_at && <p><span className="text-gray-500">Created:</span> {formatDate(job.created_at)}</p>}
        </div>
      )}
    </div>
  );
}

// ── Models Tab ─────────────────────────────────────────────

function ModelsTab() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetch_ = useCallback(async () => {
    try {
      const r = await api.getModelRouting();
      setData(r);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);

  const updateRouting = async (key: string, value: any) => {
    setSaving(true);
    try {
      await api.updateModelRouting({ [key]: value });
      fetch_();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  if (loading) return <LoadingSpinner text="Loading models..." />;

  const models = data?.models || [];
  const routing = data?.routing || {};
  const status = data?.status || {};

  // Group models by provider
  const byProvider: Record<string, any[]> = {};
  models.forEach((m: any) => {
    const p = m.provider || "unknown";
    if (!byProvider[p]) byProvider[p] = [];
    byProvider[p].push(m);
  });

  return (
    <div className="space-y-5">
      {/* Routing Config */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="w-4 h-4 text-purple-400" />
          <h3 className="text-sm font-semibold text-gray-200">Model Routing</h3>
          {saving && <RefreshCw className="w-3 h-3 text-gray-500 animate-spin" />}
        </div>

        <div className="space-y-4">
          {/* Auto-route toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-300">Auto-Route by Complexity</p>
              <p className="text-[10px] text-gray-500">Automatically select the best model based on task difficulty</p>
            </div>
            <button
              onClick={() => updateRouting("auto_route", !routing.auto_route)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                routing.auto_route ? "bg-purple-500" : "bg-gray-700"
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                routing.auto_route ? "translate-x-5" : "translate-x-0.5"
              }`} />
            </button>
          </div>

          {/* Cost-conscious toggle */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-300">Cost-Conscious Mode</p>
              <p className="text-[10px] text-gray-500">Prefer cheaper models when possible</p>
            </div>
            <button
              onClick={() => updateRouting("cost_conscious", !routing.cost_conscious)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                routing.cost_conscious ? "bg-emerald-500" : "bg-gray-700"
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                routing.cost_conscious ? "translate-x-5" : "translate-x-0.5"
              }`} />
            </button>
          </div>

          {/* Default model select */}
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">Default Model (when auto-route is off)</label>
            <select
              value={routing.default_model || "claude-sonnet"}
              onChange={(e) => updateRouting("default_model", e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-purple-500/50 focus:outline-none"
            >
              {models.map((m: any) => (
                <option key={m.id || m.name} value={m.id || m.name}>
                  {m.display_name || m.name} — {m.tier || "standard"}
                </option>
              ))}
            </select>
          </div>

          {/* Worker model select */}
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">Worker Model (for spawned workers)</label>
            <select
              value={routing.worker_model || "claude-haiku"}
              onChange={(e) => updateRouting("worker_model", e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-purple-500/50 focus:outline-none"
            >
              {models.map((m: any) => (
                <option key={m.id || m.name} value={m.id || m.name}>
                  {m.display_name || m.name} — {m.tier || "standard"}
                </option>
              ))}
            </select>
          </div>

          {/* Scheduler model select */}
          <div>
            <label className="text-xs text-gray-400 block mb-1.5">Scheduler Model (for cron jobs)</label>
            <select
              value={routing.scheduler_model || "claude-haiku"}
              onChange={(e) => updateRouting("scheduler_model", e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-purple-500/50 focus:outline-none"
            >
              {models.map((m: any) => (
                <option key={m.id || m.name} value={m.id || m.name}>
                  {m.display_name || m.name} — {m.tier || "standard"}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Available Models */}
      <div>
        <SectionHeader icon={Brain} title="Available Models" count={models.length} />
        {Object.entries(byProvider).map(([provider, providerModels]) => (
          <div key={provider} className="mb-4">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 pl-1">
              {provider === "anthropic" ? "Anthropic (Claude)" : provider === "openai" ? "OpenAI" : provider}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {(providerModels as any[]).map((m: any) => (
                <ModelCard key={m.id || m.name} model={m} />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Usage Stats */}
      {status.usage && (
        <div className="card">
          <SectionHeader icon={BarChart3} title="Usage" />
          <div className="grid grid-cols-3 gap-3 mt-3">
            <div className="text-center">
              <p className="text-lg font-bold text-gray-200">{status.usage.total_requests || 0}</p>
              <p className="text-[10px] text-gray-500">Total Requests</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-200">{status.usage.total_tokens || 0}</p>
              <p className="text-[10px] text-gray-500">Total Tokens</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-gray-200">${(status.usage.estimated_cost || 0).toFixed(4)}</p>
              <p className="text-[10px] text-gray-500">Est. Cost</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelCard({ model }: { model: any }) {
  const tierColors: Record<string, string> = {
    high: "text-purple-400 bg-purple-500/10",
    medium: "text-blue-400 bg-blue-500/10",
    low: "text-emerald-400 bg-emerald-500/10",
    fast: "text-emerald-400 bg-emerald-500/10",
  };
  const tier = model.tier || "medium";
  const tierColor = tierColors[tier] || tierColors.medium;

  return (
    <div className="card py-3 flex items-center gap-3">
      <Sparkles className={`w-4 h-4 shrink-0 ${tierColor.split(" ")[0]}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{model.display_name || model.name}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${tierColor}`}>
            {tier === "high" ? "Complex" : tier === "medium" ? "Balanced" : "Fast"}
          </span>
        </div>
        <p className="text-[10px] text-gray-500 mt-0.5">
          {model.model_id || model.id}
          {model.cost_per_1k_tokens && ` · $${model.cost_per_1k_tokens}/1K tokens`}
        </p>
      </div>
    </div>
  );
}

// ── Shared UI Helpers ──────────────────────────────────────

function SectionHeader({ icon: Icon, title, count, pulse }: {
  icon: React.ElementType; title: string; count?: number; pulse?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <div className="relative">
        <Icon className="w-4 h-4 text-gray-400" />
        {pulse && count && count > 0 && (
          <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-blue-400 animate-ping" />
        )}
      </div>
      <h2 className="text-sm font-semibold text-gray-300">{title}</h2>
      {count !== undefined && (
        <span className="text-xs text-gray-500">{count}</span>
      )}
    </div>
  );
}

function EmptyState({ icon: Icon, text, sub }: { icon: React.ElementType; text: string; sub?: string }) {
  return (
    <div className="card text-center py-8">
      <Icon className="w-8 h-8 text-gray-700 mx-auto mb-3" />
      <p className="text-sm text-gray-400">{text}</p>
      {sub && <p className="text-xs text-gray-600 mt-1 max-w-sm mx-auto">{sub}</p>}
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

// ── Main Component ─────────────────────────────────────────

export function WorkersView() {
  const [tab, setTab] = useState<"workers" | "scheduler" | "models">("workers");
  const [workerCount, setWorkerCount] = useState(0);
  const [jobCount, setJobCount] = useState(0);

  // Fetch badge counts
  useEffect(() => {
    const fetchCounts = async () => {
      try {
        const [w, s] = await Promise.all([
          api.getWorkers().catch(() => null),
          api.getScheduler().catch(() => null),
        ]);
        const workers = w?.workers || [];
        setWorkerCount(workers.filter((x: any) => x.state === "running" || x.status === "running").length);
        setJobCount(s?.stats?.active_jobs || s?.jobs?.length || 0);
      } catch { /* ignore */ }
    };
    fetchCounts();
    const iv = setInterval(fetchCounts, 5000);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="h-full overflow-y-auto max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-100">Workers & Automation</h1>
        <p className="text-sm text-gray-400 mt-1">
          Monitor workers, scheduled jobs, and model routing in real-time.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 mb-5 overflow-x-auto pb-1">
        <Tab active={tab === "workers"} onClick={() => setTab("workers")} icon={Cpu} label="Workers" badge={workerCount} />
        <Tab active={tab === "scheduler"} onClick={() => setTab("scheduler")} icon={Calendar} label="Scheduler" badge={jobCount} />
        <Tab active={tab === "models"} onClick={() => setTab("models")} icon={Brain} label="Models" />
      </div>

      {/* Tab Content */}
      {tab === "workers" && <WorkersTab />}
      {tab === "scheduler" && <SchedulerTab />}
      {tab === "models" && <ModelsTab />}
    </div>
  );
}

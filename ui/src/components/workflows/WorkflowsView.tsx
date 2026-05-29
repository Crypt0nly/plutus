import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Layers3,
  Loader2,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Trash2,
  Workflow,
  XCircle,
} from "lucide-react";
import { api, type AgentWorkflow, type AgentWorkflowRun, type AgentWorkflowStats } from "../../lib/api";

type NewWorkflowForm = {
  title: string;
  description: string;
  category: string;
};

type NewStepForm = {
  title: string;
  instruction: string;
  expected_output: string;
};

const emptyStats: AgentWorkflowStats = {
  workflow_count: 0,
  active_workflow_count: 0,
  run_count: 0,
  active_run_count: 0,
  success_count: 0,
  failure_count: 0,
};

function formatTime(ts?: number | null) {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString();
}

function statusClasses(status?: string) {
  switch (status) {
    case "active":
    case "completed":
      return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
    case "running":
    case "queued":
      return "border-sky-400/30 bg-sky-400/10 text-sky-200";
    case "failed":
    case "timeout":
      return "border-rose-400/30 bg-rose-400/10 text-rose-200";
    case "cancelled":
      return "border-amber-400/30 bg-amber-400/10 text-amber-200";
    default:
      return "border-white/10 bg-white/5 text-gray-300";
  }
}

function StatusPill({ status }: { status?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${statusClasses(status)}`}>
      {status || "draft"}
    </span>
  );
}

function StatCard({ label, value, icon: Icon }: { label: string; value: number; icon: React.ElementType }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-gray-500">{label}</div>
          <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
        </div>
        <div className="rounded-xl border border-plutus-400/20 bg-plutus-500/10 p-2 text-plutus-200">
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

export function WorkflowsView() {
  const [workflows, setWorkflows] = useState<AgentWorkflow[]>([]);
  const [runs, setRuns] = useState<AgentWorkflowRun[]>([]);
  const [stats, setStats] = useState<AgentWorkflowStats>(emptyStats);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newWorkflow, setNewWorkflow] = useState<NewWorkflowForm>({ title: "", description: "", category: "General" });
  const [newStep, setNewStep] = useState<NewStepForm>({ title: "", instruction: "", expected_output: "" });

  const selected = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedId) || workflows[0] || null,
    [workflows, selectedId]
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api.getAgentWorkflowsOverview();
      setWorkflows(data.workflows || []);
      setRuns(data.runs || []);
      setStats(data.stats || emptyStats);
      setSelectedId((current) => current && data.workflows.some((workflow) => workflow.id === current) ? current : data.workflows[0]?.id || null);
    } catch (err: any) {
      setError(err?.message || "Could not load workflows");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 8000);
    return () => window.clearInterval(timer);
  }, [load]);

  const createWorkflow = async () => {
    if (!newWorkflow.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const { workflow } = await api.createAgentWorkflow({
        title: newWorkflow.title.trim(),
        description: newWorkflow.description.trim(),
        category: newWorkflow.category.trim() || "General",
        status: "active",
        trigger_type: "manual",
        priority: "normal",
      });
      setNewWorkflow({ title: "", description: "", category: "General" });
      await load();
      setSelectedId(workflow.id);
    } catch (err: any) {
      setError(err?.message || "Could not create workflow");
    } finally {
      setSaving(false);
    }
  };

  const addStep = async () => {
    if (!selected || !newStep.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.addAgentWorkflowStep(selected.id, {
        title: newStep.title.trim(),
        instruction: newStep.instruction.trim(),
        expected_output: newStep.expected_output.trim(),
        agent_type: "general",
        status: "active",
        enabled: true,
      });
      setNewStep({ title: "", instruction: "", expected_output: "" });
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not add step");
    } finally {
      setSaving(false);
    }
  };

  const startRun = async (workflow: AgentWorkflow) => {
    setSaving(true);
    setError(null);
    try {
      await api.startAgentWorkflowRun(workflow.id);
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not start workflow");
    } finally {
      setSaving(false);
    }
  };

  const deleteWorkflow = async (workflow: AgentWorkflow) => {
    if (!window.confirm(`Delete workflow “${workflow.title}”?`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAgentWorkflow(workflow.id);
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not delete workflow");
    } finally {
      setSaving(false);
    }
  };

  const deleteStep = async (stepId: string) => {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAgentWorkflowStep(selected.id, stepId);
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not delete step");
    } finally {
      setSaving(false);
    }
  };

  const toggleWorkflowStatus = async (workflow: AgentWorkflow) => {
    setSaving(true);
    setError(null);
    try {
      await api.updateAgentWorkflow(workflow.id, { status: workflow.status === "active" ? "draft" : "active" });
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not update workflow");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        <Loader2 className="mr-2 animate-spin" size={18} /> Loading workflows…
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 text-gray-100">
      <div className="flex flex-col gap-4 rounded-3xl border border-white/10 bg-gradient-to-br from-gray-950 via-gray-950 to-plutus-950/30 p-6 shadow-2xl shadow-black/30 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-plutus-400/20 bg-plutus-400/10 px-3 py-1 text-xs font-medium text-plutus-100">
            <Workflow size={14} /> Agent Workflows
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">Turn repeatable work into one-click agent runs.</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Capture multi-step processes as reusable workflows, run them through local Plutus workers, and keep a lightweight history of every execution.
          </p>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-gray-200 hover:bg-white/10"
        >
          <RefreshCcw size={16} /> Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-100">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Workflows" value={stats.workflow_count} icon={Layers3} />
        <StatCard label="Active" value={stats.active_workflow_count} icon={CheckCircle2} />
        <StatCard label="Runs" value={stats.run_count} icon={Clock} />
        <StatCard label="In Progress" value={stats.active_run_count} icon={Play} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="flex flex-col gap-4">
          <div className="rounded-3xl border border-white/10 bg-gray-950/70 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-400">Create workflow</h2>
              <Plus size={16} className="text-plutus-200" />
            </div>
            <div className="space-y-3">
              <input
                value={newWorkflow.title}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, title: e.target.value }))}
                placeholder="Workflow name"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
              />
              <input
                value={newWorkflow.category}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, category: e.target.value }))}
                placeholder="Category"
                className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
              />
              <textarea
                value={newWorkflow.description}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, description: e.target.value }))}
                placeholder="What should this workflow accomplish?"
                rows={3}
                className="w-full resize-none rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
              />
              <button
                onClick={createWorkflow}
                disabled={saving || !newWorkflow.title.trim()}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-plutus-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-plutus-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Save workflow
              </button>
            </div>
          </div>

          <div className="overflow-hidden rounded-3xl border border-white/10 bg-gray-950/70">
            <div className="border-b border-white/10 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-gray-400">
              Library
            </div>
            <div className="max-h-[520px] overflow-y-auto p-2">
              {workflows.length === 0 ? (
                <div className="p-6 text-sm text-gray-500">No workflows yet. Create one to get started.</div>
              ) : workflows.map((workflow) => (
                <button
                  key={workflow.id}
                  onClick={() => setSelectedId(workflow.id)}
                  className={`mb-2 w-full rounded-2xl border p-4 text-left transition ${selected?.id === workflow.id ? "border-plutus-400/40 bg-plutus-500/10" : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-white">{workflow.title}</div>
                      <div className="mt-1 line-clamp-2 text-xs leading-5 text-gray-500">{workflow.description || "No description yet."}</div>
                    </div>
                    <StatusPill status={workflow.status} />
                  </div>
                  <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
                    <span>{workflow.steps?.length || 0} steps</span>
                    <span>{workflow.run_count || 0} runs</span>
                    <span>{workflow.category}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-6">
          {selected ? (
            <>
              <div className="rounded-3xl border border-white/10 bg-gray-950/70 p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="text-2xl font-semibold text-white">{selected.title}</h2>
                      <StatusPill status={selected.status} />
                    </div>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">{selected.description || "Add a description so teammates know when to use this workflow."}</p>
                    <div className="mt-4 grid gap-3 text-xs text-gray-500 sm:grid-cols-3">
                      <div>Last run: <span className="text-gray-300">{formatTime(selected.last_run_at)}</span></div>
                      <div>Successes: <span className="text-gray-300">{selected.success_count || 0}</span></div>
                      <div>Failures: <span className="text-gray-300">{selected.failure_count || 0}</span></div>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => startRun(selected)}
                      disabled={saving}
                      className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-400 disabled:opacity-50"
                    >
                      <Play size={16} /> Run
                    </button>
                    <button
                      onClick={() => toggleWorkflowStatus(selected)}
                      disabled={saving}
                      className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-gray-200 hover:bg-white/10 disabled:opacity-50"
                    >
                      {selected.status === "active" ? "Set draft" : "Activate"}
                    </button>
                    <button
                      onClick={() => deleteWorkflow(selected)}
                      disabled={saving}
                      className="inline-flex items-center gap-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-4 py-2 text-sm font-medium text-rose-100 hover:bg-rose-500/20 disabled:opacity-50"
                    >
                      <Trash2 size={16} /> Delete
                    </button>
                  </div>
                </div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-gray-950/70 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-white">Workflow steps</h3>
                  <span className="text-xs text-gray-500">Executed in order by a local worker</span>
                </div>
                <div className="space-y-3">
                  {(selected.steps || []).length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-gray-500">No steps yet. Add the first action below.</div>
                  ) : selected.steps.map((step, index) => (
                    <div key={step.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex gap-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-plutus-500/15 text-sm font-semibold text-plutus-100">{index + 1}</div>
                          <div>
                            <div className="font-medium text-white">{step.title}</div>
                            <div className="mt-1 text-sm leading-6 text-gray-400">{step.instruction || step.description || "No instruction yet."}</div>
                            {step.expected_output && <div className="mt-2 text-xs text-gray-500">Expected: {step.expected_output}</div>}
                          </div>
                        </div>
                        <button
                          onClick={() => deleteStep(step.id)}
                          className="rounded-lg p-2 text-gray-500 hover:bg-white/10 hover:text-rose-200"
                          title="Delete step"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="mt-4 grid gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4 lg:grid-cols-[1fr_1.5fr_1fr_auto]">
                  <input
                    value={newStep.title}
                    onChange={(e) => setNewStep((v) => ({ ...v, title: e.target.value }))}
                    placeholder="Step title"
                    className="rounded-xl border border-white/10 bg-gray-950 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
                  />
                  <input
                    value={newStep.instruction}
                    onChange={(e) => setNewStep((v) => ({ ...v, instruction: e.target.value }))}
                    placeholder="Instruction for the agent"
                    className="rounded-xl border border-white/10 bg-gray-950 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
                  />
                  <input
                    value={newStep.expected_output}
                    onChange={(e) => setNewStep((v) => ({ ...v, expected_output: e.target.value }))}
                    placeholder="Expected output"
                    className="rounded-xl border border-white/10 bg-gray-950 px-3 py-2 text-sm text-white outline-none placeholder:text-gray-600 focus:border-plutus-400/50"
                  />
                  <button
                    onClick={addStep}
                    disabled={saving || !newStep.title.trim()}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-gray-950 hover:bg-gray-200 disabled:opacity-50"
                  >
                    <Plus size={16} /> Add
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-3xl border border-white/10 bg-gray-950/70 p-8 text-center text-gray-500">Select or create a workflow to configure its steps.</div>
          )}

          <div className="rounded-3xl border border-white/10 bg-gray-950/70 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Recent runs</h3>
              <span className="text-xs text-gray-500">Auto-refreshes while the app is open</span>
            </div>
            <div className="space-y-3">
              {runs.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-gray-500">No workflow runs yet.</div>
              ) : runs.slice(0, 8).map((run) => (
                <div key={run.id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="flex items-center gap-2 font-medium text-white">
                        {run.status === "completed" ? <CheckCircle2 size={16} className="text-emerald-300" /> : run.status === "failed" ? <XCircle size={16} className="text-rose-300" /> : <Clock size={16} className="text-sky-300" />}
                        {run.workflow_title}
                      </div>
                      <div className="mt-1 text-xs text-gray-500">Started {formatTime(run.started_at)} {run.worker_task_id ? `• worker ${run.worker_task_id}` : ""}</div>
                    </div>
                    <StatusPill status={run.status} />
                  </div>
                  {run.result && <div className="mt-3 line-clamp-3 rounded-xl bg-black/20 p-3 text-xs leading-5 text-gray-400">{run.result}</div>}
                  {run.error && <div className="mt-3 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-xs leading-5 text-rose-100">{run.error}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

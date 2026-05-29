import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Layers3,
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Trash2,
  Workflow,
  X,
  XCircle,
} from "lucide-react";
import { api, type AgentWorkflow, type AgentWorkflowRun, type AgentWorkflowStats, type AgentWorkflowStep } from "../../lib/api";

type NewWorkflowForm = {
  title: string;
  description: string;
  category: string;
};

type WorkflowEditForm = {
  title: string;
  description: string;
  category: string;
  status: string;
  priority: string;
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

const panelClass = "rounded-3xl border border-gray-700/70 bg-gray-950/95 shadow-sm shadow-gray-950/5 dark:border-white/10 dark:bg-gray-950/70 dark:shadow-black/20";
const subtlePanelClass = "rounded-2xl border border-gray-700/70 bg-gray-900/80 dark:border-white/10 dark:bg-white/[0.03]";
const inputClass = "w-full rounded-xl border border-gray-700/80 bg-gray-950 px-3 py-2 text-sm text-gray-50 outline-none placeholder:text-gray-400 focus:border-plutus-500/60 focus:ring-2 focus:ring-plutus-500/10 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-gray-600";
const compactInputClass = "rounded-xl border border-gray-700/80 bg-gray-950 px-3 py-2 text-sm text-gray-50 outline-none placeholder:text-gray-400 focus:border-plutus-500/60 focus:ring-2 focus:ring-plutus-500/10 dark:border-white/10 dark:bg-gray-950 dark:text-white dark:placeholder:text-gray-600";
const secondaryButtonClass = "inline-flex items-center gap-2 rounded-xl border border-gray-700/80 bg-gray-950 px-4 py-2 text-sm font-medium text-gray-100 hover:border-gray-600 hover:bg-gray-900 disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10";

function formatTime(ts?: number | null) {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString();
}

function statusClasses(status?: string) {
  switch (status) {
    case "active":
    case "completed":
      return "border-emerald-500/30 bg-emerald-50 text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-200";
    case "running":
    case "queued":
      return "border-sky-500/30 bg-sky-50 text-sky-700 dark:border-sky-400/30 dark:bg-sky-400/10 dark:text-sky-200";
    case "failed":
    case "timeout":
      return "border-rose-500/30 bg-rose-50 text-rose-700 dark:border-rose-400/30 dark:bg-rose-400/10 dark:text-rose-200";
    case "cancelled":
      return "border-amber-500/30 bg-amber-50 text-amber-700 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-200";
    default:
      return "border-gray-700/80 bg-gray-900 text-gray-200 dark:border-white/10 dark:bg-white/5 dark:text-gray-300";
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
    <div className="rounded-2xl border border-gray-700/70 bg-gray-950/95 p-4 shadow-sm shadow-gray-950/5 dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/20">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-gray-400 dark:text-gray-500">{label}</div>
          <div className="mt-2 text-2xl font-semibold text-gray-50 dark:text-white">{value}</div>
        </div>
        <div className="rounded-xl border border-plutus-500/20 bg-plutus-50 p-2 text-plutus-600 dark:border-plutus-400/20 dark:bg-plutus-500/10 dark:text-plutus-200">
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
  const [editingWorkflow, setEditingWorkflow] = useState(false);
  const [workflowEdit, setWorkflowEdit] = useState<WorkflowEditForm>({ title: "", description: "", category: "General", status: "active", priority: "normal" });
  const [editingStepId, setEditingStepId] = useState<string | null>(null);
  const [stepEdit, setStepEdit] = useState<NewStepForm>({ title: "", instruction: "", expected_output: "" });

  const selected = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedId) || workflows[0] || null,
    [workflows, selectedId]
  );

  useEffect(() => {
    if (!selected) {
      setEditingWorkflow(false);
      setEditingStepId(null);
      return;
    }
    setWorkflowEdit({
      title: selected.title || "",
      description: selected.description || "",
      category: selected.category || "General",
      status: selected.status || "draft",
      priority: selected.priority || "normal",
    });
    setEditingWorkflow(false);
    setEditingStepId(null);
  }, [selected?.id]);

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

  const startEditWorkflow = (workflow: AgentWorkflow) => {
    setWorkflowEdit({
      title: workflow.title || "",
      description: workflow.description || "",
      category: workflow.category || "General",
      status: workflow.status || "draft",
      priority: workflow.priority || "normal",
    });
    setEditingWorkflow(true);
  };

  const cancelWorkflowEdit = () => {
    if (!selected) return;
    setWorkflowEdit({
      title: selected.title || "",
      description: selected.description || "",
      category: selected.category || "General",
      status: selected.status || "draft",
      priority: selected.priority || "normal",
    });
    setEditingWorkflow(false);
  };

  const saveWorkflowEdit = async () => {
    if (!selected || !workflowEdit.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateAgentWorkflow(selected.id, {
        title: workflowEdit.title.trim(),
        description: workflowEdit.description.trim(),
        category: workflowEdit.category.trim() || "General",
        status: workflowEdit.status,
        priority: workflowEdit.priority,
      });
      setEditingWorkflow(false);
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not update workflow");
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
      if (editingStepId === stepId) {
        setEditingStepId(null);
      }
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not delete step");
    } finally {
      setSaving(false);
    }
  };

  const startEditStep = (step: AgentWorkflowStep) => {
    setEditingStepId(step.id);
    setStepEdit({
      title: step.title || "",
      instruction: step.instruction || step.description || "",
      expected_output: step.expected_output || "",
    });
  };

  const cancelStepEdit = () => {
    setEditingStepId(null);
    setStepEdit({ title: "", instruction: "", expected_output: "" });
  };

  const saveStepEdit = async (stepId: string) => {
    if (!selected || !stepEdit.title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateAgentWorkflowStep(selected.id, stepId, {
        title: stepEdit.title.trim(),
        instruction: stepEdit.instruction.trim(),
        expected_output: stepEdit.expected_output.trim(),
      });
      cancelStepEdit();
      await load();
    } catch (err: any) {
      setError(err?.message || "Could not update step");
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
      <div className="relative overflow-hidden rounded-3xl border border-gray-700/70 bg-gradient-to-br from-gray-950 via-gray-950 to-plutus-50 p-6 shadow-sm shadow-gray-950/5 dark:border-white/10 dark:from-gray-950 dark:via-gray-950 dark:to-plutus-950/30 dark:shadow-2xl dark:shadow-black/30">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-plutus-400/40 to-transparent" />
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-plutus-500/20 bg-plutus-50 px-3 py-1 text-xs font-medium text-plutus-700 dark:border-plutus-400/20 dark:bg-plutus-400/10 dark:text-plutus-100">
              <Workflow size={14} /> Agent Workflows
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-gray-50 dark:text-white">Turn repeatable work into one-click agent runs.</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-300 dark:text-gray-400">
              Capture multi-step processes as reusable workflows, run them through local Plutus workers, and keep a lightweight history of every execution.
            </p>
          </div>
          <button
            onClick={load}
            className={secondaryButtonClass}
          >
            <RefreshCcw size={16} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-400/30 dark:bg-rose-500/10 dark:text-rose-100">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Workflows" value={stats.workflow_count} icon={Layers3} />
        <StatCard label="Active" value={stats.active_workflow_count} icon={CheckCircle2} />
        <StatCard label="Runs" value={stats.run_count} icon={Clock} />
        <StatCard label="Failures" value={stats.failure_count} icon={XCircle} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="flex flex-col gap-4">
          <div className={`${panelClass} p-4`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-400 dark:text-gray-500">Create workflow</h2>
              <div className="rounded-lg bg-plutus-50 p-1.5 text-plutus-600 dark:bg-plutus-500/10 dark:text-plutus-200">
                <Plus size={16} />
              </div>
            </div>
            <div className="space-y-3">
              <input
                value={newWorkflow.title}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, title: e.target.value }))}
                placeholder="Workflow name"
                className={inputClass}
              />
              <input
                value={newWorkflow.category}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, category: e.target.value }))}
                placeholder="Category"
                className={inputClass}
              />
              <textarea
                value={newWorkflow.description}
                onChange={(e) => setNewWorkflow((v) => ({ ...v, description: e.target.value }))}
                placeholder="What should this workflow accomplish?"
                rows={3}
                className={`${inputClass} resize-none`}
              />
              <button
                onClick={createWorkflow}
                disabled={saving || !newWorkflow.title.trim()}
                className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-plutus-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-plutus-500/20 hover:bg-plutus-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Save workflow
              </button>
            </div>
          </div>

          <div className={`overflow-hidden ${panelClass}`}>
            <div className="border-b border-gray-700/70 px-4 py-3 text-sm font-semibold uppercase tracking-[0.18em] text-gray-400 dark:border-white/10 dark:text-gray-500">
              Library
            </div>
            <div className="max-h-[520px] overflow-y-auto p-2">
              {workflows.length === 0 ? (
                <div className="p-6 text-sm text-gray-400 dark:text-gray-500">No workflows yet. Create one to get started.</div>
              ) : workflows.map((workflow) => (
                <button
                  key={workflow.id}
                  onClick={() => setSelectedId(workflow.id)}
                  className={`mb-2 w-full rounded-2xl border p-4 text-left transition ${selected?.id === workflow.id ? "border-plutus-500/40 bg-plutus-50 shadow-sm shadow-plutus-500/10 dark:border-plutus-400/40 dark:bg-plutus-500/10" : "border-gray-700/70 bg-gray-900/80 hover:border-gray-600 hover:bg-gray-800 dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-gray-50 dark:text-white">{workflow.title}</div>
                      <div className="mt-1 line-clamp-2 text-xs leading-5 text-gray-400 dark:text-gray-500">{workflow.description || "No description yet."}</div>
                    </div>
                    <StatusPill status={workflow.status} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-gray-400 dark:text-gray-500">
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
              <div className={`${panelClass} p-5`}>
                {editingWorkflow ? (
                  <div className="space-y-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h2 className="text-2xl font-semibold text-gray-50 dark:text-white">Edit workflow</h2>
                        <p className="mt-1 text-sm leading-6 text-gray-300 dark:text-gray-400">Update the workflow details without losing its run history or configured steps.</p>
                      </div>
                      <button onClick={cancelWorkflowEdit} disabled={saving} className={secondaryButtonClass}>
                        <X size={16} /> Cancel
                      </button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <input
                        value={workflowEdit.title}
                        onChange={(e) => setWorkflowEdit((v) => ({ ...v, title: e.target.value }))}
                        placeholder="Workflow name"
                        className={inputClass}
                      />
                      <input
                        value={workflowEdit.category}
                        onChange={(e) => setWorkflowEdit((v) => ({ ...v, category: e.target.value }))}
                        placeholder="Category"
                        className={inputClass}
                      />
                      <select
                        value={workflowEdit.status}
                        onChange={(e) => setWorkflowEdit((v) => ({ ...v, status: e.target.value }))}
                        className={inputClass}
                      >
                        <option value="draft">Draft</option>
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                      </select>
                      <select
                        value={workflowEdit.priority}
                        onChange={(e) => setWorkflowEdit((v) => ({ ...v, priority: e.target.value }))}
                        className={inputClass}
                      >
                        <option value="low">Low priority</option>
                        <option value="normal">Normal priority</option>
                        <option value="high">High priority</option>
                      </select>
                    </div>
                    <textarea
                      value={workflowEdit.description}
                      onChange={(e) => setWorkflowEdit((v) => ({ ...v, description: e.target.value }))}
                      placeholder="What should this workflow accomplish?"
                      rows={4}
                      className={`${inputClass} resize-none`}
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={saveWorkflowEdit}
                        disabled={saving || !workflowEdit.title.trim()}
                        className="inline-flex items-center gap-2 rounded-xl bg-plutus-500 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-plutus-500/20 hover:bg-plutus-400 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />} Save changes
                      </button>
                      <button onClick={cancelWorkflowEdit} disabled={saving} className={secondaryButtonClass}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="text-2xl font-semibold text-gray-50 dark:text-white">{selected.title}</h2>
                        <StatusPill status={selected.status} />
                      </div>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-300 dark:text-gray-400">{selected.description || "Add a description so teammates know when to use this workflow."}</p>
                      <div className="mt-4 grid gap-3 text-xs text-gray-400 dark:text-gray-500 sm:grid-cols-5">
                        <div>Category: <span className="text-gray-100 dark:text-gray-300">{selected.category || "General"}</span></div>
                        <div>Priority: <span className="text-gray-100 dark:text-gray-300">{selected.priority || "normal"}</span></div>
                        <div>Last run: <span className="text-gray-100 dark:text-gray-300">{formatTime(selected.last_run_at)}</span></div>
                        <div>Successes: <span className="text-gray-100 dark:text-gray-300">{selected.success_count || 0}</span></div>
                        <div>Failures: <span className="text-gray-100 dark:text-gray-300">{selected.failure_count || 0}</span></div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => startRun(selected)}
                        disabled={saving}
                        className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-emerald-500/20 hover:bg-emerald-400 disabled:opacity-50"
                      >
                        <Play size={16} /> Run
                      </button>
                      <button
                        onClick={() => startEditWorkflow(selected)}
                        disabled={saving}
                        className={secondaryButtonClass}
                      >
                        <Pencil size={16} /> Edit
                      </button>
                      <button
                        onClick={() => toggleWorkflowStatus(selected)}
                        disabled={saving}
                        className={secondaryButtonClass}
                      >
                        {selected.status === "active" ? "Set draft" : "Activate"}
                      </button>
                      <button
                        onClick={() => deleteWorkflow(selected)}
                        disabled={saving}
                        className="inline-flex items-center gap-2 rounded-xl border border-rose-500/25 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-50 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-100 dark:hover:bg-rose-500/20"
                      >
                        <Trash2 size={16} /> Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className={`${panelClass} p-5`}>
                <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <h3 className="text-lg font-semibold text-gray-50 dark:text-white">Workflow steps</h3>
                  <span className="text-xs text-gray-400 dark:text-gray-500">Executed in order by a local worker</span>
                </div>
                <div className="space-y-3">
                  {(selected.steps || []).length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-gray-700/80 p-6 text-sm text-gray-400 dark:border-white/10 dark:text-gray-500">No steps yet. Add the first action below.</div>
                  ) : selected.steps.map((step, index) => (
                    <div key={step.id} className={`${subtlePanelClass} p-4`}>
                      {editingStepId === step.id ? (
                        <div className="space-y-3">
                          <div className="flex gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-plutus-50 text-sm font-semibold text-plutus-700 dark:bg-plutus-500/15 dark:text-plutus-100">{index + 1}</div>
                            <input
                              value={stepEdit.title}
                              onChange={(e) => setStepEdit((v) => ({ ...v, title: e.target.value }))}
                              placeholder="Step title"
                              className={compactInputClass}
                            />
                          </div>
                          <textarea
                            value={stepEdit.instruction}
                            onChange={(e) => setStepEdit((v) => ({ ...v, instruction: e.target.value }))}
                            placeholder="Instruction for the agent"
                            rows={3}
                            className={`${inputClass} resize-none`}
                          />
                          <input
                            value={stepEdit.expected_output}
                            onChange={(e) => setStepEdit((v) => ({ ...v, expected_output: e.target.value }))}
                            placeholder="Expected output"
                            className={compactInputClass}
                          />
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() => saveStepEdit(step.id)}
                              disabled={saving || !stepEdit.title.trim()}
                              className="inline-flex items-center gap-2 rounded-xl bg-plutus-500 px-3 py-2 text-sm font-semibold text-white hover:bg-plutus-400 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {saving ? <Loader2 className="animate-spin" size={15} /> : <Save size={15} />} Save step
                            </button>
                            <button onClick={cancelStepEdit} disabled={saving} className={secondaryButtonClass}>Cancel</button>
                            <button
                              onClick={() => deleteStep(step.id)}
                              disabled={saving}
                              className="inline-flex items-center gap-2 rounded-xl border border-rose-500/25 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-50 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-100 dark:hover:bg-rose-500/20"
                            >
                              <Trash2 size={15} /> Delete
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex gap-3">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-plutus-50 text-sm font-semibold text-plutus-700 dark:bg-plutus-500/15 dark:text-plutus-100">{index + 1}</div>
                            <div>
                              <div className="font-medium text-gray-50 dark:text-white">{step.title}</div>
                              <div className="mt-1 text-sm leading-6 text-gray-300 dark:text-gray-400">{step.instruction || step.description || "No instruction yet."}</div>
                              {step.expected_output && <div className="mt-2 text-xs text-gray-400 dark:text-gray-500">Expected: {step.expected_output}</div>}
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <button
                              onClick={() => startEditStep(step)}
                              className="rounded-lg p-2 text-gray-400 hover:bg-plutus-50 hover:text-plutus-600 dark:text-gray-500 dark:hover:bg-white/10 dark:hover:text-plutus-200"
                              title="Edit step"
                            >
                              <Pencil size={15} />
                            </button>
                            <button
                              onClick={() => deleteStep(step.id)}
                              className="rounded-lg p-2 text-gray-400 hover:bg-rose-50 hover:text-rose-600 dark:text-gray-500 dark:hover:bg-white/10 dark:hover:text-rose-200"
                              title="Delete step"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div className="mt-4 grid gap-3 rounded-2xl border border-gray-700/70 bg-gray-900/80 p-4 dark:border-white/10 dark:bg-white/[0.03] lg:grid-cols-[1fr_1.5fr_1fr_auto]">
                  <input
                    value={newStep.title}
                    onChange={(e) => setNewStep((v) => ({ ...v, title: e.target.value }))}
                    placeholder="Step title"
                    className={compactInputClass}
                  />
                  <input
                    value={newStep.instruction}
                    onChange={(e) => setNewStep((v) => ({ ...v, instruction: e.target.value }))}
                    placeholder="Instruction for the agent"
                    className={compactInputClass}
                  />
                  <input
                    value={newStep.expected_output}
                    onChange={(e) => setNewStep((v) => ({ ...v, expected_output: e.target.value }))}
                    placeholder="Expected output"
                    className={compactInputClass}
                  />
                  <button
                    onClick={addStep}
                    disabled={saving || !newStep.title.trim()}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-gray-50 px-4 py-2 text-sm font-semibold text-gray-950 shadow-sm shadow-gray-950/10 hover:bg-gray-100 disabled:opacity-50 dark:bg-white dark:text-gray-950 dark:hover:bg-gray-200"
                  >
                    <Plus size={16} /> Add
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className={`${panelClass} p-8 text-center text-gray-400 dark:text-gray-500`}>Select or create a workflow to configure its steps.</div>
          )}

          <div className={`${panelClass} p-5`}>
            <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <h3 className="text-lg font-semibold text-gray-50 dark:text-white">Recent runs</h3>
              <span className="text-xs text-gray-400 dark:text-gray-500">Auto-refreshes while the app is open</span>
            </div>
            <div className="space-y-3">
              {runs.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-gray-700/80 p-6 text-sm text-gray-400 dark:border-white/10 dark:text-gray-500">No workflow runs yet.</div>
              ) : runs.slice(0, 8).map((run) => (
                <div key={run.id} className={`${subtlePanelClass} p-4`}>
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="flex items-center gap-2 font-medium text-gray-50 dark:text-white">
                        {run.status === "completed" ? <CheckCircle2 size={16} className="text-emerald-500 dark:text-emerald-300" /> : run.status === "failed" ? <XCircle size={16} className="text-rose-500 dark:text-rose-300" /> : <Clock size={16} className="text-sky-500 dark:text-sky-300" />}
                        {run.workflow_title}
                      </div>
                      <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">Started {formatTime(run.started_at)} {run.worker_task_id ? `• worker ${run.worker_task_id}` : ""}</div>
                    </div>
                    <StatusPill status={run.status} />
                  </div>
                  {run.result && <div className="mt-3 line-clamp-3 rounded-xl bg-gray-800 p-3 text-xs leading-5 text-gray-300 dark:bg-black/20 dark:text-gray-400">{run.result}</div>}
                  {run.error && <div className="mt-3 rounded-xl border border-rose-500/25 bg-rose-50 p-3 text-xs leading-5 text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-100">{run.error}</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

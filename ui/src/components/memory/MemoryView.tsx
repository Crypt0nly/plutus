import { useEffect, useState, useCallback } from "react";
import {
  Brain,
  Target,
  BookOpen,
  Database,
  CheckCircle2,
  XCircle,
  Clock,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ListChecks,
  Bookmark,
  AlertCircle,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

// ─── Sub-components ───────────────────────────────────────────

function StatsCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    blue: "text-blue-400 bg-blue-500/10",
    emerald: "text-emerald-400 bg-emerald-500/10",
    amber: "text-amber-400 bg-amber-500/10",
    purple: "text-purple-400 bg-purple-500/10",
    plutus: "text-plutus-400 bg-plutus-500/10",
    gray: "text-gray-400 bg-gray-500/10",
  };
  const cls = colorMap[color] || colorMap.gray;

  return (
    <div className="card flex items-center gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${cls}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-lg font-bold text-gray-200">{value}</p>
        <p className="text-xs text-gray-500">{label}</p>
      </div>
    </div>
  );
}

function PlanCard({ plan }: { plan: Record<string, any> }) {
  const [expanded, setExpanded] = useState(plan.status === "active");

  const statusColors: Record<string, string> = {
    active: "text-blue-400 bg-blue-500/10",
    completed: "text-emerald-400 bg-emerald-500/10",
    cancelled: "text-gray-400 bg-gray-500/10",
    failed: "text-red-400 bg-red-500/10",
  };

  const stepStatusIcons: Record<string, React.ElementType> = {
    done: CheckCircle2,
    in_progress: Clock,
    failed: XCircle,
    skipped: AlertCircle,
    pending: Clock,
  };

  const stepStatusColors: Record<string, string> = {
    done: "text-emerald-400",
    in_progress: "text-blue-400 animate-pulse",
    failed: "text-red-400",
    skipped: "text-gray-500",
    pending: "text-gray-600",
  };

  const steps = plan.steps || [];
  const doneCount = steps.filter((s: any) => s.status === "done" || s.status === "skipped").length;
  const progress = steps.length > 0 ? Math.round((doneCount / steps.length) * 100) : 0;

  return (
    <div className="card">
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-500" />
        )}
        <ListChecks className="w-5 h-5 text-blue-400" />
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-gray-200">{plan.title}</h4>
          {plan.goal && (
            <p className="text-xs text-gray-500 mt-0.5">{plan.goal}</p>
          )}
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            statusColors[plan.status] || statusColors.active
          }`}
        >
          {plan.status}
        </span>
        <span className="text-xs text-gray-500">
          {doneCount}/{steps.length}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mt-3 bg-gray-800 rounded-full h-1.5">
        <div
          className="bg-blue-500 rounded-full h-1.5 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Steps */}
      {expanded && steps.length > 0 && (
        <div className="mt-3 space-y-1.5 ml-6">
          {steps.map((step: any, idx: number) => {
            const StepIcon = stepStatusIcons[step.status] || Clock;
            const stepColor = stepStatusColors[step.status] || "text-gray-600";
            return (
              <div key={idx} className="flex items-start gap-2">
                <StepIcon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${stepColor}`} />
                <div className="flex-1">
                  <p
                    className={`text-sm ${
                      step.status === "done"
                        ? "text-gray-400 line-through"
                        : step.status === "in_progress"
                        ? "text-blue-300 font-medium"
                        : "text-gray-400"
                    }`}
                  >
                    {step.description}
                  </p>
                  {step.result && (
                    <p className="text-xs text-gray-600 mt-0.5">{step.result}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GoalItem({
  goal,
}: {
  goal: Record<string, any>;
}) {
  const statusIcons: Record<string, React.ElementType> = {
    active: Target,
    completed: CheckCircle2,
    failed: XCircle,
    cancelled: AlertCircle,
  };
  const statusColors: Record<string, string> = {
    active: "text-blue-400",
    completed: "text-emerald-400",
    failed: "text-red-400",
    cancelled: "text-gray-500",
  };

  const Icon = statusIcons[goal.status] || Target;
  const color = statusColors[goal.status] || "text-gray-400";

  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${color}`} />
      <div className="flex-1">
        <p className={`text-sm ${goal.status === "completed" ? "text-gray-500 line-through" : "text-gray-300"}`}>
          {goal.description}
        </p>
        <p className="text-xs text-gray-600 mt-0.5">
          {goal.status} · priority {goal.priority ?? 0}
        </p>
      </div>
    </div>
  );
}

function FactItem({
  fact,
  onDelete,
}: {
  fact: Record<string, any>;
  onDelete: (id: number) => void;
}) {
  const categoryColors: Record<string, string> = {
    task_context: "bg-blue-500/20 text-blue-400",
    decision: "bg-purple-500/20 text-purple-400",
    progress: "bg-emerald-500/20 text-emerald-400",
    file_path: "bg-amber-500/20 text-amber-400",
    technical: "bg-cyan-500/20 text-cyan-400",
    user_preference: "bg-pink-500/20 text-pink-400",
    environment: "bg-orange-500/20 text-orange-400",
    credential: "bg-red-500/20 text-red-400",
    general: "bg-gray-500/20 text-gray-400",
  };

  const catCls = categoryColors[fact.category] || categoryColors.general;

  return (
    <div className="flex items-start gap-3 py-2 group">
      <Bookmark className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-600" />
      <div className="flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${catCls}`}>
            {fact.category}
          </span>
        </div>
        <p className="text-sm text-gray-300">{fact.content}</p>
      </div>
      <button
        onClick={() => onDelete(fact.id)}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-600 hover:text-red-400"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

function SummaryCard({ summary }: { summary: Record<string, any> | null }) {
  if (!summary) {
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <BookOpen className="w-4 h-4 text-gray-500" />
          <h4 className="text-sm font-semibold text-gray-400">Conversation Summary</h4>
        </div>
        <p className="text-sm text-gray-600 italic">No summary yet — conversation is short enough to fit in context.</p>
      </div>
    );
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-purple-400" />
        <h4 className="text-sm font-semibold text-gray-300">Conversation Summary</h4>
        <span className="text-xs text-gray-600 ml-auto">
          {summary.summarized_count ?? 0} messages compressed
        </span>
      </div>

      {/* Goals from summary */}
      {summary.goals && summary.goals.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Goals</p>
          <ul className="space-y-1">
            {summary.goals.map((g: string, i: number) => (
              <li key={i} className="text-sm text-blue-300 flex items-start gap-2">
                <Target className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                {g}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Current state */}
      {summary.current_state && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Current State</p>
          <p className="text-sm text-gray-300">{summary.current_state}</p>
        </div>
      )}

      {/* Progress */}
      {summary.progress && summary.progress.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Progress</p>
          <ul className="space-y-1">
            {summary.progress.map((p: string, i: number) => (
              <li key={i} className="text-sm text-emerald-300 flex items-start gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Key facts */}
      {summary.key_facts && summary.key_facts.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Key Facts</p>
          <ul className="space-y-1">
            {summary.key_facts.map((f: string, i: number) => (
              <li key={i} className="text-sm text-gray-400 flex items-start gap-2">
                <Bookmark className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-600" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Next steps */}
      {summary.next_steps && summary.next_steps.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Next Steps</p>
          <ul className="space-y-1">
            {summary.next_steps.map((s: string, i: number) => (
              <li key={i} className="text-sm text-amber-300 flex items-start gap-2">
                <Clock className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Full summary text */}
      {summary.summary && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Full Summary</p>
          <p className="text-sm text-gray-400 whitespace-pre-wrap">{summary.summary}</p>
        </div>
      )}
    </div>
  );
}

// ─── Main View ────────────────────────────────────────────────

export function MemoryView() {
  const { conversationId } = useAppStore();

  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [plans, setPlans] = useState<Record<string, any>[]>([]);
  const [goals, setGoals] = useState<Record<string, any>[]>([]);
  const [facts, setFacts] = useState<Record<string, any>[]>([]);
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "plans" | "goals" | "facts" | "summary">("overview");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, plansData, goalsData, factsData] = await Promise.all([
        api.getMemoryStats().catch(() => null),
        api.getPlans(conversationId ?? undefined).catch(() => []),
        api.getGoals(conversationId ?? undefined).catch(() => ({ goals: [] })),
        api.getFacts().catch(() => ({ facts: [] })),
      ]);

      setStats(statsData);
      setPlans(Array.isArray(plansData) ? plansData : []);
      setGoals(goalsData?.goals || []);
      setFacts(factsData?.facts || []);

      // Load summary if we have a conversation
      if (conversationId) {
        const summaryData = await api.getConversationSummary(conversationId).catch(() => ({ summary: null }));
        setSummary(summaryData?.summary || null);
      }
    } catch (e) {
      console.error("Failed to load memory data:", e);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDeleteFact = async (factId: number) => {
    try {
      await api.deleteFact(factId);
      setFacts((prev) => prev.filter((f) => f.id !== factId));
    } catch (e) {
      console.error("Failed to delete fact:", e);
    }
  };

  const activePlans = plans.filter((p) => p.status === "active");
  const completedPlans = plans.filter((p) => p.status === "completed");
  const activeGoals = goals.filter((g) => g.status === "active");

  const tabs = [
    { id: "overview" as const, label: "Overview", icon: Brain },
    { id: "plans" as const, label: "Plans", icon: ListChecks, count: activePlans.length },
    { id: "goals" as const, label: "Goals", icon: Target, count: activeGoals.length },
    { id: "facts" as const, label: "Facts", icon: Bookmark, count: facts.length },
    { id: "summary" as const, label: "Summary", icon: BookOpen },
  ];

  return (
    <div className="h-full overflow-y-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-100 mb-1">Memory & Plans</h2>
          <p className="text-sm text-gray-500">
            Persistent memory, goals, and execution plans — the agent never forgets
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? "bg-gray-800 text-gray-200 shadow-sm"
                  : "text-gray-500 hover:text-gray-300"
              }`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
              {tab.count !== undefined && tab.count > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-400 font-semibold">
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 lg:grid-cols-6">
            <StatsCard icon={Database} label="Messages" value={stats?.messages ?? 0} color="blue" />
            <StatsCard icon={Brain} label="Conversations" value={stats?.conversations ?? 0} color="purple" />
            <StatsCard icon={Bookmark} label="Facts" value={stats?.facts ?? 0} color="amber" />
            <StatsCard icon={Target} label="Active Goals" value={stats?.active_goals ?? 0} color="emerald" />
            <StatsCard icon={BookOpen} label="Summaries" value={stats?.summaries ?? 0} color="plutus" />
            <StatsCard icon={ListChecks} label="Checkpoints" value={stats?.checkpoints ?? 0} color="gray" />
          </div>

          {/* Active plan */}
          {activePlans.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-3">Active Plans</h3>
              <div className="space-y-3">
                {activePlans.map((plan) => (
                  <PlanCard key={plan.id} plan={plan} />
                ))}
              </div>
            </div>
          )}

          {/* Active goals */}
          {activeGoals.length > 0 && (
            <div className="card">
              <h3 className="text-sm font-semibold text-gray-300 mb-3">Active Goals</h3>
              <div className="divide-y divide-gray-800">
                {activeGoals.slice(0, 5).map((goal) => (
                  <GoalItem key={goal.id} goal={goal} />
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {conversationId && <SummaryCard summary={summary} />}
        </div>
      )}

      {activeTab === "plans" && (
        <div className="space-y-4">
          {plans.length === 0 ? (
            <div className="card text-center py-8">
              <ListChecks className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500">No plans yet. The agent creates plans for complex tasks.</p>
            </div>
          ) : (
            <>
              {activePlans.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-300 mb-3">Active</h3>
                  <div className="space-y-3">
                    {activePlans.map((plan) => (
                      <PlanCard key={plan.id} plan={plan} />
                    ))}
                  </div>
                </div>
              )}
              {completedPlans.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-300 mb-3">Completed</h3>
                  <div className="space-y-3">
                    {completedPlans.map((plan) => (
                      <PlanCard key={plan.id} plan={plan} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {activeTab === "goals" && (
        <div className="card">
          {goals.length === 0 ? (
            <div className="text-center py-8">
              <Target className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500">No goals tracked yet.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-800">
              {goals.map((goal) => (
                <GoalItem key={goal.id} goal={goal} />
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "facts" && (
        <div className="card">
          {facts.length === 0 ? (
            <div className="text-center py-8">
              <Bookmark className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500">No facts stored yet. The agent saves important information here.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-800">
              {facts.map((fact) => (
                <FactItem key={fact.id} fact={fact} onDelete={handleDeleteFact} />
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "summary" && (
        <div>
          {conversationId ? (
            <SummaryCard summary={summary} />
          ) : (
            <div className="card text-center py-8">
              <BookOpen className="w-8 h-8 text-gray-600 mx-auto mb-2" />
              <p className="text-sm text-gray-500">Start a conversation to see summaries here.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

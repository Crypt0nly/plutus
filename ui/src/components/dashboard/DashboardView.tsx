import { useEffect, useState, useCallback } from "react";
import {
  Activity,
  Shield,
  Terminal,
  Clock,
  Brain,
  Users,
  MessageSquare,
  Heart,
  Wifi,
  WifiOff,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  Calendar,
  Layers,
  BarChart3,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import { StatusCard } from "./StatusCard";
import { ActivityFeed } from "./ActivityFeed";

export function DashboardView() {
  const { currentTier, connected } = useAppStore();
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [audit, setAudit] = useState<{ entries: any[]; total: number } | null>(null);
  const [conversations, setConversations] = useState<any[]>([]);
  const [connectors, setConnectors] = useState<Record<string, any> | null>(null);
  const [skills, setSkills] = useState<Record<string, any> | null>(null);
  const [memoryStats, setMemoryStats] = useState<Record<string, any> | null>(null);

  const fetchAll = useCallback(() => {
    api.getStatus().then(setStatus).catch(() => {});
    api.getAudit(20).then(setAudit).catch(() => {});
    api.getConversations(5).then(setConversations).catch(() => {});
    api.getConnectors().then(setConnectors).catch(() => {});
    api.getSkills().then(setSkills).catch(() => {});
    api.getMemoryStats().then(setMemoryStats).catch(() => {});
  }, []);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, 15000);
    return () => clearInterval(timer);
  }, [fetchAll]);

  const auditSummary = status?.guardrails?.audit_summary;
  const workerPool = status?.worker_pool;
  const scheduler = status?.scheduler;
  const heartbeat = status?.heartbeat;
  const toolCount = status?.tools?.length ?? 0;
  const totalActions = auditSummary?.total_entries ?? 0;

  // Count active connectors
  const connectorList = connectors ? Object.values(connectors) : [];
  const activeConnectors = connectorList.filter((c: any) => c?.connected || c?.running).length;

  // Skills count
  const skillCount = skills?.skills?.length ?? (Array.isArray(skills) ? skills.length : 0);

  // Memory
  const factCount = memoryStats?.total_facts ?? memoryStats?.facts ?? 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-100">Dashboard</h2>
            <p className="text-sm text-gray-500 mt-1">
              System overview and real-time metrics
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium ${
              connected
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}>
              {connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {connected ? "Connected" : "Disconnected"}
            </div>
            <span className="text-xs text-gray-600 font-mono bg-gray-800/50 px-2.5 py-1.5 rounded-lg">
              v{status?.version || "0.3.2"}
            </span>
          </div>
        </div>

        {/* Primary Metrics */}
        <div className="grid grid-cols-4 gap-4">
          <StatusCard
            icon={Activity}
            label="System Status"
            value={connected ? "Online" : "Offline"}
            color={connected ? "emerald" : "red"}
          />
          <StatusCard
            icon={Shield}
            label="Guardrail Tier"
            value={currentTier}
            color="plutus"
            capitalize
          />
          <StatusCard
            icon={Terminal}
            label="Tools Available"
            value={String(toolCount)}
            sublabel={`${totalActions} total actions`}
            color="blue"
          />
          <StatusCard
            icon={Users}
            label="Active Workers"
            value={String(workerPool?.active ?? 0)}
            sublabel={`of ${workerPool?.max_workers ?? 5} max`}
            color="purple"
          />
        </div>

        {/* Secondary Metrics Row */}
        <div className="grid grid-cols-5 gap-3">
          {[
            {
              icon: MessageSquare,
              label: "Conversations",
              value: String(conversations?.length ?? 0),
              color: "text-blue-400",
              bg: "bg-blue-500/10",
            },
            {
              icon: Calendar,
              label: "Scheduled Jobs",
              value: String(scheduler?.total_jobs ?? scheduler?.jobs ?? 0),
              color: "text-amber-400",
              bg: "bg-amber-500/10",
            },
            {
              icon: Layers,
              label: "Skills",
              value: String(skillCount),
              color: "text-emerald-400",
              bg: "bg-emerald-500/10",
            },
            {
              icon: Wifi,
              label: "Connectors",
              value: `${activeConnectors}/${connectorList.length}`,
              color: "text-purple-400",
              bg: "bg-purple-500/10",
            },
            {
              icon: Brain,
              label: "Memory Facts",
              value: String(factCount),
              color: "text-rose-400",
              bg: "bg-rose-500/10",
            },
          ].map(({ icon: Icon, label, value, color, bg }) => (
            <div
              key={label}
              className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-3.5 flex items-center gap-3"
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${bg}`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
              <div>
                <p className="text-lg font-bold text-gray-200 leading-none">{value}</p>
                <p className="text-[10px] text-gray-500 mt-0.5">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Middle Section: Action Decisions + Heartbeat */}
        <div className="grid grid-cols-3 gap-4">
          {/* Action Decisions */}
          <div className="col-span-2 bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg bg-blue-500/10 flex items-center justify-center">
                <BarChart3 className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Action Decisions</h3>
                <p className="text-xs text-gray-500">Guardrail outcomes for tool calls</p>
              </div>
            </div>

            {auditSummary?.by_decision ? (
              <div className="space-y-3">
                {[
                  { key: "allowed", label: "Allowed", icon: CheckCircle2, color: "emerald" },
                  { key: "denied", label: "Denied", icon: XCircle, color: "red" },
                  { key: "approved", label: "Approved", icon: CheckCircle2, color: "blue" },
                  { key: "rejected", label: "Rejected", icon: AlertTriangle, color: "amber" },
                ].map(({ key, label, icon: Icon, color }) => {
                  const count = auditSummary.by_decision[key] ?? 0;
                  const total = totalActions || 1;
                  const pct = Math.round((count / total) * 100);
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <Icon className={`w-4 h-4 text-${color}-400 shrink-0`} />
                      <span className="text-sm text-gray-400 w-20">{label}</span>
                      <div className="flex-1 bg-gray-800/50 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full rounded-full bg-${color}-500/60 transition-all`}
                          style={{ width: `${Math.max(pct, count > 0 ? 2 : 0)}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono text-gray-300 w-10 text-right">{count}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8">
                <p className="text-sm text-gray-500">No action data yet</p>
                <p className="text-xs text-gray-600 mt-1">Tool calls will appear here as you use Plutus</p>
              </div>
            )}
          </div>

          {/* Heartbeat + Model Info */}
          <div className="space-y-4">
            {/* Heartbeat mini */}
            <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-4">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-lg bg-rose-500/10 flex items-center justify-center">
                  <Heart className="w-4 h-4 text-rose-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-xs font-semibold text-gray-300">Heartbeat</h3>
                </div>
                {heartbeat?.running ? (
                  <span className="flex items-center gap-1.5 text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Active
                  </span>
                ) : (
                  <span className="text-[10px] text-gray-500 bg-gray-500/10 px-2 py-0.5 rounded-full">Off</span>
                )}
              </div>
              {heartbeat?.running && (
                <div className="text-xs text-gray-500 space-y-1">
                  <div className="flex justify-between">
                    <span>Beats</span>
                    <span className="text-gray-300">{heartbeat.consecutive_beats}/{heartbeat.max_consecutive}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Interval</span>
                    <span className="text-gray-300">{heartbeat.interval_seconds < 60 ? `${heartbeat.interval_seconds}s` : `${Math.floor(heartbeat.interval_seconds / 60)}m`}</span>
                  </div>
                </div>
              )}
              {!heartbeat?.running && (
                <p className="text-xs text-gray-600">Configure in Settings to enable autonomous operation</p>
              )}
            </div>

            {/* Coordinator Model */}
            <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-4">
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-lg bg-plutus-500/10 flex items-center justify-center">
                  <Brain className="w-4 h-4 text-plutus-400" />
                </div>
                <h3 className="text-xs font-semibold text-gray-300">Coordinator</h3>
              </div>
              <div className="text-xs text-gray-500 space-y-1">
                <div className="flex justify-between">
                  <span>Model</span>
                  <span className="text-gray-300 font-mono text-[10px]">{status?.model_routing?.default_worker_model || "claude-sonnet-4-6"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Planner</span>
                  <span className={`${status?.planner_enabled ? "text-emerald-400" : "text-gray-500"}`}>
                    {status?.planner_enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tool Usage */}
        {auditSummary?.by_tool && Object.keys(auditSummary.by_tool).length > 0 && (
          <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <Terminal className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-gray-200">Tool Usage</h3>
                <p className="text-xs text-gray-500">Distribution of tool calls</p>
              </div>
              <span className="text-xs text-gray-600 bg-gray-800/50 px-2.5 py-1 rounded-full">
                {Object.keys(auditSummary.by_tool).length} tools used
              </span>
            </div>
            <div className="space-y-2.5">
              {Object.entries(auditSummary.by_tool as Record<string, number>)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 10)
                .map(([tool, count]) => {
                  const maxCount = Math.max(
                    ...Object.values(auditSummary.by_tool as Record<string, number>)
                  );
                  const width = (count / maxCount) * 100;
                  return (
                    <div key={tool} className="flex items-center gap-3">
                      <span className="text-sm text-gray-400 w-28 truncate font-mono text-xs">{tool}</span>
                      <div className="flex-1 bg-gray-800/50 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-plutus-500/80 to-plutus-400/60 rounded-full h-2 transition-all"
                          style={{ width: `${width}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-400 font-mono w-10 text-right">
                        {count}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* Recent Activity */}
        <ActivityFeed entries={audit?.entries ?? []} />
      </div>
    </div>
  );
}

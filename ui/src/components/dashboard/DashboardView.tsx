import { useState, useEffect, useCallback } from "react";
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
  RefreshCw,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import { StatusCard } from "./StatusCard";
import { ActivityFeed } from "./ActivityFeed";

const cardStyle = {
  background: "rgba(15, 18, 30, 0.8)",
  border: "1px solid rgba(255, 255, 255, 0.06)",
};

export function DashboardView() {
  const { currentTier, connected } = useAppStore();
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [audit, setAudit] = useState<{ entries: any[]; total: number } | null>(null);
  const [conversations, setConversations] = useState<any[]>([]);
  const [connectors, setConnectors] = useState<Record<string, any> | null>(null);
  const [skills, setSkills] = useState<Record<string, any> | null>(null);
  const [memoryStats, setMemoryStats] = useState<Record<string, any> | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAll = useCallback(async () => {
    if (!connected) return;
    setRefreshing(true);
    await Promise.allSettled([
      api.getStatus().then(setStatus).catch(() => {}),
      api.getAudit(20).then((d) => {
        if (d && !Array.isArray(d.entries)) d.entries = [];
        setAudit(d);
      }).catch(() => {}),
      api.getConversations(5).then(setConversations).catch(() => {}),
      api.getConnectors().then(setConnectors).catch(() => {}),
      api.getSkills().then(setSkills).catch(() => {}),
      api.getMemoryStats().then(setMemoryStats).catch(() => {}),
    ]);
    setRefreshing(false);
  }, [connected]);

  useEffect(() => {
    fetchAll();
    if (!connected) return;
    const timer = setInterval(fetchAll, 15000);
    return () => clearInterval(timer);
  }, [fetchAll, connected]);

  const auditSummary = status?.guardrails?.audit_summary;
  const workerPool = status?.worker_pool;
  const scheduler = status?.scheduler;
  const heartbeat = status?.heartbeat;
  const toolCount = status?.tools?.length ?? 0;
  const totalActions = auditSummary?.total_entries ?? 0;

  const connectorList = connectors ? Object.values(connectors) : [];
  const activeConnectors = connectorList.filter((c: any) => c?.connected || c?.running).length;
  const skillCount = skills?.skills?.length ?? (Array.isArray(skills) ? skills.length : 0);
  const factCount = memoryStats?.total_facts ?? memoryStats?.facts ?? 0;

  const secondaryMetrics = [
    { icon: MessageSquare, label: "Conversations", value: String(conversations?.length ?? 0), iconColor: "#60a5fa", bg: "rgba(59, 130, 246, 0.08)", border: "rgba(59, 130, 246, 0.12)" },
    { icon: Calendar, label: "Scheduled Jobs", value: String(scheduler?.total_jobs ?? scheduler?.jobs ?? 0), iconColor: "#fbbf24", bg: "rgba(245, 158, 11, 0.08)", border: "rgba(245, 158, 11, 0.12)" },
    { icon: Layers, label: "Skills", value: String(skillCount), iconColor: "#34d399", bg: "rgba(16, 185, 129, 0.08)", border: "rgba(16, 185, 129, 0.12)" },
    { icon: Wifi, label: "Connectors", value: `${activeConnectors}/${connectorList.length}`, iconColor: "#c084fc", bg: "rgba(168, 85, 247, 0.08)", border: "rgba(168, 85, 247, 0.12)" },
    { icon: Brain, label: "Memory Facts", value: String(factCount), iconColor: "#fb7185", bg: "rgba(244, 63, 94, 0.08)", border: "rgba(244, 63, 94, 0.12)" },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div>
            <h2 className="text-xl font-bold text-gray-100 tracking-tight">System Overview</h2>
            <p className="text-sm text-gray-500 mt-0.5">Real-time metrics and activity</p>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={fetchAll}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-gray-400 hover:text-gray-200 transition-all"
              style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              <RefreshCw className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium"
              style={connected ? {
                background: "rgba(16, 185, 129, 0.08)",
                color: "#34d399",
                border: "1px solid rgba(16, 185, 129, 0.15)"
              } : {
                background: "rgba(239, 68, 68, 0.08)",
                color: "#f87171",
                border: "1px solid rgba(239, 68, 68, 0.15)"
              }}
            >
              {connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {connected ? "Connected" : "Disconnected"}
            </div>
            <span className="text-xs text-gray-600 font-mono px-2.5 py-1.5 rounded-xl"
              style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              v{status?.version || "—"}
            </span>
          </div>
        </div>

        {/* Primary Metrics */}
        <div className="grid grid-cols-4 gap-3">
          <StatusCard icon={Activity} label="System Status" value={connected ? "Online" : "Offline"} color={connected ? "emerald" : "red"} />
          <StatusCard icon={Shield} label="Guardrail Tier" value={currentTier} color="plutus" capitalize />
          <StatusCard icon={Terminal} label="Tools Available" value={String(toolCount)} sublabel={`${totalActions} total actions`} color="blue" />
          <StatusCard icon={Users} label="Active Workers" value={String(workerPool?.active ?? 0)} sublabel={`of ${workerPool?.max_workers ?? 5} max`} color="purple" />
        </div>

        {/* Secondary Metrics */}
        <div className="grid grid-cols-5 gap-3">
          {secondaryMetrics.map(({ icon: Icon, label, value, iconColor, bg, border }) => (
            <div key={label} className="rounded-2xl p-3.5 flex items-center gap-3" style={cardStyle}>
              <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: bg, border: `1px solid ${border}` }}
              >
                <Icon className="w-4 h-4" style={{ color: iconColor }} />
              </div>
              <div>
                <p className="text-lg font-bold text-gray-200 leading-none">{value}</p>
                <p className="text-[10px] text-gray-500 mt-0.5">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Middle Section */}
        <div className="grid grid-cols-3 gap-4">
          {/* Action Decisions */}
          <div className="col-span-2 rounded-2xl p-5" style={cardStyle}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: "rgba(59, 130, 246, 0.08)", border: "1px solid rgba(59, 130, 246, 0.12)" }}
              >
                <BarChart3 className="w-4.5 h-4.5 text-blue-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">Action Decisions</h3>
                <p className="text-xs text-gray-500">Guardrail outcomes for tool calls</p>
              </div>
            </div>

            {auditSummary?.by_decision ? (
              <div className="space-y-3">
                {[
                  { key: "allowed", label: "Allowed", icon: CheckCircle2, barColor: "#34d399", trackColor: "rgba(16, 185, 129, 0.1)" },
                  { key: "denied", label: "Denied", icon: XCircle, barColor: "#f87171", trackColor: "rgba(239, 68, 68, 0.1)" },
                  { key: "approved", label: "Approved", icon: CheckCircle2, barColor: "#60a5fa", trackColor: "rgba(59, 130, 246, 0.1)" },
                  { key: "rejected", label: "Rejected", icon: AlertTriangle, barColor: "#fbbf24", trackColor: "rgba(245, 158, 11, 0.1)" },
                ].map(({ key, label, icon: Icon, barColor, trackColor }) => {
                  const count = auditSummary.by_decision[key] ?? 0;
                  const total = totalActions || 1;
                  const pct = Math.round((count / total) * 100);
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <Icon className="w-4 h-4 shrink-0" style={{ color: barColor }} />
                      <span className="text-sm text-gray-400 w-20">{label}</span>
                      <div className="flex-1 rounded-full h-1.5 overflow-hidden" style={{ background: trackColor }}>
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${Math.max(pct, count > 0 ? 2 : 0)}%`, background: barColor }}
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
                <p className="text-xs text-gray-700 mt-1">Tool calls will appear here as you use Plutus</p>
              </div>
            )}
          </div>

          {/* Right column */}
          <div className="space-y-3">
            {/* Heartbeat */}
            <div className="rounded-2xl p-4" style={cardStyle}>
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-xl flex items-center justify-center"
                  style={{ background: "rgba(244, 63, 94, 0.08)", border: "1px solid rgba(244, 63, 94, 0.12)" }}
                >
                  <Heart className="w-4 h-4 text-rose-400" />
                </div>
                <div className="flex-1">
                  <h3 className="text-xs font-semibold text-gray-300">Heartbeat</h3>
                </div>
                {heartbeat?.running ? (
                  <span className="flex items-center gap-1.5 text-[10px] text-emerald-400 px-2 py-0.5 rounded-full"
                    style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.12)" }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Active
                  </span>
                ) : (
                  <span className="text-[10px] text-gray-500 px-2 py-0.5 rounded-full"
                    style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >Off</span>
                )}
              </div>
              {heartbeat?.running ? (
                <div className="text-xs text-gray-500 space-y-1.5">
                  <div className="flex justify-between">
                    <span>Beats</span>
                    <span className="text-gray-300">{heartbeat.consecutive_beats}/{heartbeat.max_consecutive}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Interval</span>
                    <span className="text-gray-300">
                      {heartbeat.interval_seconds < 60 ? `${heartbeat.interval_seconds}s` : `${Math.floor(heartbeat.interval_seconds / 60)}m`}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-gray-700">Configure in Settings to enable autonomous operation</p>
              )}
            </div>

            {/* Coordinator Model */}
            <div className="rounded-2xl p-4" style={cardStyle}>
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-8 h-8 rounded-xl flex items-center justify-center"
                  style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.12)" }}
                >
                  <Brain className="w-4 h-4 text-indigo-400" />
                </div>
                <h3 className="text-xs font-semibold text-gray-300">Coordinator</h3>
              </div>
              <div className="text-xs text-gray-500 space-y-1.5">
                <div className="flex justify-between">
                  <span>Model</span>
                  <span className="text-gray-300 font-mono text-[10px]">{status?.model_routing?.default_worker_model || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span>Planner</span>
                  <span className={status?.planner_enabled ? "text-emerald-400" : "text-gray-500"}>
                    {status?.planner_enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tool Usage */}
        {auditSummary?.by_tool && Object.keys(auditSummary.by_tool).length > 0 && (
          <div className="rounded-2xl p-5" style={cardStyle}>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.12)" }}
              >
                <Terminal className="w-4.5 h-4.5 text-emerald-400" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-gray-200">Tool Usage</h3>
                <p className="text-xs text-gray-500">Distribution of tool calls</p>
              </div>
              <span className="text-[11px] text-gray-500 px-2.5 py-1 rounded-full"
                style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgba(255,255,255,0.06)" }}
              >
                {Object.keys(auditSummary.by_tool).length} tools used
              </span>
            </div>
            <div className="space-y-2.5">
              {Object.entries(auditSummary.by_tool as Record<string, number>)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 10)
                .map(([tool, count]) => {
                  const maxCount = Math.max(...Object.values(auditSummary.by_tool as Record<string, number>));
                  const width = (count / maxCount) * 100;
                  return (
                    <div key={tool} className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-28 truncate font-mono">{tool}</span>
                      <div className="flex-1 rounded-full h-1.5 overflow-hidden"
                        style={{ background: "rgba(99, 102, 241, 0.08)" }}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${width}%`,
                            background: "linear-gradient(90deg, #6366f1, #818cf8)"
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-400 font-mono w-10 text-right">{count}</span>
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

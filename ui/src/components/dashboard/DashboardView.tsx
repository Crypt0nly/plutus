import { useEffect, useState } from "react";
import {
  Shield,
  Terminal,
  Activity,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import { StatusCard } from "./StatusCard";
import { ActivityFeed } from "./ActivityFeed";

export function DashboardView() {
  const { currentTier, connected } = useAppStore();
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [audit, setAudit] = useState<{ entries: any[]; total: number } | null>(null);

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => {});
    api.getAudit(20).then(setAudit).catch(() => {});
  }, []);

  const auditSummary = status?.guardrails?.audit_summary;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-100 mb-1">Dashboard</h2>
        <p className="text-sm text-gray-500">
          System overview and recent activity
        </p>
      </div>

      {/* Status cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatusCard
          icon={Activity}
          label="Status"
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
          value={String(status?.tools?.length ?? 0)}
          color="blue"
        />
        <StatusCard
          icon={Clock}
          label="Total Actions"
          value={String(auditSummary?.total_entries ?? 0)}
          color="gray"
        />
      </div>

      {/* Decision breakdown */}
      {auditSummary?.by_decision && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">
            Action Decisions
          </h3>
          <div className="grid grid-cols-4 gap-4">
            {[
              {
                key: "allowed",
                label: "Allowed",
                icon: CheckCircle2,
                color: "text-emerald-400",
              },
              {
                key: "denied",
                label: "Denied",
                icon: XCircle,
                color: "text-red-400",
              },
              {
                key: "approved",
                label: "Approved",
                icon: CheckCircle2,
                color: "text-blue-400",
              },
              {
                key: "rejected",
                label: "Rejected",
                icon: AlertTriangle,
                color: "text-amber-400",
              },
            ].map(({ key, label, icon: Icon, color }) => (
              <div key={key} className="flex items-center gap-3">
                <Icon className={`w-5 h-5 ${color}`} />
                <div>
                  <p className="text-lg font-bold text-gray-200">
                    {auditSummary.by_decision[key] ?? 0}
                  </p>
                  <p className="text-xs text-gray-500">{label}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool usage */}
      {auditSummary?.by_tool && Object.keys(auditSummary.by_tool).length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">
            Tool Usage
          </h3>
          <div className="space-y-2">
            {Object.entries(auditSummary.by_tool as Record<string, number>)
              .sort(([, a], [, b]) => b - a)
              .map(([tool, count]) => {
                const maxCount = Math.max(
                  ...Object.values(auditSummary.by_tool as Record<string, number>)
                );
                const width = (count / maxCount) * 100;
                return (
                  <div key={tool} className="flex items-center gap-3">
                    <span className="text-sm text-gray-400 w-24">{tool}</span>
                    <div className="flex-1 bg-gray-800 rounded-full h-2">
                      <div
                        className="bg-plutus-500 rounded-full h-2 transition-all"
                        style={{ width: `${width}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-8 text-right">
                      {count}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Recent activity */}
      <ActivityFeed entries={audit?.entries ?? []} />
    </div>
  );
}

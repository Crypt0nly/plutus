import { CheckCircle2, XCircle, Clock, Shield, AlertTriangle, Zap } from "lucide-react";

interface Props {
  entries: Record<string, any>[];
}

const decisionConfig: Record<
  string,
  { icon: React.ElementType; iconColor: string; bg: string; border: string; label: string }
> = {
  allowed: { icon: CheckCircle2, iconColor: "#34d399", bg: "rgba(16, 185, 129, 0.08)", border: "rgba(16, 185, 129, 0.12)", label: "Allowed" },
  denied: { icon: XCircle, iconColor: "#f87171", bg: "rgba(239, 68, 68, 0.08)", border: "rgba(239, 68, 68, 0.12)", label: "Denied" },
  pending_approval: { icon: Clock, iconColor: "#fbbf24", bg: "rgba(245, 158, 11, 0.08)", border: "rgba(245, 158, 11, 0.12)", label: "Pending" },
  approved: { icon: CheckCircle2, iconColor: "#60a5fa", bg: "rgba(59, 130, 246, 0.08)", border: "rgba(59, 130, 246, 0.12)", label: "Approved" },
  rejected: { icon: Shield, iconColor: "#f87171", bg: "rgba(239, 68, 68, 0.08)", border: "rgba(239, 68, 68, 0.12)", label: "Rejected" },
};

function timeAgo(timestamp: number): string {
  const now = Date.now() / 1000;
  const diff = now - timestamp;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

const cardStyle = {
  background: "rgba(15, 18, 30, 0.8)",
  border: "1px solid rgba(255, 255, 255, 0.06)",
};

export function ActivityFeed({ entries: rawEntries }: Props) {
  const entries = Array.isArray(rawEntries) ? rawEntries : [];

  if (entries.length === 0) {
    return (
      <div className="rounded-2xl p-5" style={cardStyle}>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(107, 114, 128, 0.08)", border: "1px solid rgba(107, 114, 128, 0.12)" }}
          >
            <Zap className="w-4.5 h-4.5 text-gray-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Recent Activity</h3>
            <p className="text-xs text-gray-500">Tool calls and system events</p>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-10">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
            style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgb(var(--gray-700) / 0.3)" }}
          >
            <Zap className="w-5 h-5 text-gray-700" />
          </div>
          <p className="text-sm text-gray-500">No activity yet</p>
          <p className="text-xs text-gray-700 mt-1">Start a conversation to see actions here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl p-5" style={cardStyle}>
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: "rgba(107, 114, 128, 0.08)", border: "1px solid rgba(107, 114, 128, 0.12)" }}
        >
          <Zap className="w-4.5 h-4.5 text-gray-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-200">Recent Activity</h3>
          <p className="text-xs text-gray-500">Last {Math.min(entries.length, 10)} tool calls</p>
        </div>
        <span className="text-[11px] text-gray-500 px-2.5 py-1 rounded-full"
          style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          {entries.length} total
        </span>
      </div>
      <div className="space-y-1">
        {entries.slice(0, 10).map((entry, i) => {
          const config = decisionConfig[entry.decision] || decisionConfig.allowed;
          const Icon = config.icon;

          return (
            <div
              key={entry.id || i}
              className="flex items-center gap-3 py-2.5 px-3 rounded-xl transition-all duration-150 group cursor-default"
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.03)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = "";
              }}
            >
              <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: config.bg, border: `1px solid ${config.border}` }}
              >
                <Icon className="w-3.5 h-3.5" style={{ color: config.iconColor }} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-300">{entry.tool_name}</span>
                  {entry.operation && (
                    <span className="text-xs text-gray-600 font-mono">.{entry.operation}</span>
                  )}
                </div>
                {entry.reason && (
                  <p className="text-xs text-gray-600 truncate mt-0.5">{entry.reason}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[10px] px-1.5 py-0.5 rounded-md font-medium"
                  style={{ background: config.bg, color: config.iconColor, border: `1px solid ${config.border}` }}
                >
                  {config.label}
                </span>
                <span className="text-[10px] text-gray-700">{timeAgo(entry.timestamp)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

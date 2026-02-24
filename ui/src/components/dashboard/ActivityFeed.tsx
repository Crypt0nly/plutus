import { CheckCircle2, XCircle, Clock, Shield, AlertTriangle, Zap } from "lucide-react";

interface Props {
  entries: Record<string, any>[];
}

const decisionConfig: Record<
  string,
  { icon: React.ElementType; color: string; bg: string; label: string }
> = {
  allowed: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10", label: "Allowed" },
  denied: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", label: "Denied" },
  pending_approval: { icon: Clock, color: "text-amber-400", bg: "bg-amber-500/10", label: "Pending" },
  approved: { icon: CheckCircle2, color: "text-blue-400", bg: "bg-blue-500/10", label: "Approved" },
  rejected: { icon: Shield, color: "text-red-400", bg: "bg-red-500/10", label: "Rejected" },
};

function timeAgo(timestamp: number): string {
  const now = Date.now() / 1000;
  const diff = now - timestamp;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

export function ActivityFeed({ entries }: Props) {
  if (entries.length === 0) {
    return (
      <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded-lg bg-gray-500/10 flex items-center justify-center">
            <Zap className="w-5 h-5 text-gray-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">Recent Activity</h3>
            <p className="text-xs text-gray-500">Tool calls and system events</p>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-10">
          <div className="w-12 h-12 rounded-full bg-gray-800/50 flex items-center justify-center mb-3">
            <Zap className="w-6 h-6 text-gray-600" />
          </div>
          <p className="text-sm text-gray-500">No activity yet</p>
          <p className="text-xs text-gray-600 mt-1">Start a conversation to see actions here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a2e] rounded-xl border border-gray-800/60 p-5">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-lg bg-gray-500/10 flex items-center justify-center">
          <Zap className="w-5 h-5 text-gray-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-200">Recent Activity</h3>
          <p className="text-xs text-gray-500">Last {Math.min(entries.length, 10)} tool calls</p>
        </div>
        <span className="text-xs text-gray-600 bg-gray-800/50 px-2.5 py-1 rounded-full">
          {entries.length} total
        </span>
      </div>
      <div className="space-y-1">
        {entries.slice(0, 10).map((entry, i) => {
          const config =
            decisionConfig[entry.decision] || decisionConfig.allowed;
          const Icon = config.icon;

          return (
            <div
              key={entry.id || i}
              className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-gray-800/30 transition-colors group"
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${config.bg}`}
              >
                <Icon className={`w-3.5 h-3.5 ${config.color}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-300">
                    {entry.tool_name}
                  </span>
                  {entry.operation && (
                    <span className="text-xs text-gray-500 font-mono">
                      .{entry.operation}
                    </span>
                  )}
                </div>
                {entry.reason && (
                  <p className="text-xs text-gray-500 truncate mt-0.5">{entry.reason}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${config.bg} ${config.color}`}>
                  {config.label}
                </span>
                <span className="text-[10px] text-gray-600">
                  {timeAgo(entry.timestamp)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

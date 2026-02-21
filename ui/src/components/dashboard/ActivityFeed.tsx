import { CheckCircle2, XCircle, Clock, Shield } from "lucide-react";

interface Props {
  entries: Record<string, any>[];
}

const decisionConfig: Record<
  string,
  { icon: React.ElementType; color: string; bg: string }
> = {
  allowed: { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500/10" },
  denied: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10" },
  pending_approval: { icon: Clock, color: "text-amber-400", bg: "bg-amber-500/10" },
  approved: { icon: CheckCircle2, color: "text-blue-400", bg: "bg-blue-500/10" },
  rejected: { icon: Shield, color: "text-red-400", bg: "bg-red-500/10" },
};

export function ActivityFeed({ entries }: Props) {
  if (entries.length === 0) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">
          Recent Activity
        </h3>
        <p className="text-sm text-gray-500 text-center py-8">
          No activity yet. Start a conversation to see actions here.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        Recent Activity
      </h3>
      <div className="space-y-3">
        {entries.slice(0, 10).map((entry, i) => {
          const config =
            decisionConfig[entry.decision] || decisionConfig.allowed;
          const Icon = config.icon;
          const time = new Date(entry.timestamp * 1000).toLocaleTimeString();

          return (
            <div
              key={entry.id || i}
              className="flex items-start gap-3 py-2 border-b border-gray-800 last:border-b-0"
            >
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${config.bg}`}
              >
                <Icon className={`w-3.5 h-3.5 ${config.color}`} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-300">
                    {entry.tool_name}
                  </span>
                  {entry.operation && (
                    <span className="text-xs text-gray-500">
                      .{entry.operation}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500 truncate">{entry.reason}</p>
              </div>
              <span className="text-xs text-gray-600 flex-shrink-0">
                {time}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

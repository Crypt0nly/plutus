import { Shield, Activity, Key, Loader2 } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const viewTitles: Record<string, { title: string; subtitle: string }> = {
  chat: { title: "Chat", subtitle: "Talk to Plutus" },
  dashboard: { title: "Dashboard", subtitle: "Activity overview" },
  guardrails: { title: "Guardrails", subtitle: "Safety & permissions" },
  settings: { title: "Settings", subtitle: "Configuration" },
  tools: { title: "Tools", subtitle: "Agent capabilities" },
  workers: { title: "Workers & Automation", subtitle: "Workers, schedules & model routing" },
  "tool-creator": { title: "Tool Creator", subtitle: "Build custom tools" },
  skills: { title: "Skills", subtitle: "Browse, import, and share skills" },
  memory: { title: "Memory & Plans", subtitle: "What Plutus remembers" },
  connectors: { title: "Connectors", subtitle: "Link Plutus with external apps" },
};

const tierColors: Record<string, { bg: string; text: string; dot: string }> = {
  observer: { bg: "rgba(107, 114, 128, 0.12)", text: "text-gray-400", dot: "bg-gray-500" },
  assistant: { bg: "rgba(99, 102, 241, 0.12)", text: "text-indigo-400", dot: "bg-indigo-500" },
  operator: { bg: "rgba(245, 158, 11, 0.12)", text: "text-amber-400", dot: "bg-amber-500" },
  autonomous: { bg: "rgba(239, 68, 68, 0.12)", text: "text-red-400", dot: "bg-red-500" },
};

export function Header() {
  const { view, currentTier, pendingApprovals, isProcessing, keyConfigured } =
    useAppStore();

  const viewInfo = viewTitles[view] || { title: "Plutus", subtitle: "" };
  const tierStyle = tierColors[currentTier] || tierColors.assistant;

  return (
    <header
      className="h-14 flex items-center justify-between px-6 flex-shrink-0 bg-gray-950/80 backdrop-blur-xl border-b border-gray-700/30"
      style={{
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
    >
      {/* Left: View title */}
      <div className="flex items-center gap-3">
        <div>
          <h2 className="text-[13px] font-semibold text-gray-100 leading-none tracking-tight dark:text-gray-100">
            {viewInfo.title}
          </h2>
          {viewInfo.subtitle && (
            <p className="text-[11px] text-gray-400 mt-0.5 leading-none">{viewInfo.subtitle}</p>
          )}
        </div>
      </div>

      {/* Right: Status indicators */}
      <div className="flex items-center gap-2">
        {/* Missing API key warning */}
        {!keyConfigured && (
          <button
            onClick={() => useAppStore.getState().setView("settings")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all animate-gentle-pulse"
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              color: "#fbbf24",
              border: "1px solid rgba(245, 158, 11, 0.2)"
            }}
          >
            <Key className="w-3 h-3" />
            Configure API key
          </button>
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
            style={{
              background: "rgba(99, 102, 241, 0.08)",
              border: "1px solid rgba(99, 102, 241, 0.15)"
            }}
          >
            <Loader2 className="w-3 h-3 text-plutus-400 animate-spin" />
            <span className="text-plutus-400 font-medium">Processing</span>
          </div>
        )}

        {/* Pending approvals badge */}
        {pendingApprovals.length > 0 && (
          <button
            onClick={() => useAppStore.getState().setView("chat")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium animate-gentle-pulse"
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              color: "#fbbf24",
              border: "1px solid rgba(245, 158, 11, 0.2)"
            }}
          >
            <Shield className="w-3 h-3" />
            {pendingApprovals.length} pending
          </button>
        )}

        {/* Tier badge */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium ${tierStyle.text}`}
          style={{ background: tierStyle.bg, border: "1px solid rgba(128,128,128,0.15)" }}
        >
          <div className={`w-1.5 h-1.5 rounded-full ${tierStyle.dot}`} />
          <span className="capitalize">{currentTier}</span>
        </div>
      </div>
    </header>
  );
}

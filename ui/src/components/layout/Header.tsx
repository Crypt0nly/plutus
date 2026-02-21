import { Shield, Activity, Key } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const viewTitles: Record<string, { title: string; subtitle: string }> = {
  chat: { title: "Chat", subtitle: "Talk to your AI agent" },
  dashboard: { title: "Dashboard", subtitle: "Activity overview" },
  guardrails: { title: "Guardrails", subtitle: "Safety & permissions" },
  settings: { title: "Settings", subtitle: "Configuration" },
  tools: { title: "Tools", subtitle: "Agent capabilities" },
  workers: { title: "Workers", subtitle: "Subprocess monitor" },
  "tool-creator": { title: "Tool Creator", subtitle: "Build custom tools" },
  "pc-control": { title: "Computer Use", subtitle: "Plutus sees your screen, clicks, types, and controls your PC" },
};

export function Header() {
  const { view, currentTier, pendingApprovals, isProcessing, keyConfigured } =
    useAppStore();

  const viewInfo = viewTitles[view] || { title: "Plutus", subtitle: "" };

  return (
    <header className="h-14 border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm flex items-center justify-between px-6">
      <div>
        <h2 className="text-sm font-semibold text-gray-200">
          {viewInfo.title}
        </h2>
        {viewInfo.subtitle && (
          <p className="text-[10px] text-gray-500 -mt-0.5">{viewInfo.subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Missing API key warning */}
        {!keyConfigured && (
          <button
            onClick={() => useAppStore.getState().setView("settings")}
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium animate-gentle-pulse"
          >
            <Key className="w-3 h-3" />
            No API key — click to configure
          </button>
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <div className="flex items-center gap-2 text-xs text-plutus-400">
            <Activity className="w-3.5 h-3.5 animate-pulse" />
            <span>Processing...</span>
          </div>
        )}

        {/* Pending approvals badge */}
        {pendingApprovals.length > 0 && (
          <button
            onClick={() => useAppStore.getState().setView("chat")}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium animate-gentle-pulse"
          >
            <Shield className="w-3 h-3" />
            {pendingApprovals.length} pending
          </button>
        )}

        {/* Tier badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-800 text-xs">
          <Shield className="w-3 h-3 text-plutus-400" />
          <span className="text-gray-300 capitalize">{currentTier}</span>
        </div>
      </div>
    </header>
  );
}

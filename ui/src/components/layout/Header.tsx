import { Shield, Activity } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const viewTitles: Record<string, string> = {
  chat: "Chat",
  dashboard: "Dashboard",
  guardrails: "Guardrails",
  settings: "Settings",
};

export function Header() {
  const { view, currentTier, pendingApprovals, isProcessing } = useAppStore();

  return (
    <header className="h-14 border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm flex items-center justify-between px-6">
      <h2 className="text-sm font-semibold text-gray-200">
        {viewTitles[view] || "Plutus"}
      </h2>

      <div className="flex items-center gap-4">
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

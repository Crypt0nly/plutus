import { Shield, Loader2, Key, Menu } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

const viewTitles: Record<string, string> = {
  chat: "Chat",
  sessions: "Sessions",
  dashboard: "Dashboard",
  guardrails: "Guardrails",
  settings: "Settings",
  tools: "Tools",
  workers: "Workers",
  "tool-creator": "Tool Creator",
  skills: "Skills",
  memory: "Memory",
  connectors: "Connectors",
};

interface MobileHeaderProps {
  onMenuOpen: () => void;
}

export function MobileHeader({ onMenuOpen }: MobileHeaderProps) {
  const { view, currentTier, pendingApprovals, isProcessing, keyConfigured, connected } =
    useAppStore();

  const title = viewTitles[view] || "Plutus";

  return (
    <header
      className="h-14 flex items-center justify-between px-4 flex-shrink-0"
      style={{
        background: "rgba(9, 9, 11, 0.95)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        paddingTop: "env(safe-area-inset-top)",
      }}
    >
      {/* Left: Logo + Title */}
      <div className="flex items-center gap-3">
        <div className="relative flex-shrink-0">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs text-white"
            style={{
              background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
              boxShadow: "0 2px 8px rgba(99,102,241,0.4)",
            }}
          >
            P
          </div>
          <span
            className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border-2 border-gray-950 ${
              connected ? "bg-emerald-400" : "bg-red-400"
            }`}
          />
        </div>
        <h2 className="text-[15px] font-semibold text-gray-100 tracking-tight">
          {title}
        </h2>
      </div>

      {/* Right: status + menu */}
      <div className="flex items-center gap-2">
        {/* Missing API key warning */}
        {!keyConfigured && (
          <button
            onClick={() => useAppStore.getState().setView("settings")}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium"
            style={{
              background: "rgba(245,158,11,0.1)",
              color: "#fbbf24",
              border: "1px solid rgba(245,158,11,0.2)",
            }}
          >
            <Key className="w-3 h-3" />
            API Key
          </button>
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <div
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px]"
            style={{
              background: "rgba(99,102,241,0.08)",
              border: "1px solid rgba(99,102,241,0.15)",
            }}
          >
            <Loader2 className="w-3 h-3 text-indigo-400 animate-spin" />
            <span className="text-indigo-400 font-medium">Working</span>
          </div>
        )}

        {/* Pending approvals */}
        {pendingApprovals.length > 0 && (
          <button
            onClick={() => useAppStore.getState().setView("chat")}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium"
            style={{
              background: "rgba(245,158,11,0.1)",
              color: "#fbbf24",
              border: "1px solid rgba(245,158,11,0.2)",
            }}
          >
            <Shield className="w-3 h-3" />
            {pendingApprovals.length}
          </button>
        )}

        {/* Tier badge */}
        <div
          className="px-2 py-1 rounded-lg text-[10px] font-medium capitalize text-indigo-400"
          style={{
            background: "rgba(99,102,241,0.1)",
            border: "1px solid rgba(99,102,241,0.15)",
          }}
        >
          {currentTier}
        </div>

        {/* Menu button (opens full nav drawer) */}
        <button
          onClick={onMenuOpen}
          className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors active:scale-95"
          style={{ background: "rgba(255,255,255,0.05)" }}
        >
          <Menu className="w-4.5 h-4.5 text-gray-400" />
        </button>
      </div>
    </header>
  );
}

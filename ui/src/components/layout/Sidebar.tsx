import {
  MessageSquare,
  LayoutDashboard,
  Shield,
  Settings,
  Plus,
  Wrench,
  Cpu,
  Sparkles,
  Monitor,
  Brain,
} from "lucide-react";
import { useAppStore, type View } from "../../stores/appStore";

interface NavSection {
  label: string;
  items: { id: View; label: string; icon: React.ElementType; badge?: string; primary?: boolean }[];
}

const navSections: NavSection[] = [
  {
    label: "Main",
    items: [
      { id: "chat", label: "Chat", icon: MessageSquare },
      { id: "pc-control", label: "Computer Use", icon: Monitor, primary: true },
      { id: "skills", label: "Skills", icon: Brain, badge: "New" },
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    ],
  },
  {
    label: "Agent",
    items: [
      { id: "memory", label: "Memory & Plans", icon: Brain, badge: "New" },
      { id: "tools", label: "Tools", icon: Wrench },
      { id: "workers", label: "Workers", icon: Cpu },
      { id: "tool-creator", label: "Tool Creator", icon: Sparkles },
    ],
  },
  {
    label: "System",
    items: [
      { id: "guardrails", label: "Guardrails", icon: Shield },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const { view, setView, connected, currentTier } = useAppStore();

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="p-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-plutus-500 to-plutus-700 flex items-center justify-center font-bold text-lg shadow-lg shadow-plutus-500/20">
            P
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none">Plutus</h1>
            <p className="text-xs text-gray-500 mt-0.5">v0.2.0</p>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className="px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-emerald-500 shadow-sm shadow-emerald-500/50" : "bg-red-500"
            }`}
          />
          <span className="text-gray-400">
            {connected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs mt-1.5">
          <Shield className="w-3 h-3 text-gray-500" />
          <span className="text-gray-400 capitalize">{currentTier} mode</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.label}>
            <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider px-3 mb-1.5">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const active = view === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setView(item.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                      active
                        ? item.primary
                          ? "bg-blue-600/20 text-blue-400 shadow-sm shadow-blue-500/10"
                          : "bg-plutus-600/20 text-plutus-400 shadow-sm"
                        : item.primary
                        ? "text-blue-400/70 hover:text-blue-300 hover:bg-blue-900/20"
                        : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span className="flex-1 text-left">{item.label}</span>
                    {item.badge && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-plutus-500/20 text-plutus-400 font-semibold">
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Latest Update */}
      <div className="px-3 pb-2">
        <div className="rounded-lg bg-plutus-500/10 border border-plutus-500/20 px-3 py-2">
          <p className="text-[9px] font-semibold text-plutus-400 uppercase tracking-wider">Latest Update</p>
          <p className="text-xs text-gray-300 mt-0.5 font-medium">Snapshot + Ref Navigation</p>
          <p className="text-[10px] text-gray-500 mt-0.5">v0.2.2 · Feb 22, 2026</p>
        </div>
      </div>

      {/* New Chat button */}
      <div className="p-3 border-t border-gray-800">
        <button
          onClick={() => {
            useAppStore.getState().clearMessages();
            useAppStore.getState().setConversationId(null);
            setView("chat");
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg
                     bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>
    </aside>
  );
}

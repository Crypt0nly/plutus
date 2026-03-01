import { useState } from "react";
import {
  MessageSquare,
  LayoutDashboard,
  Shield,
  Settings,
  Plus,
  Wrench,
  Cpu,
  Sparkles,
  Brain,
  Plug,
  ChevronDown,
  ChevronRight,
  History,
} from "lucide-react";
import { useAppStore, type View } from "../../stores/appStore";

interface NavSection {
  label: string;
  collapsible?: boolean;
  items: { id: View; label: string; icon: React.ElementType; badge?: string }[];
}

const navSections: NavSection[] = [
  {
    label: "Main",
    items: [
      { id: "chat", label: "Chat", icon: MessageSquare },
      { id: "skills", label: "Skills", icon: Brain, badge: "New" },
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    ],
  },
  {
    label: "Agent",
    collapsible: true,
    items: [
      { id: "memory", label: "Memory & Plans", icon: Brain },
      { id: "tools", label: "Tools", icon: Wrench },
      { id: "workers", label: "Workers", icon: Cpu },
      { id: "tool-creator", label: "Tool Creator", icon: Sparkles },
    ],
  },
  {
    label: "System",
    collapsible: true,
    items: [
      { id: "connectors", label: "Connectors", icon: Plug, badge: "New" },
      { id: "guardrails", label: "Guardrails", icon: Shield },
      { id: "settings", label: "Settings", icon: Settings },
    ],
  },
];

interface SidebarProps {
  send?: (data: Record<string, unknown>) => void;
}

export function Sidebar({ send }: SidebarProps) {
  const { view, setView, connected, currentTier, historyPanelOpen, toggleHistoryPanel } = useAppStore();
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  const toggleSection = (label: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const handleNewChat = () => {
    useAppStore.getState().clearMessages();
    useAppStore.getState().setConversationId(null);
    setView("chat");
    if (send) {
      send({ type: "new_conversation" });
    }
  };

  return (
    <aside className="w-72 bg-gray-950 border-r border-gray-800/60 flex flex-col h-full">
      {/* Header: Logo + Status */}
      <div className="px-4 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-plutus-500 to-plutus-700 flex items-center justify-center font-bold text-base shadow-lg shadow-plutus-600/20 ring-1 ring-white/10">
              P
            </div>
            <div>
              <h1 className="font-semibold text-[15px] leading-none text-gray-100">Plutus</h1>
              <div className="flex items-center gap-1.5 mt-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    connected
                      ? "bg-emerald-400 shadow-sm shadow-emerald-400/60"
                      : "bg-red-400"
                  }`}
                />
                <span className="text-[10px] text-gray-500">
                  {connected ? "Online" : "Offline"}
                </span>
                <span className="text-gray-800 text-[10px]">·</span>
                <span className="text-[10px] text-gray-500 capitalize">{currentTier}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* New Chat + History Toggle */}
      <div className="px-3 pb-4 flex items-center gap-2">
        <button
          onClick={handleNewChat}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl
                     bg-plutus-600 hover:bg-plutus-500 text-white text-sm font-medium
                     transition-all duration-200 shadow-md shadow-plutus-600/20
                     hover:shadow-lg hover:shadow-plutus-500/25 active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
        {view === "chat" && (
          <button
            onClick={toggleHistoryPanel}
            title={historyPanelOpen ? "Hide history" : "Show history"}
            className={`p-2.5 rounded-xl transition-all duration-200 ${
              historyPanelOpen
                ? "bg-plutus-500/15 text-plutus-400 ring-1 ring-plutus-500/20"
                : "bg-gray-800/60 text-gray-500 hover:text-gray-300 hover:bg-gray-800"
            }`}
          >
            <History className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Navigation — takes remaining space */}
      <nav className="flex-1 p-3 space-y-2 overflow-y-auto sidebar-scroll min-h-0">
        {navSections.map((section) => {
          const isCollapsed = collapsedSections.has(section.label);
          const hasActiveItem = section.items.some((item) => item.id === view);

          return (
            <div key={section.label}>
              {/* Section header */}
              {section.collapsible ? (
                <button
                  onClick={() => toggleSection(section.label)}
                  className="w-full flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-gray-600 uppercase tracking-wider hover:text-gray-400 transition-colors"
                >
                  {isCollapsed ? (
                    <ChevronRight className="w-3 h-3" />
                  ) : (
                    <ChevronDown className="w-3 h-3" />
                  )}
                  <span>{section.label}</span>
                  {isCollapsed && hasActiveItem && (
                    <span className="w-1.5 h-1.5 rounded-full bg-plutus-500 ml-auto" />
                  )}
                </button>
              ) : (
                <p className="px-3 py-1.5 text-[11px] font-semibold text-gray-600 uppercase tracking-wider">
                  {section.label}
                </p>
              )}

              {/* Section items */}
              {!isCollapsed && (
                <div className="space-y-0.5">
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const active = view === item.id;
                    return (
                      <button
                        key={item.id}
                        onClick={() => setView(item.id)}
                        className={`w-full relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                          active
                            ? "bg-gray-800/80 text-gray-100"
                            : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/40"
                        }`}
                      >
                        {active && (
                          <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-plutus-500" />
                        )}
                        <Icon
                          className={`w-[18px] h-[18px] ${
                            active ? "text-plutus-400" : ""
                          }`}
                        />
                        <span className="flex-1 text-left">{item.label}</span>
                        {item.badge && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-plutus-500/15 text-plutus-400 font-semibold ring-1 ring-plutus-500/20">
                            {item.badge}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

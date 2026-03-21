import { useState } from "react";
import {
  MessageSquare,
  LayoutDashboard,
  Settings,
  Plus,
  Wrench,
  Cpu,
  Sparkles,
  Brain,
  Plug,
  Layers,
  MoreHorizontal,
  X,
  ChevronRight,
} from "lucide-react";
import { useAppStore, type View } from "../../stores/appStore";

interface NavItem {
  id: View;
  label: string;
  icon: React.ElementType;
  badge?: string;
}

// Primary tabs shown in the bottom bar (max 5 including "More")
const primaryTabs: NavItem[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "sessions", label: "Sessions", icon: Layers },
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "connectors", label: "Connect", icon: Plug, badge: "New" },
  { id: "settings", label: "Settings", icon: Settings },
];

// Additional tabs shown in the "More" drawer
const moreItems: NavItem[] = [
  { id: "memory", label: "Memory & Plans", icon: Brain },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "workers", label: "Workers", icon: Cpu },
  { id: "tool-creator", label: "Tool Creator", icon: Sparkles },
  { id: "skills", label: "Skills", icon: Brain, badge: "New" },
];

interface MobileNavProps {
  send?: (data: Record<string, unknown>) => void;
}

export function MobileNav({ send: _send }: MobileNavProps) {
  const { view, setView, connected, setPendingNewSession } = useAppStore();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleNewChat = () => {
    setPendingNewSession(true);
    setView("chat");
    setDrawerOpen(false);
  };

  const handleNav = (id: View) => {
    setView(id);
    setDrawerOpen(false);
  };

  // Check if current view is in "more" items
  const isMoreActive = moreItems.some((item) => item.id === view);

  return (
    <>
      {/* Bottom navigation bar — in-flow so it never scrolls */}
      <nav
        className="flex-shrink-0 flex items-stretch z-40"
        style={{
          background: "rgba(9, 9, 11, 0.95)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        {primaryTabs.map((tab) => {
          const Icon = tab.icon;
          const active = view === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => handleNav(tab.id)}
              className="relative flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 min-h-[56px] transition-all duration-150 active:scale-95"
            >
              {/* Active indicator dot */}
              {active && (
                <span
                  className="absolute top-1.5 w-1 h-1 rounded-full"
                  style={{ background: "#818cf8" }}
                />
              )}
              <Icon
                className="w-5 h-5 transition-colors"
                style={{ color: active ? "#818cf8" : "rgba(156,163,175,0.7)" }}
                strokeWidth={active ? 2.5 : 2}
              />
              <span
                className="text-[10px] font-medium leading-none transition-colors"
                style={{ color: active ? "#818cf8" : "rgba(156,163,175,0.7)" }}
              >
                {tab.label}
              </span>
              {tab.badge && (
                <span
                  className="absolute top-1 right-[calc(50%-18px)] text-[8px] px-1 py-0.5 rounded-full font-bold"
                  style={{
                    background: "rgba(99,102,241,0.2)",
                    color: "#818cf8",
                    border: "1px solid rgba(99,102,241,0.3)",
                  }}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}

        {/* More button */}
        <button
          onClick={() => setDrawerOpen(true)}
          className="relative flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 min-h-[56px] transition-all duration-150 active:scale-95"
        >
          {isMoreActive && (
            <span
              className="absolute top-1.5 w-1 h-1 rounded-full"
              style={{ background: "#818cf8" }}
            />
          )}
          <MoreHorizontal
            className="w-5 h-5 transition-colors"
            style={{ color: isMoreActive ? "#818cf8" : "rgba(156,163,175,0.7)" }}
            strokeWidth={isMoreActive ? 2.5 : 2}
          />
          <span
            className="text-[10px] font-medium leading-none transition-colors"
            style={{ color: isMoreActive ? "#818cf8" : "rgba(156,163,175,0.7)" }}
          >
            More
          </span>
        </button>
      </nav>

      {/* Backdrop */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* Slide-up drawer */}
      <div
        className="fixed left-0 right-0 bottom-0 z-50 rounded-t-2xl overflow-hidden transition-transform duration-300"
        style={{
          background: "rgba(15, 15, 20, 0.98)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderBottom: "none",
          transform: drawerOpen ? "translateY(0)" : "translateY(100%)",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-gray-700" />
        </div>

        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-3">
          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs text-white"
              style={{
                background: "linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)",
                boxShadow: "0 2px 8px rgba(99,102,241,0.4)",
              }}
            >
              P
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-100">Plutus</p>
              <p className="text-[10px] flex items-center gap-1" style={{ color: connected ? "#34d399" : "#f87171" }}>
                <span
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{ background: connected ? "#34d399" : "#f87171" }}
                />
                {connected ? "Connected" : "Offline"}
              </p>
            </div>
          </div>
          <button
            onClick={() => setDrawerOpen(false)}
            className="w-8 h-8 rounded-full flex items-center justify-center"
            style={{ background: "rgba(255,255,255,0.06)" }}
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        {/* New Chat button */}
        <div className="px-4 pb-3">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold text-white active:scale-[0.98] transition-transform"
            style={{
              background: "linear-gradient(135deg, rgba(99,102,241,0.9), rgba(79,70,229,0.9))",
              boxShadow: "0 4px 16px rgba(99,102,241,0.25)",
            }}
          >
            <Plus className="w-4 h-4" strokeWidth={2.5} />
            New Chat
          </button>
        </div>

        {/* Divider */}
        <div className="mx-4 mb-2 h-px" style={{ background: "rgba(255,255,255,0.06)" }} />

        {/* More nav items */}
        <div className="px-3 pb-4 space-y-1">
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-gray-500">
            Agent
          </p>
          {moreItems.map((item) => {
            const Icon = item.icon;
            const active = view === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleNav(item.id)}
                className="w-full flex items-center gap-3 px-3 py-3 rounded-xl text-sm font-medium transition-all active:scale-[0.98]"
                style={{
                  background: active ? "rgba(99,102,241,0.12)" : "transparent",
                  color: active ? "#818cf8" : "rgba(209,213,219,0.8)",
                  border: active ? "1px solid rgba(99,102,241,0.2)" : "1px solid transparent",
                }}
              >
                <Icon className="w-4.5 h-4.5 flex-shrink-0" style={{ color: active ? "#818cf8" : "rgba(156,163,175,0.7)" }} />
                <span className="flex-1 text-left text-[13px]">{item.label}</span>
                {item.badge && (
                  <span
                    className="text-[9px] px-1.5 py-0.5 rounded-full font-bold"
                    style={{
                      background: "rgba(99,102,241,0.15)",
                      color: "#818cf8",
                      border: "1px solid rgba(99,102,241,0.2)",
                    }}
                  >
                    {item.badge}
                  </span>
                )}
                <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

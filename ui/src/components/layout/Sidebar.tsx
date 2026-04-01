import { useState, useEffect } from "react";
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
  Layers,
  Home,
  Star,
  Heart,
  Zap,
  Globe,
  Code,
  Terminal,
  Palette,
  Music,
  Camera,
  Video,
  Mic,
  Bell,
  Calendar,
  Clock,
  Map,
  Compass,
  Bookmark,
  Flag,
  Award,
  Target,
  TrendingUp,
  BarChart,
  PieChart,
  Database,
  Server,
  Cloud,
  Lock,
  Unlock,
  Key,
  User,
  Users,
  Mail,
  Send,
  Download,
  Upload,
  File,
  Folder,
  Image,
  Monitor,
  Smartphone,
  Wifi,
} from "lucide-react";
import { useAppStore, PENDING_NEW_SESSION_ID, type View } from "../../stores/appStore";

// ── Icon registry — maps string names to Lucide components ──────────────────

const ICON_MAP: Record<string, React.ElementType> = {
  MessageSquare, LayoutDashboard, Shield, Settings, Plus, Wrench, Cpu,
  Sparkles, Brain, Plug, Layers, Home, Star, Heart, Zap, Globe, Code,
  Terminal, Palette, Music, Camera, Video, Mic, Bell, Calendar, Clock,
  Map, Compass, Bookmark, Flag, Award, Target, TrendingUp, BarChart,
  PieChart, Database, Server, Cloud, Lock, Unlock, Key, User, Users,
  Mail, Send, Download, Upload, File, Folder, Image, Monitor, Smartphone, Wifi,
};

// ── Types ───────────────────────────────────────────────────────────────────

interface NavItemConfig {
  id: View;
  label: string;
  icon: string;       // Lucide icon name (string, resolved at runtime)
  visible?: boolean;
  badge?: string;
}

interface NavSectionConfig {
  label: string;
  collapsible?: boolean;
  items: NavItemConfig[];
}

interface UIConfig {
  sections?: NavSectionConfig[];
  sidebar_width?: string;
  sidebar_logo_text?: string;
  sidebar_show_status?: boolean;
}

interface NavSection {
  label: string;
  collapsible?: boolean;
  items: { id: View; label: string; icon: React.ElementType; badge?: string }[];
}

// ── Default navigation (used when no custom config exists) ──────────────────

const DEFAULT_SECTIONS: NavSection[] = [
  {
    label: "Main",
    items: [
      { id: "chat", label: "Chat", icon: MessageSquare },
      { id: "sessions", label: "Sessions", icon: Layers },
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
      { id: "skills", label: "Skills", icon: Brain, badge: "New" },
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

// ── Convert config JSON to resolved NavSection[] ────────────────────────────

function resolveConfig(config: UIConfig): {
  sections: NavSection[];
  sidebarWidth: string;
  logoText: string;
  showStatus: boolean;
} {
  const sidebarWidth = config.sidebar_width || "16rem";
  const logoText = config.sidebar_logo_text || "Plutus";
  const showStatus = config.sidebar_show_status !== false;

  if (!config.sections || config.sections.length === 0) {
    return { sections: DEFAULT_SECTIONS, sidebarWidth, logoText, showStatus };
  }

  const sections: NavSection[] = config.sections.map((sec) => ({
    label: sec.label,
    collapsible: sec.collapsible,
    items: sec.items
      .filter((item) => item.visible !== false)
      .map((item) => ({
        id: item.id as View,
        label: item.label,
        icon: ICON_MAP[item.icon] || MessageSquare,
        badge: item.badge,
      })),
  }));

  return { sections, sidebarWidth, logoText, showStatus };
}

// ── Component ───────────────────────────────────────────────────────────────

interface SidebarProps {
  send?: (data: Record<string, unknown>) => void;
}

export function Sidebar({ send }: SidebarProps) {
  const { view, setView, connected, currentTier, setPendingNewSession, setActiveSessionId } = useAppStore();
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [navSections, setNavSections] = useState<NavSection[]>(DEFAULT_SECTIONS);
  const [sidebarWidth, setSidebarWidth] = useState("16rem");
  const [logoText, setLogoText] = useState("Plutus");
  const [showStatus, setShowStatus] = useState(true);

  // Load custom UI config from backend on mount
  useEffect(() => {
    fetch("/api/customization/ui-config.json")
      .then((res) => res.json())
      .then((config: UIConfig) => {
        if (config && (config.sections || config.sidebar_width || config.sidebar_logo_text)) {
          const resolved = resolveConfig(config);
          setNavSections(resolved.sections);
          setSidebarWidth(resolved.sidebarWidth);
          setLogoText(resolved.logoText);
          setShowStatus(resolved.showStatus);
        }
      })
      .catch(() => {
        // No custom config — use defaults
      });
  }, []);

  const toggleSection = (label: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  const handleNewChat = () => {
    setPendingNewSession(true);
    setActiveSessionId(PENDING_NEW_SESSION_ID);
    setView("chat");
  };

  return (
    <aside
      className="sidebar-root flex flex-col h-full relative overflow-hidden"
      style={{ width: sidebarWidth }}
    >
      {/* Subtle ambient glow at top */}
      <div className="sidebar-glow-top absolute top-0 left-0 right-0 h-32 pointer-events-none" />

      {/* Header: Logo + Status */}
      <div className="relative px-4 pt-5 pb-4">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="relative w-9 h-9 flex-shrink-0">
            <img
              src="/logo.svg"
              alt={logoText}
              className="w-9 h-9 object-contain"
            />
            {/* Online indicator */}
            {showStatus && (
              <span className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-gray-950 ${
                connected ? "bg-emerald-400" : "bg-red-400"
              }`} />
            )}
          </div>

          <div className="flex-1 min-w-0">
            <h1 className="font-semibold text-[15px] leading-none text-gray-100 tracking-tight">
              {logoText}
            </h1>
            {showStatus && (
              <div className="flex items-center gap-1.5 mt-1.5">
                <span className={`text-[10px] font-medium ${connected ? "text-emerald-500 dark:text-emerald-400" : "text-red-500 dark:text-red-400"}`}>
                  {connected ? "Online" : "Offline"}
                </span>
                <span className="text-gray-600 text-[10px]">·</span>
                <span className="text-[10px] text-gray-400 capitalize">{currentTier}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="relative px-3 pb-4">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium text-white transition-all duration-200 active:scale-[0.97]"
          style={{
            background: "linear-gradient(135deg, rgba(99, 102, 241, 0.9), rgba(79, 70, 229, 0.9))",
            boxShadow: "0 4px 16px rgba(99, 102, 241, 0.25), inset 0 1px 0 rgba(255,255,255,0.1)"
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 6px 20px rgba(99, 102, 241, 0.35), inset 0 1px 0 rgba(255,255,255,0.1)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 16px rgba(99, 102, 241, 0.25), inset 0 1px 0 rgba(255,255,255,0.1)";
          }}
        >
          <Plus className="w-4 h-4" strokeWidth={2.5} />
          New Chat
        </button>
      </div>

      {/* Divider */}
      <div className="sidebar-divider mx-3 mb-3 h-px" />

      {/* Navigation */}
      <nav className="relative flex-1 px-2 pb-4 space-y-0.5 overflow-y-auto sidebar-scroll min-h-0">
        {navSections.map((section) => {
          const isCollapsed = collapsedSections.has(section.label);
          const hasActiveItem = section.items.some((item) => item.id === view);

          return (
            <div key={section.label} className="mb-1">
              {/* Section header */}
              {section.collapsible ? (
                <button
                  onClick={() => toggleSection(section.label)}
                  className="sidebar-section-label w-full flex items-center gap-1.5 px-3 py-2 text-[10px] font-semibold uppercase tracking-widest hover:text-gray-400 transition-colors rounded-lg"
                >
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-200 ${isCollapsed ? "-rotate-90" : ""}`}
                  />
                  <span>{section.label}</span>
                  {isCollapsed && hasActiveItem && (
                    <span className="w-1.5 h-1.5 rounded-full bg-plutus-500 ml-auto" />
                  )}
                </button>
              ) : (
                <p className="sidebar-section-label px-3 py-2 text-[10px] font-semibold uppercase tracking-widest">
                  {section.label}
                </p>
              )}

              {/* Section items */}
              {!isCollapsed && (
                <div className="space-y-0.5 mt-0.5">
                  {section.items.map((item) => {
                    const Icon = item.icon;
                    const active = view === item.id;
                    return (
                      <div key={item.id} className="relative">
                        <button
                          onClick={() => setView(item.id)}
                          className={`sidebar-nav-item w-full relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium ${
                            active ? "active" : ""
                          }`}
                        >
                          {active && <div className="nav-active-indicator" />}
                          <Icon
                            className={`w-[17px] h-[17px] flex-shrink-0 ${
                              active ? "text-plutus-400" : "text-gray-500"
                            }`}
                          />
                          <span className="flex-1 text-left text-[13px]">{item.label}</span>
                          {item.badge && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold tracking-wide"
                              style={{
                                background: "rgba(99, 102, 241, 0.15)",
                                color: "#818cf8",
                                border: "1px solid rgba(99, 102, 241, 0.2)"
                              }}
                            >
                              {item.badge}
                            </span>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Bottom version badge */}
      <div className="relative px-4 py-3 border-t border-gray-700/30">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-gray-500 font-mono">{logoText} AI</span>
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-500 status-dot-online" : "bg-red-500"}`} />
            <span className="text-[10px] text-gray-500">{connected ? "Connected" : "Offline"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

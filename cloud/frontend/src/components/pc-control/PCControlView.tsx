import { useState, useEffect, useCallback } from "react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

interface Capability {
  label: string;
  description: string;
  operations: string[];
}

interface Shortcut {
  name: string;
  keys: string;
  description: string;
}

interface WorkflowTemplate {
  name: string;
  description: string;
}

interface SavedWorkflow {
  name: string;
  description: string;
  step_count: number;
  tags?: string[];
}

interface Skill {
  name: string;
  description: string;
  app: string;
  category: string;
  required_params: string[];
  optional_params: string[];
  triggers: string[];
}

interface PCContext {
  active_app: string;
  active_window: string;
  category: string;
  pid?: number;
  browser_tab?: string;
  document?: string;
  mouse: { x: number; y: number };
  summary: string;
  action_count?: number;
  recent_actions?: { action: string; target_app?: string; timestamp: string }[];
}

const CAPABILITY_ICONS: Record<string, string> = {
  context: "🧠",
  mouse: "🖱️",
  keyboard: "⌨️",
  screen: "🖥️",
  windows: "🪟",
  workflows: "⚡",
};

const CAPABILITY_COLORS: Record<string, string> = {
  context: "from-cyan-500/20 to-cyan-600/10 border-cyan-500/30",
  mouse: "from-blue-500/20 to-blue-600/10 border-blue-500/30",
  keyboard: "from-emerald-500/20 to-emerald-600/10 border-emerald-500/30",
  screen: "from-purple-500/20 to-purple-600/10 border-purple-500/30",
  windows: "from-amber-500/20 to-amber-600/10 border-amber-500/30",
  workflows: "from-pink-500/20 to-pink-600/10 border-pink-500/30",
};

const CATEGORY_ICONS: Record<string, string> = {
  browser: "🌐",
  editor: "📝",
  terminal: "💻",
  messenger: "💬",
  email: "📧",
  media: "🎵",
  office: "📄",
  file_manager: "📁",
  system: "⚙️",
  game: "🎮",
  unknown: "🔲",
};

const OP_DESCRIPTIONS: Record<string, string> = {
  get_context: "Check which app/window is active right now",
  active_window: "Get detailed info about the focused window",
  move: "Move cursor smoothly to a position",
  click: "Click at a position (use target_app!)",
  double_click: "Double-click at a position",
  right_click: "Right-click for context menu",
  drag: "Drag from one point to another",
  scroll: "Scroll up or down",
  hover: "Hover to trigger tooltips",
  type: "Type text naturally (use target_app!)",
  press: "Press a single key",
  hotkey: "Press a key combination",
  shortcut: "Use a named shortcut (e.g. copy, paste)",
  key_down: "Hold a key down",
  key_up: "Release a held key",
  list_shortcuts: "Show all available shortcuts",
  screenshot: "Capture the screen",
  read_screen: "Read all text on screen (OCR)",
  find_text: "Find text and get its position",
  find_elements: "Detect UI elements",
  get_pixel_color: "Get color at a point",
  find_color: "Find elements by color",
  wait_for_text: "Wait for text to appear",
  wait_for_change: "Wait for screen to update",
  screen_info: "Get screen resolution and info",
  list_windows: "List all open windows",
  find_window: "Find a window by name",
  focus: "Bring a window to front",
  close_window: "Close a window",
  minimize: "Minimize a window",
  maximize: "Maximize a window",
  move_window: "Move a window to a position",
  resize: "Resize a window",
  snap_left: "Snap window to left half",
  snap_right: "Snap window to right half",
  snap_top: "Snap window to top half",
  snap_bottom: "Snap window to bottom half",
  snap_quarter: "Snap window to a quarter",
  tile: "Tile multiple windows",
  run_workflow: "Run a saved workflow",
  save_workflow: "Save a new workflow",
  list_workflows: "List all workflows",
  list_templates: "List workflow templates",
  get_template: "Get a template's details",
  delete_workflow: "Delete a saved workflow",
};

// ── Self-Improvement Section ──
function SelfImprovementSection() {
  const [stats, setStats] = useState<Record<string, any>>({});
  const [log, setLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, logRes] = await Promise.all([
          api.getImprovementStats().catch(() => ({})),
          api.getImprovementLog(20).catch(() => ({ log: [] })),
        ]);
        setStats(statsRes || {});
        setLog(Array.isArray(logRes.log) ? logRes.log : []);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const totalCreated = stats.total_created || 0;
  const totalUpdated = stats.total_updated || 0;
  const totalDeleted = stats.total_deleted || 0;
  const categories = stats.categories || {};

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white/90 flex items-center gap-2">
          <span className="text-rose-400">🧬</span> Self-Improvement
          <span className="text-xs font-normal text-white/40 bg-white/5 px-2 py-0.5 rounded-full">
            {totalCreated} skills learned
          </span>
        </h2>
      </div>

      <p className="text-white/40 text-sm">
        Plutus learns from experience. When it completes a complex task, it can save the steps as a
        reusable skill — making it faster and more reliable over time. Skills are saved permanently
        and available in all future conversations.
      </p>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-gradient-to-br from-emerald-500/10 to-emerald-600/5 border border-emerald-500/20 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-emerald-400">{totalCreated}</div>
          <div className="text-white/40 text-xs mt-1">Skills Created</div>
        </div>
        <div className="bg-gradient-to-br from-blue-500/10 to-blue-600/5 border border-blue-500/20 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-blue-400">{totalUpdated}</div>
          <div className="text-white/40 text-xs mt-1">Skills Updated</div>
        </div>
        <div className="bg-gradient-to-br from-amber-500/10 to-amber-600/5 border border-amber-500/20 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-amber-400">{Object.keys(categories).length}</div>
          <div className="text-white/40 text-xs mt-1">Categories</div>
        </div>
        <div className="bg-gradient-to-br from-red-500/10 to-red-600/5 border border-red-500/20 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-red-400">{totalDeleted}</div>
          <div className="text-white/40 text-xs mt-1">Skills Removed</div>
        </div>
      </div>

      {/* How it works */}
      <div className="bg-surface border border-gray-800/60 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-white/70 mb-3">How Self-Improvement Works</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="flex items-start gap-2">
            <span className="text-emerald-400 text-lg">1️⃣</span>
            <div>
              <div className="text-white/70 text-xs font-semibold">Learn</div>
              <div className="text-white/40 text-[11px]">Plutus completes a multi-step task and recognizes a reusable pattern</div>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-blue-400 text-lg">2️⃣</span>
            <div>
              <div className="text-white/70 text-xs font-semibold">Save</div>
              <div className="text-white/40 text-[11px]">It creates a skill with validated steps, parameters, and triggers</div>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-violet-400 text-lg">3️⃣</span>
            <div>
              <div className="text-white/70 text-xs font-semibold">Reuse</div>
              <div className="text-white/40 text-[11px]">Next time a similar task comes up, it uses the skill instantly</div>
            </div>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      {Object.keys(categories).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(categories).map(([cat, count]) => (
            <div key={cat} className="bg-white/5 border border-gray-800/60 rounded-lg px-3 py-1.5 flex items-center gap-2">
              <span className="text-sm">{CATEGORY_ICONS[cat] || '📦'}</span>
              <span className="text-white/60 text-xs capitalize">{cat}</span>
              <span className="text-white/30 text-xs">{String(count)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Improvement Log */}
      <div>
        <button
          onClick={() => setShowLog(!showLog)}
          className="flex items-center gap-2 text-sm text-white/50 hover:text-white/70 transition-colors"
        >
          <span>{showLog ? '▼' : '▶'}</span>
          <span>Improvement History ({log.length} entries)</span>
        </button>

        {showLog && (
          <div className="mt-3 space-y-2 max-h-80 overflow-y-auto">
            {loading ? (
              <div className="text-white/30 text-sm text-center py-4">Loading...</div>
            ) : log.length === 0 ? (
              <div className="text-center py-6 text-white/30 text-sm">
                <div className="text-2xl mb-2">🌱</div>
                No improvements yet. As Plutus completes tasks, it will learn and create new skills automatically.
              </div>
            ) : (
              log.map((entry, i) => (
                <div key={i} className="bg-white/[0.03] border border-white/5 rounded-lg p-3 flex items-start gap-3">
                  <span className="text-lg">
                    {entry.action === 'created' ? '🌟' : entry.action === 'updated' ? '🔧' : '🗑️'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-white/70 text-xs font-semibold">{entry.skill_name || 'Unknown'}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        entry.action === 'created' ? 'bg-emerald-500/10 text-emerald-400' :
                        entry.action === 'updated' ? 'bg-blue-500/10 text-blue-400' :
                        'bg-red-500/10 text-red-400'
                      }`}>
                        {entry.action || 'unknown'}
                      </span>
                    </div>
                    {entry.reason && (
                      <div className="text-white/30 text-[11px] mt-0.5">{entry.reason}</div>
                    )}
                    {entry.timestamp && (
                      <div className="text-white/20 text-[10px] mt-1">{new Date(entry.timestamp).toLocaleString()}</div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function PCControlView() {
  const [capabilities, setCapabilities] = useState<Record<string, Capability>>({});
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([]);
  const [workflows, setWorkflows] = useState<SavedWorkflow[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [context, setContext] = useState<PCContext | null>(null);
  const [available, setAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expandedCap, setExpandedCap] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [shortcutSearch, setShortcutSearch] = useState("");
  const [contextLive, setContextLive] = useState(true);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillCategories, setSkillCategories] = useState<string[]>([]);
  const [selectedSkillCat, setSelectedSkillCat] = useState<string>("all");
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);

  // Fetch main data once
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, shortcutsRes, workflowsRes, skillsRes] = await Promise.all([
        api.getPCStatus().catch(() => ({ available: false, capabilities: {}, context: null })),
        api.getPCShortcuts().catch(() => ({ shortcuts: [] })),
        api.getPCWorkflows().catch(() => ({ workflows: [], templates: [] })),
        api.getSkills().catch(() => ({ skills: [], categories: [] })),
      ]);

      setAvailable(statusRes.available ?? false);
      setCapabilities(statusRes.capabilities ?? {});

      // Set initial context from status
      if (statusRes.context) {
        setContext(prev => prev || { ...statusRes.context, summary: "", mouse: statusRes.context.mouse || { x: 0, y: 0 } });
      }

      // Defensive: ensure shortcuts is always an array
      const rawShortcuts = shortcutsRes.shortcuts;
      if (Array.isArray(rawShortcuts)) {
        setShortcuts(rawShortcuts);
      } else if (rawShortcuts && typeof rawShortcuts === "object") {
        setShortcuts(
          Object.entries(rawShortcuts).map(([name, keys]) => ({
            name,
            keys: String(keys),
            description: name.replace(/_/g, " "),
          }))
        );
      } else {
        setShortcuts([]);
      }

      setWorkflows(Array.isArray(workflowsRes.workflows) ? workflowsRes.workflows : []);
      setTemplates(Array.isArray(workflowsRes.templates) ? workflowsRes.templates : []);

      setSkills(Array.isArray(skillsRes.skills) ? skillsRes.skills : []);
      setSkillCategories(Array.isArray(skillsRes.categories) ? skillsRes.categories : []);
    } catch {
      setAvailable(false);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch live context
  const fetchContext = useCallback(async () => {
    try {
      const res = await api.getPCContext();
      if (res && res.active_app) {
        setContext(res as PCContext);
      }
    } catch {
      // Context unavailable — that's fine
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Poll context every 3 seconds when live mode is on
  useEffect(() => {
    if (!contextLive) return;
    fetchContext();
    const interval = setInterval(fetchContext, 3000);
    return () => clearInterval(interval);
  }, [contextLive, fetchContext]);

  const filteredShortcuts = Array.isArray(shortcuts)
    ? shortcuts.filter(
        (s) =>
          !shortcutSearch ||
          (s.name || "").toLowerCase().includes(shortcutSearch.toLowerCase()) ||
          (s.description || "").toLowerCase().includes(shortcutSearch.toLowerCase()) ||
          (s.keys || "").toLowerCase().includes(shortcutSearch.toLowerCase())
      )
    : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* ── Live Context Banner ── */}
      <div className="bg-gradient-to-r from-cyan-900/40 via-blue-900/30 to-purple-900/30 border border-cyan-500/30 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-lg shadow-lg">
              🧠
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Context Awareness
                {contextLive && (
                  <span className="flex items-center gap-1.5 text-xs font-normal">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                    <span className="text-cyan-400">Live</span>
                  </span>
                )}
              </h2>
              <p className="text-white/40 text-xs">
                Plutus always knows which app and window is active before acting
              </p>
            </div>
          </div>
          <button
            onClick={() => setContextLive(!contextLive)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              contextLive
                ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30"
                : "bg-white/5 text-white/40 border border-gray-800/60 hover:bg-white/10"
            }`}
          >
            {contextLive ? "⏸ Pause" : "▶ Resume"}
          </button>
        </div>

        {context ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Active App */}
            <div className="bg-white/5 rounded-xl p-3 border border-white/5">
              <div className="text-white/40 text-xs mb-1">Active App</div>
              <div className="flex items-center gap-2">
                <span className="text-lg">
                  {CATEGORY_ICONS[context.category] || CATEGORY_ICONS.unknown}
                </span>
                <div>
                  <div className="text-white font-semibold text-sm">
                    {context.active_app || "Unknown"}
                  </div>
                  <div className="text-white/30 text-xs capitalize">
                    {context.category || "unknown"}
                  </div>
                </div>
              </div>
            </div>

            {/* Active Window */}
            <div className="bg-white/5 rounded-xl p-3 border border-white/5">
              <div className="text-white/40 text-xs mb-1">Window Title</div>
              <div className="text-white text-sm font-medium truncate">
                {context.active_window || "Unknown"}
              </div>
              {context.browser_tab && (
                <div className="text-blue-400/60 text-xs mt-1 truncate">
                  Tab: {context.browser_tab}
                </div>
              )}
              {context.document && (
                <div className="text-emerald-400/60 text-xs mt-1 truncate">
                  Doc: {context.document}
                </div>
              )}
            </div>

            {/* Mouse Position + Actions */}
            <div className="bg-white/5 rounded-xl p-3 border border-white/5">
              <div className="text-white/40 text-xs mb-1">Mouse & Actions</div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-white text-sm font-mono">
                    ({context.mouse?.x || 0}, {context.mouse?.y || 0})
                  </div>
                  <div className="text-white/30 text-xs">cursor position</div>
                </div>
                {context.action_count !== undefined && (
                  <div className="text-right">
                    <div className="text-white text-sm font-semibold">
                      {context.action_count}
                    </div>
                    <div className="text-white/30 text-xs">actions logged</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white/5 rounded-xl p-4 border border-white/5 text-center">
            <p className="text-white/40 text-sm">
              Context will appear once Plutus starts interacting with the computer.
            </p>
            <p className="text-white/25 text-xs mt-1">
              The context engine tracks which app is active, preventing actions on the wrong window.
            </p>
          </div>
        )}

        {/* Recent Actions */}
        {context?.recent_actions && context.recent_actions.length > 0 && (
          <div className="mt-3 bg-white/5 rounded-xl p-3 border border-white/5">
            <div className="text-white/40 text-xs mb-2">Recent Actions</div>
            <div className="space-y-1">
              {context.recent_actions.slice(-5).reverse().map((a, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-cyan-400/60 font-mono w-16 text-right">
                    {new Date(a.timestamp).toLocaleTimeString()}
                  </span>
                  <code className="text-white/70 bg-white/5 px-1.5 py-0.5 rounded">
                    {a.action}
                  </code>
                  {a.target_app && (
                    <span className="text-emerald-400/60">→ {a.target_app}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Hero Section ── */}
      <div className="bg-gradient-to-r from-blue-600/20 via-purple-600/15 to-pink-600/20 border border-gray-800/60 rounded-2xl p-8">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-2xl shadow-lg">
            👻
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Computer Use</h1>
            <p className="text-white/60 text-sm">
              Plutus reads the accessibility tree, interacts by element reference, and controls your PC
            </p>
          </div>
        </div>

        <p className="text-white/50 text-sm max-w-2xl mb-4">
          This is how Plutus primarily operates. When you give it a task, it automatically uses
          these capabilities to interact with your computer — just like a person sitting at the keyboard.
          You don't need to configure anything here. Just go to <button
            onClick={() => useAppStore.getState().setView("chat")}
            className="text-blue-400 hover:text-blue-300 underline"
          >Chat</button> and tell Plutus what to do.
        </p>

        {available ? (
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-emerald-400 text-sm font-medium">System Active</span>
            <span className="text-white/40 text-sm ml-2">
              {Object.keys(capabilities).length} capability groups •{" "}
              {Object.values(capabilities).reduce((a, c) => a + (c.operations?.length || 0), 0)} operations
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span className="text-amber-400 text-sm font-medium">
              Requires desktop environment (pyautogui, Pillow)
            </span>
          </div>
        )}

        {/* Navigate → Snapshot → Ref → Act → Verify loop */}
        <div className="mt-6 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {[
            { step: "1", label: "Open", desc: "Launch app or navigate to URL", color: "text-cyan-400" },
            { step: "2", label: "Snapshot", desc: "Read the accessibility tree", color: "text-blue-400" },
            { step: "3", label: "Find", desc: "Identify elements by [ref] number", color: "text-purple-400" },
            { step: "4", label: "Act", desc: "Click, type, or select by ref", color: "text-pink-400" },
            { step: "5", label: "Verify", desc: "Snapshot again to confirm", color: "text-emerald-400" },
          ].map((s) => (
            <div key={s.step} className="bg-white/5 rounded-xl p-3 border border-white/5">
              <div className={`text-lg font-bold ${s.color}`}>
                {s.step}. {s.label}
              </div>
              <div className="text-white/50 text-xs mt-1">{s.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Quick Start ── */}
      <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border border-blue-500/20 rounded-xl p-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold">Ready to go</h3>
            <p className="text-white/50 text-sm mt-1">
              Just tell Plutus what to do in the chat. It will automatically use the computer.
            </p>
          </div>
          <button
            onClick={() => useAppStore.getState().setView("chat")}
            className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors whitespace-nowrap"
          >
            Open Chat
          </button>
        </div>
      </div>

      {/* ── Capability Cards ── */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white/90">What Plutus Can Do</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(capabilities).map(([key, cap]) => (
            <div
              key={key}
              className={`bg-gradient-to-br ${CAPABILITY_COLORS[key] || "from-gray-500/20 to-gray-600/10 border-gray-500/30"} border rounded-xl p-5 cursor-pointer transition-all hover:scale-[1.02] hover:shadow-lg`}
              onClick={() => setExpandedCap(expandedCap === key ? null : key)}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{CAPABILITY_ICONS[key] || "🔧"}</span>
                  <div>
                    <h3 className="font-semibold text-white">{cap.label}</h3>
                    <p className="text-white/50 text-xs">{cap.description}</p>
                  </div>
                </div>
                <span className="text-white/30 text-xs bg-white/5 px-2 py-1 rounded-full">
                  {cap.operations?.length || 0} ops
                </span>
              </div>

              {expandedCap === key && cap.operations && (
                <div className="mt-4 space-y-1.5 border-t border-gray-800/60 pt-3">
                  {cap.operations.map((op: string) => (
                    <div
                      key={op}
                      className="flex items-center justify-between py-1.5 px-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                    >
                      <code className="text-xs font-mono text-white/80">{op}</code>
                      <span className="text-white/40 text-xs ml-2 text-right">
                        {OP_DESCRIPTIONS[op] || ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {expandedCap !== key && cap.operations && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {cap.operations.slice(0, 5).map((op: string) => (
                    <span
                      key={op}
                      className="text-xs bg-white/10 text-white/60 px-2 py-0.5 rounded-full"
                    >
                      {op}
                    </span>
                  ))}
                  {cap.operations.length > 5 && (
                    <span className="text-xs text-white/30 px-2 py-0.5">
                      +{cap.operations.length - 5} more
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Fallback static cards */}
          {Object.keys(capabilities).length === 0 && (
            <>
              {[
                { icon: "🧠", label: "Context Awareness", desc: "Always knows which app is active. Prevents typing into wrong windows.", color: CAPABILITY_COLORS.context },
                { icon: "🖱️", label: "Mouse Control", desc: "Smooth bezier-curve movement, clicking, dragging, scrolling", color: CAPABILITY_COLORS.mouse },
                { icon: "⌨️", label: "Keyboard Control", desc: "Natural typing, 37 shortcuts, hotkeys, cross-platform", color: CAPABILITY_COLORS.keyboard },
                { icon: "🖥️", label: "Screen Reading", desc: "Screenshots, OCR text reading, element detection", color: CAPABILITY_COLORS.screen },
                { icon: "🪟", label: "Window Management", desc: "Snap, tile, resize, focus, and manage app windows", color: CAPABILITY_COLORS.windows },
                { icon: "⚡", label: "Workflow Automation", desc: "Chain actions into replayable multi-step sequences", color: CAPABILITY_COLORS.workflows },
              ].map((cap) => (
                <div
                  key={cap.label}
                  className={`bg-gradient-to-br ${cap.color} border rounded-xl p-5`}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl">{cap.icon}</span>
                    <div>
                      <h3 className="font-semibold text-white">{cap.label}</h3>
                      <p className="text-white/50 text-xs">{cap.desc}</p>
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── Snapshot + Ref Explainer ── */}
      <div className="bg-gradient-to-r from-cyan-900/20 to-blue-900/20 border border-cyan-500/20 rounded-xl p-5">
        <h3 className="text-white font-semibold flex items-center gap-2 mb-3">
          <span className="text-cyan-400">🌳</span> How Accessibility Tree Navigation Works
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
            <div className="text-red-400 text-xs font-semibold mb-2">❌ Old way: Screenshots + OCR</div>
            <div className="space-y-1 text-xs text-white/50 font-mono">
              <div>Take screenshot → OCR text → guess coordinates</div>
              <div className="text-red-400/60">→ Slow, uses many tokens</div>
              <div className="text-red-400/60">→ Unreliable pixel clicking</div>
            </div>
          </div>
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3">
            <div className="text-emerald-400 text-xs font-semibold mb-2">✅ New way: Accessibility Tree + Refs</div>
            <div className="space-y-1 text-xs text-white/50 font-mono">
              <div>snapshot() → [1] button 'Sign In' → click_ref(ref=1)</div>
              <div className="text-emerald-400/60">→ Fast, minimal tokens</div>
              <div className="text-emerald-400/60">→ Precise element targeting</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Keyboard Shortcuts ── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white/90">Keyboard Shortcuts</h2>
          <button
            onClick={() => setShowShortcuts(!showShortcuts)}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            {showShortcuts ? "Hide" : `Show all ${shortcuts.length} shortcuts`}
          </button>
        </div>

        {showShortcuts && (
          <div className="bg-surface border border-gray-800/60 rounded-xl overflow-hidden">
            <div className="p-3 border-b border-gray-800/60">
              <input
                type="text"
                placeholder="Search shortcuts..."
                value={shortcutSearch}
                onChange={(e) => setShortcutSearch(e.target.value)}
                className="w-full bg-white/5 border border-gray-800/60 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
              />
            </div>
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-white/5 sticky top-0">
                  <tr>
                    <th className="text-left px-4 py-2 text-white/50 font-medium">Name</th>
                    <th className="text-left px-4 py-2 text-white/50 font-medium">Keys</th>
                    <th className="text-left px-4 py-2 text-white/50 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredShortcuts.map((s, i) => (
                    <tr
                      key={s.name}
                      className={`border-t border-white/5 ${i % 2 === 0 ? "bg-white/[0.02]" : ""}`}
                    >
                      <td className="px-4 py-2">
                        <code className="text-blue-400 text-xs font-mono bg-blue-500/10 px-1.5 py-0.5 rounded">
                          {s.name}
                        </code>
                      </td>
                      <td className="px-4 py-2">
                        <kbd className="text-white/70 text-xs bg-white/10 px-2 py-0.5 rounded border border-gray-800/60 font-mono">
                          {s.keys}
                        </kbd>
                      </td>
                      <td className="px-4 py-2 text-white/50 text-xs">{s.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredShortcuts.length === 0 && (
                <div className="text-center py-6 text-white/30 text-sm">No shortcuts match your search</div>
              )}
            </div>
          </div>
        )}

        {!showShortcuts && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {["copy", "paste", "save", "undo", "redo", "new_tab", "close_tab", "find", "select_all", "screenshot", "switch_app", "lock_screen"].map(
              (name) => {
                const s = shortcuts.find((sc) => sc.name === name);
                return (
                  <div
                    key={name}
                    className="bg-white/5 border border-gray-800/60 rounded-lg p-2.5 text-center hover:bg-white/10 transition-colors"
                  >
                    <code className="text-xs font-mono text-blue-400">{name}</code>
                    {s && (
                      <div className="text-white/30 text-[10px] mt-1 font-mono">{s.keys}</div>
                    )}
                  </div>
                );
              }
            )}
          </div>
        )}
      </div>

      {/* ── Workflows ── */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white/90">Workflows</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface border border-gray-800/60 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white/70 mb-3 flex items-center gap-2">
              <span className="text-amber-400">📋</span> Templates
            </h3>
            {templates.length > 0 ? (
              <div className="space-y-2">
                {templates.map((t) => (
                  <div
                    key={t.name}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                  >
                    <div>
                      <code className="text-xs font-mono text-amber-400">{t.name}</code>
                      <p className="text-white/40 text-xs mt-0.5">{t.description}</p>
                    </div>
                    <span className="text-white/20 text-xs">built-in</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-white/30 text-sm">Templates load when the agent runs</p>
            )}
          </div>

          <div className="bg-surface border border-gray-800/60 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white/70 mb-3 flex items-center gap-2">
              <span className="text-emerald-400">💾</span> Saved Workflows
            </h3>
            {workflows.length > 0 ? (
              <div className="space-y-2">
                {workflows.map((w) => (
                  <div
                    key={w.name}
                    className="flex items-center justify-between p-2.5 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
                  >
                    <div>
                      <code className="text-xs font-mono text-emerald-400">{w.name}</code>
                      <p className="text-white/40 text-xs mt-0.5">
                        {w.description || `${w.step_count} steps`}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <p className="text-white/30 text-sm">No saved workflows yet</p>
                <p className="text-white/20 text-xs mt-1">
                  Ask Plutus in chat to create a workflow
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── App Skills ── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white/90 flex items-center gap-2">
            <span className="text-violet-400">🎯</span> App Skills
            <span className="text-xs font-normal text-white/40 bg-white/5 px-2 py-0.5 rounded-full">
              {skills.length} available
            </span>
          </h2>
          <div className="flex gap-1.5">
            <button
              onClick={() => setSelectedSkillCat("all")}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                selectedSkillCat === "all"
                  ? "bg-violet-500/20 text-violet-400 border border-violet-500/30"
                  : "bg-white/5 text-white/40 border border-gray-800/60 hover:bg-white/10"
              }`}
            >
              All
            </button>
            {skillCategories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedSkillCat(cat)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors capitalize ${
                  selectedSkillCat === cat
                    ? "bg-violet-500/20 text-violet-400 border border-violet-500/30"
                    : "bg-white/5 text-white/40 border border-gray-800/60 hover:bg-white/10"
                }`}
              >
                {CATEGORY_ICONS[cat] || "📦"} {cat}
              </button>
            ))}
          </div>
        </div>

        <p className="text-white/40 text-sm">
          Pre-built, tested workflows for common apps. When you ask Plutus to do something,
          it automatically uses the right skill if one exists — no manual selection needed.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {skills
            .filter((s) => selectedSkillCat === "all" || s.category === selectedSkillCat)
            .map((skill) => (
              <div
                key={skill.name}
                className={`bg-surface border rounded-xl overflow-hidden transition-all cursor-pointer ${
                  expandedSkill === skill.name
                    ? "border-violet-500/40 shadow-lg shadow-violet-500/10"
                    : "border-gray-800/60 hover:border-white/20"
                }`}
                onClick={() => setExpandedSkill(expandedSkill === skill.name ? null : skill.name)}
              >
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {CATEGORY_ICONS[skill.category] || "📦"}
                      </span>
                      <div>
                        <h3 className="text-sm font-semibold text-white">{skill.app}</h3>
                        <code className="text-[10px] font-mono text-violet-400/70">{skill.name}</code>
                      </div>
                    </div>
                    <span className="text-white/20 text-xs">
                      {expandedSkill === skill.name ? "▲" : "▼"}
                    </span>
                  </div>
                  <p className="text-white/50 text-xs">{skill.description}</p>
                </div>

                {expandedSkill === skill.name && (
                  <div className="border-t border-gray-800/60 p-4 bg-white/[0.02] space-y-3">
                    {skill.required_params.length > 0 && (
                      <div>
                        <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Required</div>
                        <div className="flex flex-wrap gap-1">
                          {skill.required_params.map((p) => (
                            <span key={p} className="text-xs bg-violet-500/10 text-violet-400 px-2 py-0.5 rounded font-mono">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {skill.optional_params.length > 0 && (
                      <div>
                        <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Optional</div>
                        <div className="flex flex-wrap gap-1">
                          {skill.optional_params.map((p) => (
                            <span key={p} className="text-xs bg-white/5 text-white/40 px-2 py-0.5 rounded font-mono">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    <div>
                      <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Triggers</div>
                      <div className="flex flex-wrap gap-1">
                        {skill.triggers.slice(0, 5).map((t) => (
                          <span key={t} className="text-[10px] bg-white/5 text-white/30 px-1.5 py-0.5 rounded">
                            "{t}"
                          </span>
                        ))}
                        {skill.triggers.length > 5 && (
                          <span className="text-[10px] text-white/20">+{skill.triggers.length - 5} more</span>
                        )}
                      </div>
                    </div>
                    <div className="bg-violet-500/5 border border-violet-500/10 rounded-lg p-2">
                      <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Example</div>
                      <code className="text-[10px] text-violet-400/80 font-mono break-all">
                        pc(operation="run_skill", skill_name="{skill.name}",
                        skill_params=&#123;{skill.required_params.map(p => `"${p}": "..."`).join(", ")}&#125;)
                      </code>
                    </div>
                  </div>
                )}
              </div>
            ))}
        </div>

        {skills.filter((s) => selectedSkillCat === "all" || s.category === selectedSkillCat).length === 0 && (
          <div className="text-center py-8 text-white/30 text-sm">
            No skills available for this category
          </div>
        )}
      </div>

      {/* ── Self-Improvement ── */}
      <SelfImprovementSection />

      {/* ── How it works ── */}
      <div className="bg-surface border border-gray-800/60 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white/90 mb-4">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-blue-400">Just tell Plutus what to do</h3>
            <div className="space-y-1.5">
              {[
                '"Open WhatsApp and send a message to Mom"',
                '"Open Chrome and go to google.com"',
                '"Click the Submit button"',
                '"Take a screenshot and tell me what you see"',
                '"Snap VS Code to the left and Chrome to the right"',
                '"Type my email address into the login field"',
              ].map((example) => (
                <div
                  key={example}
                  className="bg-white/5 rounded-lg px-3 py-2 text-white/60 text-xs font-mono cursor-pointer hover:bg-white/10 transition-colors"
                  onClick={() => {
                    useAppStore.getState().setView("chat");
                  }}
                >
                  {example}
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-purple-400">What happens behind the scenes</h3>
            <div className="space-y-2 text-sm text-white/50">
              <div className="flex items-start gap-2">
                <span className="text-cyan-400 mt-0.5">🚀</span>
                <p>
                  <strong className="text-white/70">OS Commands</strong> open apps instantly via native
                  shell commands — no clicking desktop icons.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-blue-400 mt-0.5">🌳</span>
                <p>
                  <strong className="text-white/70">Accessibility Tree</strong> reads every interactive
                  element on the page with numbered [ref] identifiers.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">🎯</span>
                <p>
                  <strong className="text-white/70">Ref-Based Interaction</strong> clicks and types by
                  element reference — precise, fast, no pixel guessing.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400 mt-0.5">🔄</span>
                <p>
                  <strong className="text-white/70">Snapshot Loop</strong> takes a fresh snapshot after
                  every action to see the updated page state.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-amber-400 mt-0.5">⌨️</span>
                <p>
                  <strong className="text-white/70">Desktop Fallback</strong> uses keyboard/mouse only
                  for native apps that aren't in the browser.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

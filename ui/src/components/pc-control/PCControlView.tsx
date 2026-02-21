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

const CAPABILITY_ICONS: Record<string, string> = {
  mouse: "🖱️",
  keyboard: "⌨️",
  screen: "🖥️",
  windows: "🪟",
  workflows: "⚡",
};

const CAPABILITY_COLORS: Record<string, string> = {
  mouse: "from-blue-500/20 to-blue-600/10 border-blue-500/30",
  keyboard: "from-emerald-500/20 to-emerald-600/10 border-emerald-500/30",
  screen: "from-purple-500/20 to-purple-600/10 border-purple-500/30",
  windows: "from-amber-500/20 to-amber-600/10 border-amber-500/30",
  workflows: "from-pink-500/20 to-pink-600/10 border-pink-500/30",
};

const OP_DESCRIPTIONS: Record<string, string> = {
  move: "Move cursor smoothly to a position",
  click: "Click at a position",
  double_click: "Double-click at a position",
  right_click: "Right-click for context menu",
  drag: "Drag from one point to another",
  scroll: "Scroll up or down",
  hover: "Hover to trigger tooltips",
  type: "Type text naturally",
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
  active_window: "Get the focused window",
  run_workflow: "Run a saved workflow",
  save_workflow: "Save a new workflow",
  list_workflows: "List all workflows",
  list_templates: "List workflow templates",
  get_template: "Get a template's details",
  delete_workflow: "Delete a saved workflow",
  smart_click: "Find text on screen and click it",
  smart_click_near: "Click near a text label",
  type_into: "Find a field by label and type into it",
};

export default function PCControlView() {
  const [capabilities, setCapabilities] = useState<Record<string, Capability>>({});
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([]);
  const [workflows, setWorkflows] = useState<SavedWorkflow[]>([]);
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [available, setAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expandedCap, setExpandedCap] = useState<string | null>(null);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [shortcutSearch, setShortcutSearch] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, shortcutsRes, workflowsRes] = await Promise.all([
        api.getPCStatus().catch(() => ({ available: false, capabilities: {} })),
        api.getPCShortcuts().catch(() => ({ shortcuts: [] })),
        api.getPCWorkflows().catch(() => ({ workflows: [], templates: [] })),
      ]);

      setAvailable(statusRes.available ?? false);
      setCapabilities(statusRes.capabilities ?? {});

      // Defensive: ensure shortcuts is always an array of objects
      const rawShortcuts = shortcutsRes.shortcuts;
      if (Array.isArray(rawShortcuts)) {
        setShortcuts(rawShortcuts);
      } else if (rawShortcuts && typeof rawShortcuts === "object") {
        // Convert dict {name: keys} to array [{name, keys, description}]
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

      // Defensive: ensure workflows and templates are arrays
      setWorkflows(Array.isArray(workflowsRes.workflows) ? workflowsRes.workflows : []);
      setTemplates(Array.isArray(workflowsRes.templates) ? workflowsRes.templates : []);
    } catch {
      setAvailable(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-blue-600/20 via-purple-600/15 to-pink-600/20 border border-white/10 rounded-2xl p-8">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-2xl shadow-lg">
            👻
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Computer Use</h1>
            <p className="text-white/60 text-sm">
              Plutus sees your screen, moves the mouse, types on the keyboard, and controls your PC
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

        {/* See → Think → Act → Verify loop */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-4 gap-3">
          {[
            { step: "1", label: "See", desc: "Screenshot to see the screen", color: "text-blue-400" },
            { step: "2", label: "Think", desc: "Find buttons/text with OCR", color: "text-purple-400" },
            { step: "3", label: "Act", desc: "Click, type, or use shortcuts", color: "text-pink-400" },
            { step: "4", label: "Verify", desc: "Screenshot again to confirm", color: "text-emerald-400" },
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

      {/* Quick Start — go to chat */}
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

      {/* Capability Cards */}
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
                <div className="mt-4 space-y-1.5 border-t border-white/10 pt-3">
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

          {/* If no capabilities loaded, show static cards */}
          {Object.keys(capabilities).length === 0 && (
            <>
              {[
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

      {/* Keyboard Shortcuts Section */}
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
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl overflow-hidden">
            <div className="p-3 border-b border-white/10">
              <input
                type="text"
                placeholder="Search shortcuts..."
                value={shortcutSearch}
                onChange={(e) => setShortcutSearch(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50"
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
                        <kbd className="text-white/70 text-xs bg-white/10 px-2 py-0.5 rounded border border-white/10 font-mono">
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
                    className="bg-white/5 border border-white/10 rounded-lg p-2.5 text-center hover:bg-white/10 transition-colors"
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

      {/* Workflows Section */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white/90">Workflows</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-5">
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

          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-5">
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

      {/* How it works */}
      <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-white/90 mb-4">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-blue-400">Just tell Plutus what to do</h3>
            <div className="space-y-1.5">
              {[
                '"Open Chrome and go to google.com"',
                '"Click the Submit button"',
                '"Take a screenshot and tell me what you see"',
                '"Snap VS Code to the left and Chrome to the right"',
                '"Type my email address into the login field"',
                '"Create a new folder on the desktop called Projects"',
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
                <span className="text-blue-400 mt-0.5">🖱️</span>
                <p>
                  <strong className="text-white/70">Mouse</strong> moves along smooth bezier curves
                  — no teleporting. Looks natural.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-emerald-400 mt-0.5">⌨️</span>
                <p>
                  <strong className="text-white/70">Keyboard</strong> types at natural speed with
                  slight randomization. 37+ cross-platform shortcuts.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400 mt-0.5">🖥️</span>
                <p>
                  <strong className="text-white/70">Screen</strong> uses OCR to read text and find
                  UI elements — no hardcoded coordinates.
                </p>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-amber-400 mt-0.5">🪟</span>
                <p>
                  <strong className="text-white/70">Windows</strong> can snap, tile, resize, and
                  focus any application.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

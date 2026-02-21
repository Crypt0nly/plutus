import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

// ── Category icons & colors ──
const CATEGORY_META: Record<string, { icon: string; color: string; bg: string; border: string }> = {
  messaging:     { icon: "💬", color: "text-green-400",   bg: "bg-green-500/10",   border: "border-green-500/20" },
  calendar:      { icon: "📅", color: "text-blue-400",    bg: "bg-blue-500/10",    border: "border-blue-500/20" },
  email:         { icon: "📧", color: "text-cyan-400",    bg: "bg-cyan-500/10",    border: "border-cyan-500/20" },
  music:         { icon: "🎵", color: "text-pink-400",    bg: "bg-pink-500/10",    border: "border-pink-500/20" },
  files:         { icon: "📁", color: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20" },
  browser:       { icon: "🌐", color: "text-indigo-400",  bg: "bg-indigo-500/10",  border: "border-indigo-500/20" },
  productivity:  { icon: "⚡", color: "text-yellow-400",  bg: "bg-yellow-500/10",  border: "border-yellow-500/20" },
  social:        { icon: "👥", color: "text-violet-400",  bg: "bg-violet-500/10",  border: "border-violet-500/20" },
  development:   { icon: "💻", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  system:        { icon: "⚙️", color: "text-gray-400",    bg: "bg-gray-500/10",    border: "border-gray-500/20" },
  custom:        { icon: "🧩", color: "text-rose-400",    bg: "bg-rose-500/10",    border: "border-rose-500/20" },
};

const DEFAULT_META = { icon: "📦", color: "text-white/60", bg: "bg-white/5", border: "border-white/10" };

function getMeta(cat: string) {
  return CATEGORY_META[cat] || DEFAULT_META;
}

// ── Skill type ──
interface Skill {
  name: string;
  description: string;
  app: string;
  category: string;
  triggers: string[];
  required_params: string[];
  optional_params: string[];
  steps_count?: number;
  dynamic?: boolean;
  version?: number;
  reason?: string;
  steps?: any[];
}

// ── Main Component ──
export default function SkillsView() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [savedSkills, setSavedSkills] = useState<Skill[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCat, setSelectedCat] = useState("all");
  const [search, setSearch] = useState("");
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"browse" | "my-skills" | "import" | "community">("browse");
  const [importText, setImportText] = useState("");
  const [importStatus, setImportStatus] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [exportingSkill, setExportingSkill] = useState<string | null>(null);
  const [exportedJson, setExportedJson] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchSkills = useCallback(async () => {
    try {
      const [allRes, savedRes] = await Promise.all([
        api.getSkills().catch(() => ({ skills: [], categories: [] })),
        api.getSavedSkills().catch(() => ({ skills: [] })),
      ]);
      const allSkills = Array.isArray(allRes.skills) ? allRes.skills : [];
      const cats = Array.isArray(allRes.categories) ? allRes.categories : [];
      const saved = Array.isArray(savedRes.skills) ? savedRes.skills : [];
      setSkills(allSkills);
      setCategories(cats);
      setSavedSkills(saved);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  // Filter skills
  const filteredSkills = skills.filter((s) => {
    const matchesCat = selectedCat === "all" || s.category === selectedCat;
    const matchesSearch =
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.description.toLowerCase().includes(search.toLowerCase()) ||
      s.app.toLowerCase().includes(search.toLowerCase()) ||
      s.triggers.some((t) => t.toLowerCase().includes(search.toLowerCase()));
    return matchesCat && matchesSearch;
  });

  // Import handler
  const handleImport = async (jsonStr: string) => {
    setImportStatus(null);
    try {
      const data = JSON.parse(jsonStr);
      const res = await api.importSkill(data);
      setImportStatus({ type: "success", msg: res.message || `Imported skill: ${res.skill_name}` });
      setImportText("");
      fetchSkills();
    } catch (e: any) {
      setImportStatus({ type: "error", msg: e.message || "Invalid JSON or import failed" });
    }
  };

  // File upload handler
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setImportText(text);
      handleImport(text);
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  // Export handler
  const handleExport = async (skillName: string) => {
    setExportingSkill(skillName);
    setExportedJson(null);
    try {
      const pkg = await api.exportSkill(skillName);
      setExportedJson(JSON.stringify(pkg, null, 2));
    } catch (e: any) {
      setExportedJson(`Error: ${e.message}`);
    }
  };

  // Delete handler
  const handleDelete = async (skillName: string) => {
    try {
      await api.deleteSkill(skillName);
      fetchSkills();
    } catch {
      // ignore
    }
  };

  // Copy to clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const tabs = [
    { id: "browse" as const, label: "Browse All", icon: "🔍", count: skills.length },
    { id: "my-skills" as const, label: "My Skills", icon: "⭐", count: savedSkills.length },
    { id: "import" as const, label: "Import / Upload", icon: "📥" },
    { id: "community" as const, label: "Community", icon: "🌍" },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Hero */}
      <div className="bg-gradient-to-br from-violet-600/10 via-purple-600/5 to-fuchsia-600/10 border border-violet-500/20 rounded-2xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <span className="text-3xl">🧠</span> Skills
            </h1>
            <p className="text-white/50 text-sm mt-1 max-w-xl">
              Skills are step-by-step recipes that teach Plutus how to use apps on your computer.
              Browse built-in skills, import community skills, or let Plutus create new ones automatically.
            </p>
          </div>
          <div className="flex gap-3">
            <div className="text-center">
              <div className="text-2xl font-bold text-violet-400">{skills.length}</div>
              <div className="text-white/30 text-[10px]">Total</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-emerald-400">{savedSkills.length}</div>
              <div className="text-white/30 text-[10px]">Custom</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-amber-400">{categories.length}</div>
              <div className="text-white/30 text-[10px]">Categories</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-[#0f0f1a] border border-white/10 rounded-xl p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "bg-violet-500/20 text-violet-400 border border-violet-500/30"
                : "text-white/40 hover:text-white/60 hover:bg-white/5 border border-transparent"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-white/5">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* ── Browse Tab ── */}
      {activeTab === "browse" && (
        <div className="space-y-4">
          {/* Search & Filter */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills by name, app, or trigger..."
                className="w-full bg-[#1a1a2e] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-violet-500/50"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 text-xs"
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          {/* Category pills */}
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setSelectedCat("all")}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                selectedCat === "all"
                  ? "bg-violet-500/20 text-violet-400 border border-violet-500/30"
                  : "bg-white/5 text-white/40 border border-white/10 hover:bg-white/10"
              }`}
            >
              All ({skills.length})
            </button>
            {categories.map((cat) => {
              const meta = getMeta(cat);
              const count = skills.filter((s) => s.category === cat).length;
              return (
                <button
                  key={cat}
                  onClick={() => setSelectedCat(cat)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize flex items-center gap-1.5 ${
                    selectedCat === cat
                      ? `${meta.bg} ${meta.color} border ${meta.border}`
                      : "bg-white/5 text-white/40 border border-white/10 hover:bg-white/10"
                  }`}
                >
                  {meta.icon} {cat} ({count})
                </button>
              );
            })}
          </div>

          {/* Skills Grid */}
          {loading ? (
            <div className="text-center py-12 text-white/30">Loading skills...</div>
          ) : filteredSkills.length === 0 ? (
            <div className="text-center py-12 text-white/30">
              <div className="text-3xl mb-2">🔍</div>
              No skills found matching your search.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredSkills.map((skill) => {
                const meta = getMeta(skill.category);
                const isExpanded = expandedSkill === skill.name;
                return (
                  <div
                    key={skill.name}
                    className={`bg-[#1a1a2e] border rounded-xl overflow-hidden transition-all cursor-pointer ${
                      isExpanded
                        ? `${meta.border} shadow-lg`
                        : "border-white/10 hover:border-white/20"
                    }`}
                    onClick={() => setExpandedSkill(isExpanded ? null : skill.name)}
                  >
                    <div className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2.5">
                          <span className={`text-xl w-8 h-8 rounded-lg ${meta.bg} flex items-center justify-center`}>
                            {meta.icon}
                          </span>
                          <div>
                            <h3 className="text-sm font-semibold text-white">{skill.app}</h3>
                            <code className="text-[10px] font-mono text-violet-400/70">{skill.name}</code>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {skill.dynamic && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400">Custom</span>
                          )}
                          <span className="text-white/20 text-xs">{isExpanded ? "▲" : "▼"}</span>
                        </div>
                      </div>
                      <p className="text-white/50 text-xs leading-relaxed">{skill.description}</p>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-white/10 p-4 bg-white/[0.02] space-y-3">
                        {/* Params */}
                        {skill.required_params.length > 0 && (
                          <div>
                            <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Required Parameters</div>
                            <div className="flex flex-wrap gap-1">
                              {skill.required_params.map((p) => (
                                <span key={p} className={`text-xs ${meta.bg} ${meta.color} px-2 py-0.5 rounded font-mono`}>
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

                        {/* Triggers */}
                        <div>
                          <div className="text-white/40 text-[10px] uppercase tracking-wider mb-1">Triggers</div>
                          <div className="flex flex-wrap gap-1">
                            {skill.triggers.slice(0, 6).map((t) => (
                              <span key={t} className="text-[10px] bg-white/5 text-white/30 px-1.5 py-0.5 rounded">
                                "{t}"
                              </span>
                            ))}
                            {skill.triggers.length > 6 && (
                              <span className="text-[10px] text-white/20">+{skill.triggers.length - 6} more</span>
                            )}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2 pt-1">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleExport(skill.name); }}
                            className="flex-1 text-xs py-1.5 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 transition-colors"
                          >
                            📤 Export
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              useAppStore.getState().setView("chat");
                            }}
                            className="flex-1 text-xs py-1.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                          >
                            💬 Try in Chat
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── My Skills Tab ── */}
      {activeTab === "my-skills" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-white/40 text-sm">
              Skills created by you or by Plutus during conversations. These are saved permanently on your machine.
            </p>
            <button
              onClick={() => setActiveTab("import")}
              className="text-xs px-3 py-1.5 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 transition-colors"
            >
              + Import Skill
            </button>
          </div>

          {savedSkills.length === 0 ? (
            <div className="text-center py-16 bg-[#1a1a2e] border border-white/10 rounded-xl">
              <div className="text-4xl mb-3">🌱</div>
              <h3 className="text-white/70 font-semibold mb-1">No custom skills yet</h3>
              <p className="text-white/30 text-sm max-w-md mx-auto">
                As you use Plutus, it will automatically create skills for tasks it learns.
                You can also import skills from the community or create them manually.
              </p>
              <div className="flex gap-3 justify-center mt-4">
                <button
                  onClick={() => setActiveTab("import")}
                  className="text-xs px-4 py-2 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20"
                >
                  📥 Import a Skill
                </button>
                <button
                  onClick={() => setActiveTab("community")}
                  className="text-xs px-4 py-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20"
                >
                  🌍 Browse Community
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {savedSkills.map((skill) => {
                const meta = getMeta(skill.category);
                return (
                  <div key={skill.name} className="bg-[#1a1a2e] border border-white/10 rounded-xl p-4 flex items-center gap-4">
                    <span className={`text-xl w-10 h-10 rounded-lg ${meta.bg} flex items-center justify-center flex-shrink-0`}>
                      {meta.icon}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-white">{skill.name}</h3>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-white/30">
                          v{skill.version || 1}
                        </span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded ${meta.bg} ${meta.color} capitalize`}>
                          {skill.category}
                        </span>
                      </div>
                      <p className="text-white/40 text-xs mt-0.5 truncate">{skill.description}</p>
                      {skill.reason && (
                        <p className="text-white/20 text-[10px] mt-0.5 italic">Created because: {skill.reason}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-white/20 text-xs">{skill.steps_count || "?"} steps</span>
                      <button
                        onClick={() => handleExport(skill.name)}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 transition-colors"
                      >
                        📤 Export
                      </button>
                      <button
                        onClick={() => handleDelete(skill.name)}
                        className="text-xs px-2.5 py-1.5 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Import Tab ── */}
      {activeTab === "import" && (
        <div className="space-y-6">
          {/* Upload File */}
          <div className="bg-[#1a1a2e] border border-dashed border-violet-500/30 rounded-xl p-8 text-center">
            <div className="text-4xl mb-3">📁</div>
            <h3 className="text-white/80 font-semibold mb-1">Upload a Skill File</h3>
            <p className="text-white/30 text-sm mb-4">
              Drop a <code className="text-violet-400/70">.json</code> skill file here or click to browse
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-6 py-2.5 rounded-xl bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 transition-colors text-sm font-medium"
            >
              Choose File
            </button>
          </div>

          {/* Paste JSON */}
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-6">
            <h3 className="text-white/80 font-semibold mb-1 flex items-center gap-2">
              <span>📋</span> Paste Skill JSON
            </h3>
            <p className="text-white/30 text-sm mb-3">
              Paste a skill JSON exported from another Plutus instance or from the community
            </p>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={`{
  "plutus_skill": true,
  "skill": {
    "name": "my_skill",
    "description": "What this skill does",
    "app": "MyApp",
    "category": "custom",
    "triggers": ["my trigger"],
    "required_params": ["param1"],
    "optional_params": [],
    "steps": [
      {
        "description": "Step 1",
        "operation": "open_app",
        "params": { "app_name": "{{param1}}" }
      }
    ]
  }
}`}
              className="w-full h-48 bg-[#0f0f1a] border border-white/10 rounded-xl p-4 text-xs font-mono text-white/70 placeholder-white/20 focus:outline-none focus:border-violet-500/50 resize-none"
            />
            <div className="flex items-center justify-between mt-3">
              <div>
                {importStatus && (
                  <div className={`text-xs px-3 py-1.5 rounded-lg ${
                    importStatus.type === "success"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-red-500/10 text-red-400 border border-red-500/20"
                  }`}>
                    {importStatus.type === "success" ? "✅" : "❌"} {importStatus.msg}
                  </div>
                )}
              </div>
              <button
                onClick={() => handleImport(importText)}
                disabled={!importText.trim()}
                className="px-5 py-2 rounded-xl bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 transition-colors text-sm font-medium disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Import Skill
              </button>
            </div>
          </div>

          {/* Skill Format Guide */}
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-6">
            <h3 className="text-white/80 font-semibold mb-3 flex items-center gap-2">
              <span>📖</span> Skill Format Guide
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="space-y-2">
                <div className="text-white/50 font-semibold">Required Fields</div>
                <div className="space-y-1">
                  {[
                    { field: "name", desc: "Unique identifier (snake_case)" },
                    { field: "description", desc: "What the skill does" },
                    { field: "steps", desc: "Array of step objects" },
                  ].map((f) => (
                    <div key={f.field} className="flex items-center gap-2">
                      <code className="text-violet-400/80 bg-violet-500/10 px-1.5 py-0.5 rounded">{f.field}</code>
                      <span className="text-white/30">{f.desc}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <div className="text-white/50 font-semibold">Optional Fields</div>
                <div className="space-y-1">
                  {[
                    { field: "app", desc: "App name (e.g., WhatsApp)" },
                    { field: "category", desc: "Category (messaging, calendar, etc.)" },
                    { field: "triggers", desc: "Keywords that activate this skill" },
                    { field: "required_params", desc: "Parameters the user must provide" },
                    { field: "optional_params", desc: "Parameters that are optional" },
                  ].map((f) => (
                    <div key={f.field} className="flex items-center gap-2">
                      <code className="text-blue-400/80 bg-blue-500/10 px-1.5 py-0.5 rounded">{f.field}</code>
                      <span className="text-white/30">{f.desc}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 text-white/30 text-xs">
              Each step needs: <code className="text-violet-400/60">operation</code> (like "open_app", "browser_click"),{" "}
              <code className="text-violet-400/60">description</code>, and{" "}
              <code className="text-violet-400/60">params</code>. Use <code className="text-amber-400/60">{"{{param_name}}"}</code> for dynamic values.
            </div>
          </div>
        </div>
      )}

      {/* ── Community Tab ── */}
      {activeTab === "community" && (
        <div className="space-y-6">
          {/* Community Hero */}
          <div className="bg-gradient-to-br from-blue-600/10 via-indigo-600/5 to-violet-600/10 border border-blue-500/20 rounded-2xl p-8 text-center">
            <div className="text-5xl mb-4">🌍</div>
            <h2 className="text-xl font-bold text-white mb-2">Plutus Skill Community</h2>
            <p className="text-white/40 text-sm max-w-lg mx-auto">
              Share your skills with other Plutus users and discover skills created by the community.
              Every skill you share helps make Plutus smarter for everyone.
            </p>
          </div>

          {/* How to Share */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-5">
              <div className="text-2xl mb-2">📤</div>
              <h3 className="text-white/80 font-semibold text-sm mb-1">Export & Share</h3>
              <p className="text-white/30 text-xs leading-relaxed">
                Go to <strong className="text-white/50">My Skills</strong>, click <strong className="text-violet-400">Export</strong> on any skill,
                and share the JSON file on GitHub, Discord, or any community platform.
              </p>
            </div>
            <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-5">
              <div className="text-2xl mb-2">📥</div>
              <h3 className="text-white/80 font-semibold text-sm mb-1">Import from Others</h3>
              <p className="text-white/30 text-xs leading-relaxed">
                Download a <code className="text-violet-400/60">.json</code> skill file from the community,
                then use the <strong className="text-white/50">Import</strong> tab to add it to your Plutus.
              </p>
            </div>
            <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-5">
              <div className="text-2xl mb-2">🤖</div>
              <h3 className="text-white/80 font-semibold text-sm mb-1">AI-Created Skills</h3>
              <p className="text-white/30 text-xs leading-relaxed">
                When Plutus creates a skill for you, it appears in <strong className="text-white/50">My Skills</strong>.
                Export it and share it so others can benefit from what your Plutus learned!
              </p>
            </div>
          </div>

          {/* Community Links */}
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-6">
            <h3 className="text-white/80 font-semibold mb-4 flex items-center gap-2">
              <span>🔗</span> Community Channels
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <a
                href="https://github.com/Crypt0nly/plutus/discussions"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/20 transition-colors group"
              >
                <span className="text-2xl">💬</span>
                <div>
                  <div className="text-white/70 text-sm font-semibold group-hover:text-white/90 transition-colors">
                    GitHub Discussions
                  </div>
                  <div className="text-white/30 text-xs">Share skills, ask questions, suggest features</div>
                </div>
              </a>
              <a
                href="https://github.com/Crypt0nly/plutus/tree/main/community-skills"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/20 transition-colors group"
              >
                <span className="text-2xl">📂</span>
                <div>
                  <div className="text-white/70 text-sm font-semibold group-hover:text-white/90 transition-colors">
                    Skill Repository
                  </div>
                  <div className="text-white/30 text-xs">Browse and download community-created skills</div>
                </div>
              </a>
              <a
                href="https://github.com/Crypt0nly/plutus/issues/new?template=skill-request.md"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/20 transition-colors group"
              >
                <span className="text-2xl">💡</span>
                <div>
                  <div className="text-white/70 text-sm font-semibold group-hover:text-white/90 transition-colors">
                    Request a Skill
                  </div>
                  <div className="text-white/30 text-xs">Can't find what you need? Request it from the community</div>
                </div>
              </a>
              <a
                href="https://github.com/Crypt0nly/plutus/blob/main/CONTRIBUTING.md"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 p-4 rounded-xl bg-white/[0.03] border border-white/10 hover:border-white/20 transition-colors group"
              >
                <span className="text-2xl">🤝</span>
                <div>
                  <div className="text-white/70 text-sm font-semibold group-hover:text-white/90 transition-colors">
                    Contributing Guide
                  </div>
                  <div className="text-white/30 text-xs">Learn how to contribute skills to the official repo</div>
                </div>
              </a>
            </div>
          </div>

          {/* Featured Skills Placeholder */}
          <div className="bg-[#1a1a2e] border border-white/10 rounded-xl p-6">
            <h3 className="text-white/80 font-semibold mb-3 flex items-center gap-2">
              <span>⭐</span> Featured Community Skills
            </h3>
            <p className="text-white/30 text-sm mb-4">
              Popular skills shared by the community. Click to import directly.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {[
                { name: "slack_send_message", app: "Slack", cat: "messaging", desc: "Send a message in any Slack channel or DM", author: "community" },
                { name: "notion_create_page", app: "Notion", cat: "productivity", desc: "Create a new page in Notion with title and content", author: "community" },
                { name: "zoom_join_meeting", app: "Zoom", cat: "communication", desc: "Join a Zoom meeting by meeting ID", author: "community" },
                { name: "twitter_post", app: "Twitter/X", cat: "social", desc: "Post a tweet from your account", author: "community" },
                { name: "google_docs_create", app: "Google Docs", cat: "productivity", desc: "Create a new Google Doc with content", author: "community" },
                { name: "youtube_search_play", app: "YouTube", cat: "media", desc: "Search YouTube and play the first result", author: "community" },
              ].map((s) => {
                const meta = getMeta(s.cat);
                return (
                  <div
                    key={s.name}
                    className="bg-white/[0.03] border border-white/10 rounded-xl p-4 hover:border-violet-500/30 transition-colors cursor-pointer group"
                    onClick={() => {
                      setActiveTab("import");
                      setImportText(JSON.stringify({
                        plutus_skill: true,
                        skill: {
                          name: s.name,
                          description: s.desc,
                          app: s.app,
                          category: s.cat,
                          triggers: [s.app.toLowerCase(), s.name.replace(/_/g, " ")],
                          required_params: [],
                          optional_params: [],
                          steps: [
                            { description: `Open ${s.app}`, operation: "open_app", params: { app_name: s.app } },
                          ],
                          reason: `Community skill for ${s.app}`,
                        },
                      }, null, 2));
                    }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-lg w-7 h-7 rounded-lg ${meta.bg} flex items-center justify-center`}>
                        {meta.icon}
                      </span>
                      <div>
                        <h4 className="text-xs font-semibold text-white/70 group-hover:text-white/90">{s.app}</h4>
                        <code className="text-[9px] text-violet-400/50">{s.name}</code>
                      </div>
                    </div>
                    <p className="text-white/30 text-[11px] leading-relaxed">{s.desc}</p>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-[9px] text-white/20">by {s.author}</span>
                      <span className="text-[9px] text-violet-400/50 opacity-0 group-hover:opacity-100 transition-opacity">
                        Click to import →
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Export Modal ── */}
      {exportingSkill && exportedJson && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-[#1a1a2e] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <div>
                <h3 className="text-white font-semibold">Export Skill</h3>
                <code className="text-violet-400/70 text-xs">{exportingSkill}</code>
              </div>
              <button
                onClick={() => { setExportingSkill(null); setExportedJson(null); }}
                className="text-white/30 hover:text-white/60 text-lg"
              >
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[50vh]">
              <pre className="text-xs font-mono text-white/60 bg-[#0f0f1a] rounded-xl p-4 overflow-x-auto">
                {exportedJson}
              </pre>
            </div>
            <div className="p-6 border-t border-white/10 flex gap-3">
              <button
                onClick={() => copyToClipboard(exportedJson)}
                className="flex-1 py-2.5 rounded-xl bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 transition-colors text-sm font-medium"
              >
                📋 Copy to Clipboard
              </button>
              <button
                onClick={() => {
                  const blob = new Blob([exportedJson], { type: "application/json" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `${exportingSkill}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="flex-1 py-2.5 rounded-xl bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 transition-colors text-sm font-medium"
              >
                💾 Download .json
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

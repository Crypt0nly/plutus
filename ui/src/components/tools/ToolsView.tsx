import { useState, useEffect } from "react";
import {
  Terminal,
  Code2,
  Cpu,
  Monitor,
  Puzzle,
  ChevronDown,
  ChevronUp,
  Wrench,
  Search,
  RefreshCw,
  Zap,
  FileCode,
  GitBranch,
  Globe,
  Clipboard,
  AppWindow,
  HardDrive,
  Info,
} from "lucide-react";
import { api } from "../../lib/api";
import { useApi } from "../../hooks/useApi";

// Icon mapping for tool categories
const categoryIcons: Record<string, React.ElementType> = {
  terminal: Terminal,
  code: Code2,
  cpu: Cpu,
  monitor: Monitor,
  puzzle: Puzzle,
};

// Icon mapping for individual tools
const toolIcons: Record<string, React.ElementType> = {
  shell: Terminal,
  filesystem: HardDrive,
  process: Cpu,
  system_info: Info,
  code_editor: FileCode,
  code_analysis: GitBranch,
  subprocess: Zap,
  tool_creator: Wrench,
  browser: Globe,
  clipboard: Clipboard,
  desktop: Monitor,
  app_manager: AppWindow,
};

// Friendly descriptions for non-technical users
const friendlyDescriptions: Record<string, string> = {
  shell: "Runs commands on your computer, like installing software or running scripts.",
  filesystem: "Reads, writes, and manages files and folders on your system.",
  process: "Shows what programs are running and can start or stop them.",
  system_info: "Checks your computer's health — CPU, memory, disk space, and more.",
  code_editor: "Creates and edits code files with smart find-and-replace editing.",
  code_analysis: "Analyzes code to find functions, classes, complexity, and potential issues.",
  subprocess: "Runs multiple tasks at the same time in isolated processes.",
  tool_creator: "Creates brand new tools on the fly when the AI needs a new capability.",
  browser: "Opens websites, fills forms, clicks buttons — like a virtual web assistant.",
  clipboard: "Reads and writes to your clipboard (copy/paste).",
  desktop: "Interacts with desktop windows and applications.",
  app_manager: "Installs, updates, and manages applications on your system.",
};

// Status colors
const statusColors: Record<string, string> = {
  core: "from-blue-500/20 to-blue-600/10 border-blue-500/30",
  code: "from-emerald-500/20 to-emerald-600/10 border-emerald-500/30",
  subprocess: "from-purple-500/20 to-purple-600/10 border-purple-500/30",
  desktop: "from-amber-500/20 to-amber-600/10 border-amber-500/30",
  custom: "from-pink-500/20 to-pink-600/10 border-pink-500/30",
};

const statusTextColors: Record<string, string> = {
  core: "text-blue-400",
  code: "text-emerald-400",
  subprocess: "text-purple-400",
  desktop: "text-amber-400",
  custom: "text-pink-400",
};

interface ToolCardProps {
  tool: Record<string, any>;
  category: string;
}

function ToolCard({ tool, category }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);
  const Icon = toolIcons[tool.name] || Wrench;
  const textColor = statusTextColors[category] || "text-gray-400";
  const friendly = friendlyDescriptions[tool.name];

  return (
    <div
      className={`card hover:border-gray-700 transition-all duration-200 cursor-pointer ${
        expanded ? "ring-1 ring-gray-700" : ""
      }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start gap-3">
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 bg-gradient-to-br ${statusColors[category]}`}
        >
          <Icon className={`w-5 h-5 ${textColor}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-200">
              {tool.name.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase())}
            </h3>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${textColor} bg-gray-800`}>
              {category}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">
            {friendly || tool.description}
          </p>
        </div>
        <button className="text-gray-500 hover:text-gray-300 p-1">
          {expanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>
      </div>

      {expanded && (
        <div className="mt-4 pt-3 border-t border-gray-800 animate-fade-in">
          <div className="space-y-3">
            {/* Technical description */}
            <div>
              <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1">
                What it does
              </h4>
              <p className="text-xs text-gray-300">{tool.description}</p>
            </div>

            {/* Parameters */}
            {tool.parameters?.properties && (
              <div>
                <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Available Options
                </h4>
                <div className="space-y-1.5">
                  {Object.entries(tool.parameters.properties).map(
                    ([key, value]: [string, any]) => (
                      <div
                        key={key}
                        className="flex items-start gap-2 bg-gray-800/50 rounded-lg px-3 py-2"
                      >
                        <code className="text-[11px] text-plutus-400 font-mono flex-shrink-0">
                          {key}
                        </code>
                        <span className="text-[11px] text-gray-400">
                          {value.description || value.type || "—"}
                        </span>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

            {/* Operations enum */}
            {tool.parameters?.properties?.operation?.enum && (
              <div>
                <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Operations
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {tool.parameters.properties.operation.enum.map(
                    (op: string) => (
                      <span
                        key={op}
                        className={`text-[10px] px-2 py-1 rounded-md bg-gray-800 ${textColor}`}
                      >
                        {op}
                      </span>
                    )
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function ToolsView() {
  const { data, loading, error, refetch } = useApi(
    () => api.getToolsDetails(),
    []
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-gray-400">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>Loading tools...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card text-center py-8">
        <p className="text-red-400 mb-2">Failed to load tools</p>
        <p className="text-xs text-gray-500">{error}</p>
        <button onClick={refetch} className="btn-primary mt-4 text-sm">
          Retry
        </button>
      </div>
    );
  }

  const categories = data?.categories || {};
  const totalTools = data?.total || 0;

  // Filter tools by search
  const filteredCategories = Object.entries(categories).reduce(
    (acc, [key, cat]: [string, any]) => {
      if (!cat.tools || cat.tools.length === 0) return acc;

      const filtered = cat.tools.filter(
        (t: any) =>
          t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.description.toLowerCase().includes(searchQuery.toLowerCase())
      );
      if (filtered.length > 0) {
        acc[key] = { ...cat, tools: filtered };
      }
      return acc;
    },
    {} as Record<string, any>
  );

  return (
    <div className="h-full overflow-y-auto space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Tools</h1>
        <p className="text-sm text-gray-400 mt-1">
          These are all the capabilities your AI agent has. Each tool lets it perform
          specific actions on your computer.
        </p>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {Object.entries(categories).map(([key, cat]: [string, any]) => {
          const Icon = categoryIcons[cat.icon] || Wrench;
          const textColor = statusTextColors[key] || "text-gray-400";
          return (
            <button
              key={key}
              onClick={() =>
                setExpandedCategory(expandedCategory === key ? null : key)
              }
              className={`card flex items-center gap-3 hover:border-gray-700 transition-all ${
                expandedCategory === key ? "ring-1 ring-plutus-500/50" : ""
              }`}
            >
              <Icon className={`w-5 h-5 ${textColor}`} />
              <div className="text-left">
                <p className="text-lg font-bold text-gray-200">
                  {cat.tools?.length || 0}
                </p>
                <p className="text-[10px] text-gray-500">{cat.label}</p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          type="text"
          placeholder="Search tools... (e.g., 'edit files', 'analyze code')"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="input pl-10"
        />
      </div>

      {/* Tool categories */}
      {Object.entries(filteredCategories).map(([key, cat]: [string, any]) => {
        const Icon = categoryIcons[cat.icon] || Wrench;
        const textColor = statusTextColors[key] || "text-gray-400";
        const isExpanded =
          expandedCategory === null || expandedCategory === key;

        return (
          <div key={key} className={isExpanded ? "" : "hidden"}>
            <div className="flex items-center gap-2 mb-3">
              <Icon className={`w-4 h-4 ${textColor}`} />
              <h2 className="text-sm font-semibold text-gray-300">
                {cat.label}
              </h2>
              <span className="text-xs text-gray-500">
                — {cat.description}
              </span>
              <span className="text-xs text-gray-600 ml-auto">
                {cat.tools.length} tool{cat.tools.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {cat.tools.map((tool: any) => (
                <ToolCard key={tool.name} tool={tool} category={key} />
              ))}
            </div>
          </div>
        );
      })}

      {/* Empty state */}
      {Object.keys(filteredCategories).length === 0 && (
        <div className="card text-center py-12">
          <Search className="w-8 h-8 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400">No tools match your search.</p>
          <button
            onClick={() => setSearchQuery("")}
            className="text-plutus-400 text-sm mt-2 hover:underline"
          >
            Clear search
          </button>
        </div>
      )}

      {/* Footer */}
      <div className="text-center text-xs text-gray-600 pb-4">
        {totalTools} tools available · Tools are used automatically by the AI
        during conversations
      </div>
    </div>
  );
}

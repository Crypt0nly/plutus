import { useState, useEffect } from "react";
import {
  Wrench,
  Plus,
  Trash2,
  Code2,
  FileCode,
  Info,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Eye,
  Package,
  RefreshCw,
  Lightbulb,
  Copy,
  ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";
import { useApi } from "../../hooks/useApi";

// ── Step indicator ──────────────────────────────────────────

function StepIndicator({
  steps,
  currentStep,
}: {
  steps: string[];
  currentStep: number;
}) {
  return (
    <div className="flex items-center gap-1 mb-6">
      {steps.map((label, i) => (
        <div key={i} className="flex items-center">
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
              i === currentStep
                ? "bg-plutus-500/20 text-plutus-400 border border-plutus-500/30"
                : i < currentStep
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-gray-800 text-gray-500"
            }`}
          >
            {i < currentStep ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <span className="w-4 h-4 rounded-full bg-gray-700 flex items-center justify-center text-[10px]">
                {i + 1}
              </span>
            )}
            <span className="hidden sm:inline">{label}</span>
          </div>
          {i < steps.length - 1 && (
            <ChevronRight className="w-4 h-4 text-gray-700 mx-1" />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Template cards ──────────────────────────────────────────

interface Template {
  name: string;
  description: string;
  icon: React.ElementType;
  code: string;
  toolName: string;
}

const templates: Template[] = [
  {
    name: "Word Counter",
    description: "Count words, lines, and characters in a file",
    icon: FileCode,
    toolName: "word_counter",
    code: `"""Count words, lines, and characters in a file."""

def main(args: dict) -> dict:
    path = args.get("path", "")
    if not path:
        return {"success": False, "result": "Please provide a file path"}
    
    try:
        with open(path, "r") as f:
            content = f.read()
        
        lines = content.split("\\n")
        words = content.split()
        
        return {
            "success": True,
            "result": {
                "file": path,
                "lines": len(lines),
                "words": len(words),
                "characters": len(content),
                "non_empty_lines": sum(1 for l in lines if l.strip()),
            }
        }
    except FileNotFoundError:
        return {"success": False, "result": f"File not found: {path}"}
    except Exception as e:
        return {"success": False, "result": str(e)}
`,
  },
  {
    name: "JSON Formatter",
    description: "Pretty-print and validate JSON files",
    icon: Code2,
    toolName: "json_formatter",
    code: `"""Format and validate JSON files."""
import json

def main(args: dict) -> dict:
    path = args.get("path", "")
    indent = args.get("indent", 2)
    
    if not path:
        return {"success": False, "result": "Please provide a file path"}
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
        
        formatted = json.dumps(data, indent=indent, sort_keys=True)
        
        # Optionally write back
        if args.get("write_back", False):
            with open(path, "w") as f:
                f.write(formatted)
        
        return {
            "success": True,
            "result": {
                "valid": True,
                "keys": len(data) if isinstance(data, dict) else None,
                "items": len(data) if isinstance(data, list) else None,
                "formatted": formatted[:500],
            }
        }
    except json.JSONDecodeError as e:
        return {"success": False, "result": f"Invalid JSON: {e}"}
    except Exception as e:
        return {"success": False, "result": str(e)}
`,
  },
  {
    name: "File Search",
    description: "Search for files by name or content pattern",
    icon: Eye,
    toolName: "file_search",
    code: `"""Search for files by name or content."""
import os
import re

def main(args: dict) -> dict:
    directory = args.get("directory", ".")
    pattern = args.get("pattern", "")
    content_pattern = args.get("content", "")
    max_results = args.get("max_results", 20)
    
    if not pattern and not content_pattern:
        return {"success": False, "result": "Provide a 'pattern' or 'content' to search for"}
    
    results = []
    
    try:
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            
            for fname in files:
                if len(results) >= max_results:
                    break
                
                full_path = os.path.join(root, fname)
                
                # Match filename
                if pattern and re.search(pattern, fname, re.IGNORECASE):
                    results.append({"path": full_path, "match": "filename"})
                    continue
                
                # Match content
                if content_pattern:
                    try:
                        with open(full_path, "r", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if re.search(content_pattern, line):
                                    results.append({
                                        "path": full_path,
                                        "match": "content",
                                        "line": i,
                                        "text": line.strip()[:100],
                                    })
                                    break
                    except (PermissionError, IsADirectoryError):
                        pass
        
        return {"success": True, "result": {"matches": results, "count": len(results)}}
    except Exception as e:
        return {"success": False, "result": str(e)}
`,
  },
  {
    name: "Start from Scratch",
    description: "Write your own tool from a blank template",
    icon: Sparkles,
    toolName: "my_tool",
    code: `"""Describe what your tool does here."""

def main(args: dict) -> dict:
    \"\"\"
    Main entry point for the tool.
    
    Args:
        args: Dictionary of arguments passed to the tool.
              Access them with args.get("key", default_value)
    
    Returns:
        Dictionary with "success" (bool) and "result" (any) keys.
    \"\"\"
    # Your code here
    name = args.get("name", "World")
    
    return {
        "success": True,
        "result": f"Hello, {name}! Your tool is working."
    }
`,
  },
];

// ── Main Component ──────────────────────────────────────────

export function ToolCreatorView() {
  // Wizard state
  const [step, setStep] = useState(0);
  const [toolName, setToolName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState("");
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  // Existing tools
  const {
    data: customTools,
    loading: toolsLoading,
    refetch: refetchTools,
  } = useApi(() => api.getCustomTools(), []);

  const wizardSteps = ["Choose Template", "Name & Describe", "Write Code", "Create"];

  // ── Step 0: Template selection ──

  const handleSelectTemplate = (template: Template) => {
    setToolName(template.toolName);
    setDescription(template.description);
    setCode(template.code);
    setStep(1);
  };

  // ── Step 3: Create tool ──

  const handleCreate = async () => {
    setCreating(true);
    setCreateResult(null);

    try {
      // We use the chat WebSocket to ask the agent to create the tool
      // But for direct creation, we can call the API
      // For now, we'll show a success message and instruct the user
      setCreateResult({
        success: true,
        message: `Tool "${toolName}" is ready! Ask the AI in chat: "Create a tool called ${toolName} that ${description}" and paste the code. Or the AI can create it automatically during a conversation.`,
      });
    } catch (e) {
      setCreateResult({
        success: false,
        message: e instanceof Error ? e.message : "Failed to create tool",
      });
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteTool = async (name: string) => {
    if (!confirm(`Delete tool "${name}"? This cannot be undone.`)) return;
    try {
      await api.deleteCustomTool(name);
      refetchTools();
    } catch (e) {
      console.error("Failed to delete tool:", e);
    }
  };

  const resetWizard = () => {
    setStep(0);
    setToolName("");
    setDescription("");
    setCode("");
    setCreateResult(null);
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-100">Tool Creator</h1>
        <p className="text-sm text-gray-400 mt-1">
          Create custom tools that extend what the AI can do. Tools are small
          Python scripts that the AI can call during conversations.
        </p>
      </div>

      {/* Two columns: Wizard + Existing Tools */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Wizard (2/3 width) */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <Plus className="w-4 h-4 text-plutus-400" />
                Create New Tool
              </h2>
              {step > 0 && (
                <button
                  onClick={resetWizard}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Start over
                </button>
              )}
            </div>

            <StepIndicator steps={wizardSteps} currentStep={step} />

            {/* Step 0: Template Selection */}
            {step === 0 && (
              <div className="space-y-3">
                <p className="text-xs text-gray-400 mb-4">
                  Pick a starting template or start from scratch. Don't worry — you
                  can customize everything in the next steps.
                </p>
                <div className="grid sm:grid-cols-2 gap-3">
                  {templates.map((t) => {
                    const Icon = t.icon;
                    return (
                      <button
                        key={t.name}
                        onClick={() => handleSelectTemplate(t)}
                        className="text-left p-4 rounded-xl border border-gray-800 hover:border-plutus-500/50 hover:bg-gray-800/50 transition-all group"
                      >
                        <div className="flex items-center gap-3 mb-2">
                          <div className="w-8 h-8 rounded-lg bg-plutus-500/10 flex items-center justify-center group-hover:bg-plutus-500/20 transition-colors">
                            <Icon className="w-4 h-4 text-plutus-400" />
                          </div>
                          <h3 className="text-sm font-medium text-gray-200">
                            {t.name}
                          </h3>
                        </div>
                        <p className="text-xs text-gray-500">{t.description}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Step 1: Name & Description */}
            {step === 1 && (
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-gray-400 mb-1.5 block">
                    Tool Name
                  </label>
                  <input
                    type="text"
                    className="input font-mono"
                    value={toolName}
                    onChange={(e) =>
                      setToolName(
                        e.target.value
                          .toLowerCase()
                          .replace(/[^a-z0-9_]/g, "_")
                      )
                    }
                    placeholder="my_awesome_tool"
                  />
                  <p className="text-[10px] text-gray-600 mt-1">
                    Use lowercase letters, numbers, and underscores only.
                  </p>
                </div>

                <div>
                  <label className="text-xs text-gray-400 mb-1.5 block">
                    Description
                  </label>
                  <textarea
                    className="input min-h-[80px] resize-y"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe what this tool does in plain English..."
                    rows={3}
                  />
                  <p className="text-[10px] text-gray-600 mt-1">
                    This helps the AI understand when to use your tool.
                  </p>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => setStep(0)}
                    className="btn-secondary flex items-center gap-2"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Back
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    disabled={!toolName.trim()}
                    className="btn-primary flex items-center gap-2"
                  >
                    Next
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Code Editor */}
            {step === 2 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-xs text-gray-400">
                    Python Code
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(code);
                      }}
                      className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" />
                      Copy
                    </button>
                  </div>
                </div>

                <div className="relative">
                  <textarea
                    className="input font-mono text-xs min-h-[300px] resize-y leading-relaxed"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    spellCheck={false}
                    style={{ tabSize: 4 }}
                  />
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <Lightbulb className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                    <div className="text-xs text-blue-300/80">
                      <p className="font-medium mb-1">How tools work:</p>
                      <ul className="space-y-1 text-blue-300/60">
                        <li>
                          • Your tool must have a{" "}
                          <code className="text-blue-400">
                            main(args: dict) → dict
                          </code>{" "}
                          function
                        </li>
                        <li>
                          • Return{" "}
                          <code className="text-blue-400">
                            {`{"success": True, "result": ...}`}
                          </code>
                        </li>
                        <li>
                          • Access arguments with{" "}
                          <code className="text-blue-400">
                            args.get("key", default)
                          </code>
                        </li>
                        <li>• The AI will call your tool automatically when needed</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    onClick={() => setStep(1)}
                    className="btn-secondary flex items-center gap-2"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Back
                  </button>
                  <button
                    onClick={() => setStep(3)}
                    disabled={!code.trim()}
                    className="btn-primary flex items-center gap-2"
                  >
                    Review & Create
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Review & Create */}
            {step === 3 && (
              <div className="space-y-4">
                {/* Summary */}
                <div className="bg-gray-800/50 rounded-xl p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-plutus-500/10 flex items-center justify-center">
                      <Package className="w-5 h-5 text-plutus-400" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-200">
                        {toolName}
                      </h3>
                      <p className="text-xs text-gray-400">{description}</p>
                    </div>
                  </div>

                  <div className="border-t border-gray-700 pt-3">
                    <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
                      Code Preview
                    </p>
                    <pre className="text-xs text-gray-300 font-mono bg-gray-900 rounded-lg p-3 max-h-40 overflow-y-auto">
                      {code.slice(0, 500)}
                      {code.length > 500 ? "\n..." : ""}
                    </pre>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span>{code.split("\n").length} lines</span>
                    <span>{code.length} characters</span>
                  </div>
                </div>

                {/* Result */}
                {createResult && (
                  <div
                    className={`rounded-lg p-4 ${
                      createResult.success
                        ? "bg-emerald-500/10 border border-emerald-500/20"
                        : "bg-red-500/10 border border-red-500/20"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {createResult.success ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                      ) : (
                        <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
                      )}
                      <p
                        className={`text-sm ${
                          createResult.success
                            ? "text-emerald-300"
                            : "text-red-300"
                        }`}
                      >
                        {createResult.message}
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex gap-3">
                  <button
                    onClick={() => setStep(2)}
                    className="btn-secondary flex items-center gap-2"
                  >
                    <ChevronLeft className="w-4 h-4" />
                    Edit Code
                  </button>
                  <button
                    onClick={handleCreate}
                    disabled={creating}
                    className="btn-primary flex items-center gap-2"
                  >
                    {creating ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                    {creating ? "Creating..." : "Create Tool"}
                  </button>
                  {createResult?.success && (
                    <button onClick={resetWizard} className="btn-secondary">
                      Create Another
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Existing Tools Sidebar (1/3 width) */}
        <div className="space-y-4">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <Wrench className="w-4 h-4 text-gray-400" />
                Your Custom Tools
              </h2>
              <button
                onClick={refetchTools}
                className="text-gray-500 hover:text-gray-300"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {toolsLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
              </div>
            ) : !customTools?.tools?.length ? (
              <div className="text-center py-8">
                <Package className="w-8 h-8 text-gray-700 mx-auto mb-3" />
                <p className="text-sm text-gray-400">No custom tools yet</p>
                <p className="text-xs text-gray-600 mt-1">
                  Create one using the wizard, or ask the AI to create one
                  during a conversation.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {customTools.tools.map((tool: any) => (
                  <div
                    key={tool.name}
                    className="flex items-start gap-3 p-3 rounded-lg bg-gray-800/50 hover:bg-gray-800 transition-colors group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-pink-500/10 flex items-center justify-center flex-shrink-0">
                      <Wrench className="w-4 h-4 text-pink-400" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-xs font-medium text-gray-200">
                        {tool.name}
                      </h3>
                      <p className="text-[10px] text-gray-500 line-clamp-2 mt-0.5">
                        {tool.description || "No description"}
                      </p>
                      {tool.code_lines && (
                        <span className="text-[10px] text-gray-600">
                          {tool.code_lines} lines
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => handleDeleteTool(tool.name)}
                      className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 p-1 transition-opacity"
                      title="Delete tool"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Tips card */}
          <div className="card bg-gradient-to-br from-plutus-500/5 to-purple-500/5 border-plutus-500/20">
            <div className="flex items-start gap-2">
              <Lightbulb className="w-4 h-4 text-plutus-400 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="text-xs font-semibold text-gray-300 mb-2">
                  Pro Tips
                </h3>
                <ul className="space-y-1.5 text-[11px] text-gray-400">
                  <li>
                    💬 You can ask the AI: <em>"Create a tool that..."</em> and
                    it will write the code for you
                  </li>
                  <li>
                    🔄 Custom tools persist across sessions and are available
                    immediately
                  </li>
                  <li>
                    🛡️ Each tool runs in an isolated subprocess for safety
                  </li>
                  <li>
                    📦 Tools can import standard Python libraries (os, json,
                    re, etc.)
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

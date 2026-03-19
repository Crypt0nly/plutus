import { useState } from "react";
import {
  Bot,
  Terminal,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileCode,
  GitBranch,
  Zap,
  Wrench,
  CheckCircle2,
  XCircle,
  Clock,
  Copy,
  Check,
  Code2,
  FileEdit,
  FileDown,
  Search,
  Play,
  Monitor,
  Camera,
  Minimize2,
  Maximize2,
  Send,
  Cpu,
  Heart,
  Info,
} from "lucide-react";
import type { Message } from "../../lib/types";
import { ToolApproval } from "./ToolApproval";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface Props {
  message: Message;
  send: (data: Record<string, unknown>) => void;
}

const toolIconMap: Record<string, React.ElementType> = {
  code_editor: FileEdit,
  code_analysis: GitBranch,
  subprocess: Zap,
  tool_creator: Wrench,
  shell: Terminal,
  filesystem: FileCode,
  browser: Search,
  pc: Monitor,
  connector: Send,
};

const toolColorMap: Record<string, { icon: string; bg: string; border: string }> = {
  code_editor: { icon: "#34d399", bg: "rgba(16, 185, 129, 0.06)", border: "rgba(16, 185, 129, 0.12)" },
  code_analysis: { icon: "#60a5fa", bg: "rgba(59, 130, 246, 0.06)", border: "rgba(59, 130, 246, 0.12)" },
  subprocess: { icon: "#a78bfa", bg: "rgba(139, 92, 246, 0.06)", border: "rgba(139, 92, 246, 0.12)" },
  tool_creator: { icon: "#f472b6", bg: "rgba(236, 72, 153, 0.06)", border: "rgba(236, 72, 153, 0.12)" },
  shell: { icon: "#fbbf24", bg: "rgba(245, 158, 11, 0.06)", border: "rgba(245, 158, 11, 0.12)" },
  filesystem: { icon: "#22d3ee", bg: "rgba(6, 182, 212, 0.06)", border: "rgba(6, 182, 212, 0.12)" },
  pc: { icon: "#60a5fa", bg: "rgba(59, 130, 246, 0.06)", border: "rgba(59, 130, 246, 0.12)" },
  connector: { icon: "#a78bfa", bg: "rgba(139, 92, 246, 0.06)", border: "rgba(139, 92, 246, 0.12)" },
};

const defaultToolColor = { icon: "#9ca3af", bg: "rgba(107, 114, 128, 0.06)", border: "rgba(107, 114, 128, 0.12)" };

const operationLabels: Record<string, string> = {
  read: "Reading file", write: "Writing file", edit: "Editing file",
  append: "Appending to file", delete: "Deleting file", move: "Moving file",
  copy: "Copying file", find: "Finding files", grep: "Searching in files",
  diff: "Comparing files", list: "Listing directory", mkdir: "Creating directory",
  analyze: "Analyzing code", find_functions: "Finding functions",
  find_classes: "Finding classes", find_imports: "Finding imports",
  complexity: "Checking complexity", summarize: "Summarizing code",
  call_graph: "Building call graph", find_todos: "Finding TODOs",
  symbols: "Listing symbols", spawn: "Running subprocess",
  spawn_many: "Running parallel tasks", create: "Creating tool",
  validate: "Validating tool", run: "Running tool",
  open_app: "Opening app", close_app: "Closing app", open_url: "Opening URL",
  shell_exec: "Running command", list_processes: "Listing processes",
  system_info: "Getting system info", snapshot: "Reading page elements",
  click_ref: "Clicking element", type_ref: "Typing into element",
  select_ref: "Selecting option", check_ref: "Toggling checkbox",
  hover_ref: "Hovering element", navigate: "Navigating to URL",
  browser_back: "Going back", browser_forward: "Going forward",
  browser_refresh: "Refreshing page", new_tab: "Opening new tab",
  close_tab: "Closing tab", switch_tab: "Switching tab",
  list_tabs: "Listing tabs", page_content: "Reading page content",
  scroll_page: "Scrolling page", keyboard_type: "Typing text",
  keyboard_press: "Pressing key", keyboard_shortcut: "Using shortcut",
  mouse_click: "Clicking", mouse_move: "Moving mouse",
  take_screenshot: "Taking screenshot", send: "Sending message",
  send_file: "Sending file", run_skill: "Running skill",
  list_skills: "Listing skills", create_skill: "Creating skill",
  update_skill: "Updating skill", delete_skill: "Deleting skill",
};

function ToolCallCard({ name, args }: { name: string; args: Record<string, unknown>; id: string }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = toolIconMap[name] || Terminal;
  const colors = toolColorMap[name] || defaultToolColor;

  const operation = args.operation as string | undefined;
  const action = args.action as string | undefined;

  const friendlyLabel = operation
    ? operationLabels[operation] || operation.replace(/_/g, " ")
    : action
      ? operationLabels[action] || action.replace(/_/g, " ")
      : name.replace(/_/g, " ");

  const path = (args.path || args.file_path || args.directory || "") as string;
  const command = (args.command || "") as string;
  const text = (args.text || args.value || "") as string;
  const ref = args.ref as number | undefined;
  const url = (args.url || "") as string;
  const appName = (args.app_name || "") as string;
  const skillName = (args.skill_name || "") as string;

  let preview = "";
  if (ref !== undefined) {
    preview = `[ref=${ref}]`;
    if (text) preview += ` "${text.slice(0, 30)}${text.length > 30 ? "..." : ""}"`;
  } else if (url) {
    preview = url.length > 50 ? url.slice(0, 47) + "..." : url;
  } else if (appName) {
    preview = appName;
  } else if (skillName) {
    preview = skillName;
  } else if (path) {
    preview = path.length > 50 ? "..." + path.slice(-47) : path;
  } else if (command) {
    preview = `$ ${command.slice(0, 50)}`;
  } else if (text) {
    preview = text.length > 40 ? `"${text.slice(0, 37)}..."` : `"${text}"`;
  }

  return (
    <div className="rounded-xl overflow-hidden transition-all"
      style={{ border: `1px solid ${colors.border}` }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3.5 py-2.5 transition-all"
        style={{ background: colors.bg }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.filter = "brightness(1.15)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.filter = "";
        }}
      >
        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: colors.icon }} />
        <div className="flex-1 text-left min-w-0">
          <span className="text-xs font-medium capitalize" style={{ color: colors.icon }}>{friendlyLabel}</span>
          {preview && (
            <span className="text-[11px] text-gray-600 ml-2 font-mono truncate">{preview}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-gray-700 animate-pulse" />
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-gray-600" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-gray-600" />
          )}
        </div>
      </button>
      {expanded && (
        <div className="px-3.5 py-3 animate-fade-in"
          style={{
            background: "rgb(var(--surface-deep) / 0.8)",
            borderTop: `1px solid ${colors.border}`
          }}
        >
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Parameters</p>
          <div className="space-y-1.5">
            {Object.entries(args).map(([key, value]) => (
              <div key={key} className="flex items-start gap-2">
                <span className="text-[11px] text-gray-600 font-mono w-20 flex-shrink-0">{key}</span>
                <span className="text-[11px] text-gray-400 font-mono break-all">
                  {typeof value === "string"
                    ? value.length > 200 ? value.slice(0, 200) + "..." : value
                    : JSON.stringify(value, null, 2).slice(0, 200)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ScreenshotDisplay({ base64 }: { base64: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: "rgba(8, 10, 20, 0.8)", border: "1px solid rgba(59, 130, 246, 0.15)" }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3.5 py-2 transition-colors"
        style={{ background: "rgba(59, 130, 246, 0.06)" }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.filter = "brightness(1.2)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.filter = ""; }}
      >
        <div className="flex items-center gap-2">
          <Camera className="w-3.5 h-3.5 text-blue-400" />
          <span className="text-xs font-medium text-blue-400">Screenshot</span>
        </div>
        {expanded ? <Minimize2 className="w-3.5 h-3.5 text-gray-500" /> : <Maximize2 className="w-3.5 h-3.5 text-gray-500" />}
      </button>
      <div className={`transition-all duration-300 ${expanded ? "max-h-[600px]" : "max-h-48"} overflow-hidden`}>
        <img src={`data:image/png;base64,${base64}`} alt="Screenshot" className="w-full h-auto cursor-pointer" onClick={() => setExpanded(!expanded)} />
      </div>
    </div>
  );
}

function AttachmentImageDisplay({ base64, fileName, caption }: { base64: string; fileName: string; caption: string }) {
  const [expanded, setExpanded] = useState(false);
  const ext = fileName.split(".").pop()?.toLowerCase() || "png";
  const mime = ext === "jpg" || ext === "jpeg" ? "image/jpeg" : ext === "gif" ? "image/gif" : ext === "webp" ? "image/webp" : "image/png";

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: "rgb(var(--surface-deep) / 0.8)", border: "1px solid rgba(139, 92, 246, 0.15)" }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3.5 py-2 transition-colors"
        style={{ background: "rgba(139, 92, 246, 0.06)" }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.filter = "brightness(1.2)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.filter = ""; }}
      >
        <div className="flex items-center gap-2">
          <Camera className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-xs font-medium text-violet-400">{caption || fileName}</span>
        </div>
        {expanded ? <Minimize2 className="w-3.5 h-3.5 text-gray-500" /> : <Maximize2 className="w-3.5 h-3.5 text-gray-500" />}
      </button>
      <div className={`transition-all duration-300 ${expanded ? "max-h-[600px]" : "max-h-48"} overflow-hidden`}>
        <img src={`data:${mime};base64,${base64}`} alt={caption || fileName} className="w-full h-auto cursor-pointer" onClick={() => setExpanded(!expanded)} />
      </div>
    </div>
  );
}

function AttachmentFileDisplay({ fileName, sizeKB, filePath, caption }: { fileName: string; sizeKB: string; filePath: string; caption: string }) {
  const sizeLabel = parseInt(sizeKB) >= 1024 ? `${(parseInt(sizeKB) / 1024).toFixed(1)} MB` : `${sizeKB} KB`;
  const downloadUrl = `/api/files?path=${encodeURIComponent(filePath)}`;

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: "rgb(var(--surface-deep) / 0.8)", border: "1px solid rgb(var(--gray-700) / 0.4)" }}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgb(var(--gray-700) / 0.4)" }}
        >
          <FileDown className="w-5 h-5 text-gray-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-200 truncate">{fileName}</p>
          <p className="text-xs text-gray-500">{sizeLabel}{caption ? ` — ${caption}` : ""}</p>
        </div>
        <a
          href={downloadUrl}
          download={fileName}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-200 transition-colors hover:bg-gray-700/50"
          style={{ background: "rgb(var(--gray-800) / 0.6)", border: "1px solid rgb(var(--gray-700) / 0.4)" }}
        >
          <FileDown className="w-3.5 h-3.5" /> Download
        </a>
      </div>
    </div>
  );
}

function SnapshotDisplay({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const lines = content.split("\n");
  const previewLines = lines.slice(0, 15);
  const hasMore = lines.length > 15;

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderLine = (line: string, i: number) => {
    const refMatch = line.match(/\[ref=(\d+)\]/);
    const indent = line.match(/^(\s*)/)?.[1]?.length || 0;
    let typeColor = "text-gray-400";
    if (line.includes("button")) typeColor = "text-violet-400";
    else if (line.includes("link")) typeColor = "text-blue-400";
    else if (line.includes("textbox") || line.includes("input") || line.includes("textarea")) typeColor = "text-emerald-400";
    else if (line.includes("heading")) typeColor = "text-amber-400";
    else if (line.includes("img") || line.includes("image")) typeColor = "text-pink-400";
    else if (line.includes("checkbox") || line.includes("radio")) typeColor = "text-cyan-400";
    else if (line.includes("select") || line.includes("combobox")) typeColor = "text-orange-400";

    if (refMatch) {
      const refNum = refMatch[1];
      const beforeRef = line.slice(0, line.indexOf("[ref="));
      const afterRef = line.slice(line.indexOf("]") + 1);
      return (
        <div key={i} className={`${typeColor} whitespace-pre hover:bg-white/5 px-1 rounded`} style={{ paddingLeft: `${indent * 8 + 4}px` }}>
          {beforeRef.trim()}
          <span className="bg-blue-500/15 text-blue-300 px-1 rounded font-bold text-[10px] mx-1">ref={refNum}</span>
          {afterRef}
        </div>
      );
    }
    return (
      <div key={i} className={`${typeColor} whitespace-pre px-1`} style={{ paddingLeft: `${indent * 8 + 4}px` }}>{line.trim()}</div>
    );
  };

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: "rgb(var(--surface-deep) / 0.8)", border: "1px solid rgba(59, 130, 246, 0.15)" }}
    >
      <div className="flex items-center justify-between px-3.5 py-2"
        style={{ background: "rgba(59, 130, 246, 0.06)", borderBottom: "1px solid rgba(59, 130, 246, 0.1)" }}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-blue-400">Accessibility Tree</span>
          <span className="text-[10px] text-gray-500">{lines.length} elements</span>
        </div>
        <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300 transition-colors">
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
      <div className="py-2 text-xs font-mono overflow-x-auto max-h-80 overflow-y-auto">
        {(expanded ? lines : previewLines).map((line, i) => renderLine(line, i))}
      </div>
      {hasMore && (
        <button onClick={() => setExpanded(!expanded)}
          className="w-full px-3.5 py-2 text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
          style={{ background: "rgba(59, 130, 246, 0.04)", borderTop: "1px solid rgba(59, 130, 246, 0.1)" }}
        >
          {expanded ? "Show less" : `Show all ${lines.length} elements`}
        </button>
      )}
    </div>
  );
}

function ToolResultContent({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  if (content.startsWith("__SCREENSHOT__:")) return <ScreenshotDisplay base64={content.replace("__SCREENSHOT__:", "")} />;

  if (content.startsWith("__ATTACHMENT_IMAGE__:")) {
    const rest = content.replace("__ATTACHMENT_IMAGE__:", "");
    const firstColon = rest.indexOf(":");
    const fileName = rest.slice(0, firstColon);
    const remaining = rest.slice(firstColon + 1);
    const newlineIdx = remaining.indexOf("\n");
    const base64 = newlineIdx >= 0 ? remaining.slice(0, newlineIdx) : remaining;
    const caption = newlineIdx >= 0 ? remaining.slice(newlineIdx + 1) : "";
    return <AttachmentImageDisplay base64={base64} fileName={fileName} caption={caption} />;
  }

  if (content.startsWith("__ATTACHMENT_FILE__:")) {
    const rest = content.replace("__ATTACHMENT_FILE__:", "");
    const parts = rest.split(":");
    const fileName = parts[0] || "file";
    const sizeKB = parts[1] || "0";
    const pathAndCaption = parts.slice(2).join(":");
    const dashIdx = pathAndCaption.indexOf(" — ");
    const filePath = dashIdx >= 0 ? pathAndCaption.slice(0, dashIdx) : pathAndCaption;
    const caption = dashIdx >= 0 ? pathAndCaption.slice(dashIdx + 3) : "";
    return <AttachmentFileDisplay fileName={fileName} sizeKB={sizeKB} filePath={filePath} caption={caption} />;
  }

  const isSnapshot = content.includes("[ref=") && (content.includes("button") || content.includes("link") || content.includes("textbox") || content.includes("heading"));
  if (isSnapshot) return <SnapshotDisplay content={content} />;

  const isLong = content.length > 300;
  const isDiff = content.includes("@@") || content.includes("--- ") || content.includes("+++ ");
  const isJson = content.trim().startsWith("{") || content.trim().startsWith("[");
  const isError = content.startsWith("[ERROR]") || content.toLowerCase().includes("error:");

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const headerStyle = { background: "rgb(var(--surface-alt) / 0.8)", borderBottom: "1px solid rgb(var(--gray-700) / 0.3)" };
  const containerStyle = { background: "rgb(var(--surface-deep) / 0.8)", border: "1px solid rgb(var(--gray-700) / 0.4)" };

  if (isDiff) {
    return (
      <div className="rounded-xl overflow-hidden" style={containerStyle}>
        <div className="flex items-center justify-between px-3.5 py-2" style={headerStyle}>
          <div className="flex items-center gap-2">
            <Code2 className="w-3.5 h-3.5 text-gray-500" />
            <span className="text-[11px] font-medium text-gray-400">File Changes</span>
          </div>
          <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300 transition-colors">
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
        <pre className="px-3.5 py-2.5 text-xs font-mono overflow-x-auto max-h-64 overflow-y-auto">
          {content.split("\n").map((line, i) => {
            let lineClass = "text-gray-400";
            if (line.startsWith("+") && !line.startsWith("+++")) lineClass = "text-emerald-400 bg-emerald-500/5";
            else if (line.startsWith("-") && !line.startsWith("---")) lineClass = "text-red-400 bg-red-500/5";
            else if (line.startsWith("@@")) lineClass = "text-blue-400";
            else if (line.startsWith("---") || line.startsWith("+++")) lineClass = "text-gray-500 font-bold";
            return <div key={i} className={`${lineClass} px-1 whitespace-pre-wrap`}>{line}</div>;
          })}
        </pre>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl px-4 py-3"
        style={{ background: "rgba(239, 68, 68, 0.05)", border: "1px solid rgba(239, 68, 68, 0.15)" }}
      >
        <div className="flex items-start gap-2">
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <pre className="text-xs text-red-300 font-mono whitespace-pre-wrap">{content}</pre>
        </div>
      </div>
    );
  }

  if (isJson) {
    let parsed: unknown;
    try { parsed = JSON.parse(content); } catch { parsed = null; }
    if (parsed) {
      const displayContent = JSON.stringify(parsed, null, 2);
      const showContent = expanded ? displayContent : displayContent.slice(0, 300);
      return (
        <div className="rounded-xl overflow-hidden" style={containerStyle}>
          <div className="flex items-center justify-between px-3.5 py-2" style={headerStyle}>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[11px] font-medium text-gray-400">Result</span>
            </div>
            <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300 transition-colors">
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
          <pre className="px-3.5 py-2.5 text-xs font-mono text-gray-300 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
            {showContent}{!expanded && displayContent.length > 300 && "..."}
          </pre>
          {displayContent.length > 300 && (
            <button onClick={() => setExpanded(!expanded)}
              className="w-full px-3.5 py-2 text-[11px] text-gray-400 hover:text-gray-200 transition-colors"
              style={{ background: "rgb(var(--surface-alt) / 0.5)", borderTop: "1px solid rgb(var(--gray-700) / 0.3)" }}
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      );
    }
  }

  const showContent = expanded ? content : content.slice(0, 300);
  return (
    <div className="rounded-xl overflow-hidden" style={containerStyle}>
      <div className="flex items-center justify-between px-3.5 py-2" style={headerStyle}>
        <div className="flex items-center gap-2">
          <Play className="w-3.5 h-3.5 text-gray-500" />
          <span className="text-[11px] font-medium text-gray-400">Output</span>
        </div>
        <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300 transition-colors">
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
      <pre className="px-3.5 py-2.5 text-xs font-mono text-gray-300 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
        {showContent}{!expanded && isLong && "..."}
      </pre>
      {isLong && (
        <button onClick={() => setExpanded(!expanded)}
          className="w-full px-3.5 py-2 text-[11px] text-gray-400 hover:text-gray-200 transition-colors"
          style={{ background: "rgb(var(--surface-alt) / 0.5)", borderTop: "1px solid rgb(var(--gray-700) / 0.3)" }}
        >
          {expanded ? "Show less" : `Show more (${content.length} chars)`}
        </button>
      )}
    </div>
  );
}

export function MessageBubble({ message, send }: Props) {
  const { role, content, tool_calls } = message;

  // ── User message ──
  if (role === "user") {
    return (
      <div className="flex justify-end py-2 animate-slide-up">
        <div className="max-w-xl">
          <div className="px-4 py-3 rounded-2xl rounded-br-lg text-sm leading-relaxed text-white"
            style={{
              background: "linear-gradient(135deg, #6366f1, #4f46e5)",
              boxShadow: "0 4px 16px rgba(99, 102, 241, 0.25)"
            }}
          >
            {content}
          </div>
        </div>
      </div>
    );
  }

  // ── Assistant message ──
  if (role === "assistant") {
    const safeContent = typeof content === "string" ? content : String(content || "");

    // Worker result
    if (safeContent.startsWith("__WORKER_RESULT__:")) {
      const rest = safeContent.replace("__WORKER_RESULT__:", "");
      const firstColon = rest.indexOf(":");
      const workerName = firstColon >= 0 ? rest.slice(0, firstColon) : "Worker";
      const afterName = firstColon >= 0 ? rest.slice(firstColon + 1) : rest;
      const secondColon = afterName.indexOf(":");
      const workerModel = secondColon >= 0 ? afterName.slice(0, secondColon) : "";
      const workerResult = secondColon >= 0 ? afterName.slice(secondColon + 1) : afterName;

      return (
        <div className="py-2 animate-slide-up">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
              style={{
                background: "rgba(245, 158, 11, 0.1)",
                border: "1px solid rgba(245, 158, 11, 0.2)"
              }}
            >
              <Cpu className="w-3.5 h-3.5 text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-semibold text-amber-300">{workerName}</span>
                {workerModel && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-md font-mono"
                    style={{ background: "rgba(245, 158, 11, 0.1)", color: "rgba(251, 191, 36, 0.7)" }}
                  >{workerModel}</span>
                )}
              </div>
              <div className="text-sm leading-relaxed text-gray-200">
                <MarkdownRenderer content={workerResult} />
              </div>
            </div>
          </div>
        </div>
      );
    }

    // Standard assistant
    return (
      <div className="py-2 animate-slide-up message-container">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{
              background: "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(79, 70, 229, 0.08))",
              border: "1px solid rgba(99, 102, 241, 0.15)"
            }}
          >
            <Bot className="w-3.5 h-3.5" style={{ color: "#818cf8" }} />
          </div>
          <div className="flex-1 min-w-0">
            {content && (
              <div className="text-sm leading-relaxed text-gray-200">
                <MarkdownRenderer content={typeof content === "string" ? content : String(content)} />
              </div>
            )}
            {tool_calls && tool_calls.length > 0 && (
              <div className={`${content ? "mt-3" : ""} space-y-2`}>
                {tool_calls.map((tc) => (
                  <ToolCallCard key={tc.id} name={tc.name} args={tc.arguments} id={tc.id} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Tool result ──
  if (role === "tool") {
    return (
      <div className="py-1 pl-11 animate-fade-in">
        <ToolResultContent content={content || ""} />
      </div>
    );
  }

  // ── System messages ──
  if (role === "system") {
    if (content?.startsWith("Approval needed")) {
      return <ToolApproval message={content} send={send} approvalId={message.approval_id ?? undefined} />;
    }

    if (content?.includes("Computer Use mode") || content?.includes("Standard mode")) {
      const isComputerUse = content.includes("Computer Use mode");
      return (
        <div className="flex items-center justify-center py-2 animate-fade-in">
          <div className="px-3 py-1.5 rounded-full text-[11px] font-medium flex items-center gap-1.5"
            style={isComputerUse ? {
              background: "rgba(59, 130, 246, 0.08)",
              color: "#60a5fa",
              border: "1px solid rgba(59, 130, 246, 0.15)"
            } : {
              background: "rgba(16, 185, 129, 0.08)",
              color: "#34d399",
              border: "1px solid rgba(16, 185, 129, 0.15)"
            }}
          >
            {isComputerUse ? <Monitor className="w-3 h-3" /> : <Terminal className="w-3 h-3" />}
            {content}
          </div>
        </div>
      );
    }

    if (typeof content === "string" && content.startsWith("__WORKER_STARTED__:")) {
      const rest = content.replace("__WORKER_STARTED__:", "");
      const colonIdx = rest.indexOf(":");
      const wName = colonIdx >= 0 ? rest.slice(0, colonIdx) : rest;
      const wModel = colonIdx >= 0 ? rest.slice(colonIdx + 1) : "";
      return (
        <div className="flex items-center justify-center py-2 animate-fade-in">
          <div className="px-3 py-1.5 rounded-full text-[11px] font-medium flex items-center gap-2"
            style={{ background: "rgba(245, 158, 11, 0.07)", color: "rgba(251, 191, 36, 0.8)", border: "1px solid rgba(245, 158, 11, 0.12)" }}
          >
            <Cpu className="w-3 h-3" />
            <span>Worker <strong>{wName}</strong> dispatched</span>
            <span className="text-[10px] font-mono" style={{ color: "rgba(251, 191, 36, 0.5)" }}>{wModel}</span>
          </div>
        </div>
      );
    }

    if (typeof content === "string" && content.startsWith("[HEARTBEAT]")) {
      return (
        <div className="flex items-center justify-center py-2 animate-fade-in">
          <div className="px-3 py-1.5 rounded-full text-[11px] font-medium flex items-center gap-1.5"
            style={{ background: "rgba(239, 68, 68, 0.07)", color: "rgba(252, 165, 165, 0.8)", border: "1px solid rgba(239, 68, 68, 0.12)" }}
          >
            <Heart className="w-3 h-3" /><span>Heartbeat</span>
          </div>
        </div>
      );
    }

    if (typeof content === "string" && content.startsWith("[SYSTEM NOTIFICATION]")) {
      const notifText = content.replace("[SYSTEM NOTIFICATION]\n", "").replace("[SYSTEM NOTIFICATION]", "").trim();
      return (
        <div className="flex items-center justify-center py-2 animate-fade-in">
          <div className="px-3 py-1.5 rounded-full text-[11px] font-medium flex items-center gap-1.5 max-w-lg truncate"
            style={{ background: "rgba(59, 130, 246, 0.07)", color: "rgba(147, 197, 253, 0.8)", border: "1px solid rgba(59, 130, 246, 0.12)" }}
          >
            <Info className="w-3 h-3 shrink-0" /><span className="truncate">{notifText || "System notification"}</span>
          </div>
        </div>
      );
    }

    if (typeof content === "string" && content.startsWith("[SYSTEM]")) {
      const sysText = content.replace("[SYSTEM]", "").trim();
      return (
        <div className="flex items-center justify-center py-2 animate-fade-in">
          <div className="px-3 py-1.5 rounded-full text-[11px] font-medium flex items-center gap-1.5 max-w-lg"
            style={{ background: "rgba(107, 114, 128, 0.07)", color: "rgba(156, 163, 175, 0.8)", border: "1px solid rgba(107, 114, 128, 0.12)" }}
          >
            <Info className="w-3 h-3 shrink-0" /><span className="truncate">{sysText}</span>
          </div>
        </div>
      );
    }

    if (content?.startsWith("Step ")) {
      return (
        <div className="flex items-center justify-center py-1 animate-fade-in">
          <span className="text-[10px] text-gray-700 font-mono">{content}</span>
        </div>
      );
    }

    return (
      <div className="flex items-center justify-center gap-2 py-2 animate-fade-in">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs text-gray-500">{content}</span>
      </div>
    );
  }

  return null;
}

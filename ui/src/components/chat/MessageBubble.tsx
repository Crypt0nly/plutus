import { useState } from "react";
import {
  User,
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
  MousePointer,
  Keyboard,
  Camera,
  Move,
  Hand,
  Scroll,
  Timer,
  Maximize2,
  Minimize2,
} from "lucide-react";
import type { Message } from "../../lib/types";
import { ToolApproval } from "./ToolApproval";

interface Props {
  message: Message;
  send: (data: Record<string, unknown>) => void;
}

// ── Tool icon mapping ───────────────────────────────────────

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

const toolColorMap: Record<string, string> = {
  code_editor: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  code_analysis: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  subprocess: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  tool_creator: "text-pink-400 bg-pink-500/10 border-pink-500/20",
  shell: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  filesystem: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  pc: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  connector: "text-purple-400 bg-purple-500/10 border-purple-500/20",
};

// ── Friendly operation labels ───────────────────────────────

const operationLabels: Record<string, string> = {
  // File operations
  read: "Reading file",
  write: "Writing file",
  edit: "Editing file",
  append: "Appending to file",
  delete: "Deleting file",
  move: "Moving file",
  copy: "Copying file",
  find: "Finding files",
  grep: "Searching in files",
  diff: "Comparing files",
  list: "Listing directory",
  mkdir: "Creating directory",
  // Code analysis
  analyze: "Analyzing code",
  find_functions: "Finding functions",
  find_classes: "Finding classes",
  find_imports: "Finding imports",
  complexity: "Checking complexity",
  summarize: "Summarizing code",
  call_graph: "Building call graph",
  find_todos: "Finding TODOs",
  symbols: "Listing symbols",
  // Subprocess
  spawn: "Running subprocess",
  spawn_many: "Running parallel tasks",
  create: "Creating tool",
  validate: "Validating tool",
  run: "Running tool",
  // PC Control — OS
  open_app: "Opening app",
  close_app: "Closing app",
  open_url: "Opening URL",
  shell_exec: "Running command",
  list_processes: "Listing processes",
  system_info: "Getting system info",
  // PC Control — Browser (accessibility tree)
  snapshot: "Reading page elements",
  click_ref: "Clicking element",
  type_ref: "Typing into element",
  select_ref: "Selecting option",
  check_ref: "Toggling checkbox",
  hover_ref: "Hovering element",
  navigate: "Navigating to URL",
  browser_back: "Going back",
  browser_forward: "Going forward",
  browser_refresh: "Refreshing page",
  new_tab: "Opening new tab",
  close_tab: "Closing tab",
  switch_tab: "Switching tab",
  list_tabs: "Listing tabs",
  page_content: "Reading page content",
  scroll_page: "Scrolling page",
  // PC Control — Desktop fallback
  keyboard_type: "Typing text",
  keyboard_press: "Pressing key",
  keyboard_shortcut: "Using shortcut",
  mouse_click: "Clicking",
  mouse_move: "Moving mouse",
  take_screenshot: "Taking screenshot",
  // Connectors
  send: "Sending message",
  send_file: "Sending file",
  // Skills
  run_skill: "Running skill",
  list_skills: "Listing skills",
  create_skill: "Creating skill",
  update_skill: "Updating skill",
  delete_skill: "Deleting skill",
};

// ── Tool Call Card ──────────────────────────────────────────

function ToolCallCard({
  name,
  args,
  id,
}: {
  name: string;
  args: Record<string, unknown>;
  id: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const Icon = toolIconMap[name] || Terminal;
  const colors = toolColorMap[name] || "text-gray-400 bg-gray-500/10 border-gray-500/20";
  const [iconColor, bgColor, borderColor] = colors.split(" ");

  const operation = args.operation as string | undefined;
  const action = args.action as string | undefined;

  let friendlyLabel: string;
  friendlyLabel = operation
    ? operationLabels[operation] || operation.replace(/_/g, " ")
    : action
      ? operationLabels[action] || action.replace(/_/g, " ")
      : name.replace(/_/g, " ");

  // Extract key info for preview
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
    <div
      className={`border rounded-lg overflow-hidden transition-all ${borderColor} ${
        expanded ? "ring-1 ring-gray-700" : ""
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center gap-3 px-3 py-2.5 ${bgColor} hover:opacity-90 transition-opacity`}
      >
        <Icon className={`w-4 h-4 ${iconColor} flex-shrink-0`} />
        <div className="flex-1 text-left min-w-0">
          <span className={`text-xs font-medium ${iconColor}`}>
            {friendlyLabel}
          </span>
          {preview && (
            <span className="text-[10px] text-gray-500 ml-2 font-mono truncate">
              {preview}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-gray-600 animate-pulse" />
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 py-2.5 bg-gray-900/50 border-t border-gray-800 animate-fade-in">
          <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
            Parameters
          </p>
          <div className="space-y-1">
            {Object.entries(args).map(([key, value]) => (
              <div key={key} className="flex items-start gap-2">
                <span className="text-[10px] text-gray-500 font-mono w-20 flex-shrink-0">
                  {key}:
                </span>
                <span className="text-[10px] text-gray-300 font-mono break-all">
                  {typeof value === "string"
                    ? value.length > 200
                      ? value.slice(0, 200) + "..."
                      : value
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

// ── Screenshot Display ─────────────────────────────────────

function ScreenshotDisplay({ base64 }: { base64: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-900 border border-blue-500/20 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-blue-500/10 hover:bg-blue-500/15 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Camera className="w-3.5 h-3.5 text-blue-400" />
          <span className="text-xs font-medium text-blue-400">Screenshot</span>
        </div>
        {expanded ? (
          <Minimize2 className="w-3.5 h-3.5 text-gray-500" />
        ) : (
          <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
        )}
      </button>
      <div className={`transition-all duration-300 ${expanded ? "max-h-[600px]" : "max-h-48"} overflow-hidden`}>
        <img
          src={`data:image/png;base64,${base64}`}
          alt="Screenshot"
          className="w-full h-auto cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        />
      </div>
    </div>
  );
}
// ── Attachment Displays ───────────────────────────────────────────

function AttachmentImageDisplay({
  base64,
  fileName,
  caption,
}: {
  base64: string;
  fileName: string;
  caption: string;
}) {
  const [expanded, setExpanded] = useState(false);

  // Detect format from file extension
  const ext = fileName.split(".").pop()?.toLowerCase() || "png";
  const mime = ext === "jpg" || ext === "jpeg" ? "image/jpeg"
    : ext === "gif" ? "image/gif"
    : ext === "webp" ? "image/webp"
    : "image/png";

  return (
    <div className="bg-gray-900 border border-purple-500/20 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-purple-500/10 hover:bg-purple-500/15 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Camera className="w-3.5 h-3.5 text-purple-400" />
          <span className="text-xs font-medium text-purple-400">
            {caption || fileName}
          </span>
        </div>
        {expanded ? (
          <Minimize2 className="w-3.5 h-3.5 text-gray-500" />
        ) : (
          <Maximize2 className="w-3.5 h-3.5 text-gray-500" />
        )}
      </button>
      <div className={`transition-all duration-300 ${expanded ? "max-h-[600px]" : "max-h-48"} overflow-hidden`}>
        <img
          src={`data:${mime};base64,${base64}`}
          alt={caption || fileName}
          className="w-full h-auto cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        />
      </div>
    </div>
  );
}

function AttachmentFileDisplay({
  fileName,
  sizeKB,
  filePath,
  caption,
}: {
  fileName: string;
  sizeKB: string;
  filePath: string;
  caption: string;
}) {
  const sizeLabel = parseInt(sizeKB) >= 1024
    ? `${(parseInt(sizeKB) / 1024).toFixed(1)} MB`
    : `${sizeKB} KB`;

  const downloadUrl = `/api/files?path=${encodeURIComponent(filePath)}`;

  return (
    <div className="bg-gray-900 border border-gray-700/50 rounded-lg overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="w-10 h-10 rounded-lg bg-gray-800 flex items-center justify-center flex-shrink-0">
          <FileDown className="w-5 h-5 text-gray-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-200 truncate">{fileName}</p>
          <p className="text-xs text-gray-500">
            {sizeLabel}
            {caption ? ` — ${caption}` : ""}
          </p>
        </div>
        <a
          href={downloadUrl}
          download={fileName}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs font-medium transition-colors"
        >
          <FileDown className="w-3.5 h-3.5" />
          Download
        </a>
      </div>
    </div>
  );
}

// ── Accessibility Tree Snapshot Display ───────────────────────────

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
    // Highlight [ref=N] markers
    const refMatch = line.match(/\[ref=(\d+)\]/);
    const indent = line.match(/^(\s*)/)?.[1]?.length || 0;

    // Determine element type for coloring
    let typeColor = "text-gray-400";
    if (line.includes("button")) typeColor = "text-purple-400";
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
          <span className="bg-blue-500/20 text-blue-300 px-1 rounded font-bold text-[10px] mx-1">
            ref={refNum}
          </span>
          {afterRef}
        </div>
      );
    }

    return (
      <div key={i} className={`${typeColor} whitespace-pre px-1`} style={{ paddingLeft: `${indent * 8 + 4}px` }}>
        {line.trim()}
      </div>
    );
  };

  const displayLines = expanded ? lines : previewLines;

  return (
    <div className="bg-gray-900 border border-blue-500/20 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-blue-500/10 border-b border-blue-800">
        <div className="flex items-center gap-2">
          <span className="text-blue-400 text-sm">🌳</span>
          <span className="text-[10px] font-medium text-blue-400">Accessibility Tree</span>
          <span className="text-[10px] text-gray-500">{lines.length} elements</span>
        </div>
        <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300">
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
      <div className="py-2 text-xs font-mono overflow-x-auto max-h-80 overflow-y-auto">
        {displayLines.map((line, i) => renderLine(line, i))}
      </div>
      {hasMore && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full px-3 py-1.5 text-[10px] text-blue-400 hover:text-blue-300 bg-blue-500/5 border-t border-blue-800"
        >
          {expanded ? "Show less" : `Show all ${lines.length} elements`}
        </button>
      )}
    </div>
  );
}

// ── Tool Result Card ────────────────────────────────────────

function ToolResultContent({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // Check if this is a screenshot
  if (content.startsWith("__SCREENSHOT__:")) {
    const base64 = content.replace("__SCREENSHOT__:", "");
    return <ScreenshotDisplay base64={base64} />;
  }

  // Check if this is an image attachment
  if (content.startsWith("__ATTACHMENT_IMAGE__:")) {
    const rest = content.replace("__ATTACHMENT_IMAGE__:", "");
    const firstColon = rest.indexOf(":");
    const fileName = rest.slice(0, firstColon);
    const remaining = rest.slice(firstColon + 1);
    // Caption is after a newline, if present
    const newlineIdx = remaining.indexOf("\n");
    const base64 = newlineIdx >= 0 ? remaining.slice(0, newlineIdx) : remaining;
    const caption = newlineIdx >= 0 ? remaining.slice(newlineIdx + 1) : "";
    return <AttachmentImageDisplay base64={base64} fileName={fileName} caption={caption} />;
  }

  // Check if this is a file attachment
  if (content.startsWith("__ATTACHMENT_FILE__:")) {
    const rest = content.replace("__ATTACHMENT_FILE__:", "");
    const parts = rest.split(":");
    const fileName = parts[0] || "file";
    const sizeKB = parts[1] || "0";
    // file_path may contain colons (e.g. C:\...), and caption is after " — "
    const pathAndCaption = parts.slice(2).join(":");
    const dashIdx = pathAndCaption.indexOf(" — ");
    const filePath = dashIdx >= 0 ? pathAndCaption.slice(0, dashIdx) : pathAndCaption;
    const caption = dashIdx >= 0 ? pathAndCaption.slice(dashIdx + 3) : "";
    return <AttachmentFileDisplay fileName={fileName} sizeKB={sizeKB} filePath={filePath} caption={caption} />;
  }

  // Check if this is an accessibility tree snapshot
  const isSnapshot = content.includes("[ref=") && (content.includes("button") || content.includes("link") || content.includes("textbox") || content.includes("heading"));
  if (isSnapshot) {
    return <SnapshotDisplay content={content} />;
  }

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

  // Render diff with syntax highlighting
  if (isDiff) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800/50 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Code2 className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-[10px] font-medium text-gray-400">
              File Changes
            </span>
          </div>
          <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300">
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>
        <pre className="px-3 py-2 text-xs font-mono overflow-x-auto max-h-64 overflow-y-auto">
          {content.split("\n").map((line, i) => {
            let lineClass = "text-gray-400";
            if (line.startsWith("+") && !line.startsWith("+++")) lineClass = "text-emerald-400 bg-emerald-500/5";
            else if (line.startsWith("-") && !line.startsWith("---")) lineClass = "text-red-400 bg-red-500/5";
            else if (line.startsWith("@@")) lineClass = "text-blue-400";
            else if (line.startsWith("---") || line.startsWith("+++")) lineClass = "text-gray-500 font-bold";

            return (
              <div key={i} className={`${lineClass} px-1 whitespace-pre-wrap`}>
                {line}
              </div>
            );
          })}
        </pre>
      </div>
    );
  }

  // Render error
  if (isError) {
    return (
      <div className="bg-red-500/5 border border-red-500/20 rounded-lg px-4 py-3">
        <div className="flex items-start gap-2">
          <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
          <pre className="text-xs text-red-300 font-mono whitespace-pre-wrap">{content}</pre>
        </div>
      </div>
    );
  }

  // Render JSON
  if (isJson) {
    let parsed: any;
    try {
      parsed = JSON.parse(content);
    } catch {
      parsed = null;
    }

    if (parsed) {
      const displayContent = JSON.stringify(parsed, null, 2);
      const showContent = expanded ? displayContent : displayContent.slice(0, 300);

      return (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800/50 border-b border-gray-800">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[10px] font-medium text-gray-400">
                Result
              </span>
            </div>
            <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300">
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
          <pre className="px-3 py-2 text-xs font-mono text-gray-300 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
            {showContent}
            {!expanded && displayContent.length > 300 && "..."}
          </pre>
          {displayContent.length > 300 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="w-full px-3 py-1.5 text-[10px] text-gray-500 hover:text-gray-300 bg-gray-800/30 border-t border-gray-800"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      );
    }
  }

  // Default rendering
  const showContent = expanded ? content : content.slice(0, 300);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-800/50 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <Play className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-[10px] font-medium text-gray-400">Output</span>
        </div>
        <button onClick={handleCopy} className="text-gray-500 hover:text-gray-300">
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
      <pre className="px-3 py-2 text-xs font-mono text-gray-300 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
        {showContent}
        {!expanded && isLong && "..."}
      </pre>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full px-3 py-1.5 text-[10px] text-gray-500 hover:text-gray-300 bg-gray-800/30 border-t border-gray-800"
        >
          {expanded ? "Show less" : `Show more (${content.length} chars)`}
        </button>
      )}
    </div>
  );
}

// ── Main MessageBubble ──────────────────────────────────────

export function MessageBubble({ message, send }: Props) {
  const { role, content, tool_calls } = message;

  if (role === "user") {
    return (
      <div className="flex gap-3 justify-end animate-fade-in">
        <div className="max-w-2xl">
          <div className="bg-plutus-600 text-white px-4 py-3 rounded-2xl rounded-tr-md text-sm leading-relaxed">
            {content}
          </div>
        </div>
        <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center flex-shrink-0">
          <User className="w-4 h-4 text-gray-300" />
        </div>
      </div>
    );
  }

  if (role === "assistant") {
    return (
      <div className="flex gap-3 animate-fade-in">
        <div className="w-8 h-8 rounded-full bg-plutus-600/20 flex items-center justify-center flex-shrink-0">
          <Bot className="w-4 h-4 text-plutus-400" />
        </div>
        <div className="max-w-2xl w-full">
          {content && (
            <div className="bg-gray-800 px-4 py-3 rounded-2xl rounded-tl-md text-sm leading-relaxed text-gray-200">
              <FormattedContent text={content} />
            </div>
          )}
          {tool_calls && tool_calls.length > 0 && (
            <div className="mt-2 space-y-2">
              {tool_calls.map((tc) => (
                <ToolCallCard
                  key={tc.id}
                  name={tc.name}
                  args={tc.arguments}
                  id={tc.id}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (role === "tool") {
    return (
      <div className="flex gap-3 animate-fade-in">
        <div className="w-8 h-8" /> {/* spacer to align with assistant */}
        <div className="max-w-2xl w-full">
          <ToolResultContent content={content || ""} />
        </div>
      </div>
    );
  }

  if (role === "system") {
    // Check if it's an approval request
    if (content?.startsWith("Approval needed")) {
      return <ToolApproval message={content} send={send} approvalId={message.approval_id ?? undefined} />;
    }

    // Mode indicator
    if (content?.includes("Computer Use mode") || content?.includes("Standard mode")) {
      const isComputerUse = content.includes("Computer Use mode");
      return (
        <div className="flex items-center justify-center gap-2 py-2 animate-fade-in">
          <div className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1.5 ${
            isComputerUse
              ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
              : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
          }`}>
            {isComputerUse ? (
              <Monitor className="w-3 h-3" />
            ) : (
              <Terminal className="w-3 h-3" />
            )}
            {content}
          </div>
        </div>
      );
    }

    // Step indicator
    if (content?.startsWith("Step ")) {
      return (
        <div className="flex items-center justify-center gap-2 py-1 animate-fade-in">
          <span className="text-[10px] text-gray-600 font-mono">{content}</span>
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

// ── Formatted Content ───────────────────────────────────────

function FormattedContent({ text }: { text: string }) {
  // Handle code blocks first
  const blocks = text.split(/(```[\s\S]*?```)/g);

  return (
    <>
      {blocks.map((block, i) => {
        // Code block
        if (block.startsWith("```") && block.endsWith("```")) {
          const lines = block.slice(3, -3).split("\n");
          const lang = lines[0]?.trim() || "";
          const code = lang ? lines.slice(1).join("\n") : lines.join("\n");

          return (
            <div key={i} className="my-2 bg-gray-900 rounded-lg overflow-hidden border border-gray-800">
              {lang && (
                <div className="px-3 py-1 bg-gray-800/50 border-b border-gray-800 text-[10px] text-gray-500">
                  {lang}
                </div>
              )}
              <pre className="px-3 py-2 text-xs font-mono text-gray-300 overflow-x-auto">
                {code}
              </pre>
            </div>
          );
        }

        // Inline formatting
        const parts = block.split(/(\*\*.*?\*\*|`.*?`|\n)/g);
        return (
          <span key={i}>
            {parts.map((part, j) => {
              if (part === "\n") return <br key={j} />;
              if (part.startsWith("**") && part.endsWith("**")) {
                return (
                  <strong key={j} className="font-semibold text-gray-100">
                    {part.slice(2, -2)}
                  </strong>
                );
              }
              if (part.startsWith("`") && part.endsWith("`")) {
                return (
                  <code
                    key={j}
                    className="px-1.5 py-0.5 bg-gray-700 rounded text-plutus-300 text-xs font-mono"
                  >
                    {part.slice(1, -1)}
                  </code>
                );
              }
              return <span key={j}>{part}</span>;
            })}
          </span>
        );
      })}
    </>
  );
}

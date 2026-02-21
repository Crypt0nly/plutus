import { User, Bot, Terminal, AlertTriangle } from "lucide-react";
import type { Message } from "../../lib/types";
import { ToolApproval } from "./ToolApproval";

interface Props {
  message: Message;
  send: (data: Record<string, unknown>) => void;
}

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
        <div className="max-w-2xl">
          {content && (
            <div className="bg-gray-800 px-4 py-3 rounded-2xl rounded-tl-md text-sm leading-relaxed text-gray-200">
              <FormattedContent text={content} />
            </div>
          )}
          {tool_calls && tool_calls.length > 0 && (
            <div className="mt-2 space-y-2">
              {tool_calls.map((tc) => (
                <div
                  key={tc.id}
                  className="flex items-center gap-2 px-3 py-2 bg-gray-800/50 border border-gray-700 rounded-lg text-xs"
                >
                  <Terminal className="w-3.5 h-3.5 text-plutus-400" />
                  <span className="text-plutus-300 font-medium">{tc.name}</span>
                  <span className="text-gray-500 truncate">
                    {JSON.stringify(tc.arguments).slice(0, 80)}
                  </span>
                </div>
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
          <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 text-xs font-mono text-gray-400 overflow-x-auto max-h-64 overflow-y-auto">
            <pre className="whitespace-pre-wrap">{content}</pre>
          </div>
        </div>
      </div>
    );
  }

  if (role === "system") {
    // Check if it's an approval request
    if (content?.startsWith("Approval needed")) {
      return <ToolApproval message={content} send={send} />;
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

function FormattedContent({ text }: { text: string }) {
  // Simple markdown-like formatting for bold and code
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold text-gray-100">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code
              key={i}
              className="px-1.5 py-0.5 bg-gray-700 rounded text-plutus-300 text-xs font-mono"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

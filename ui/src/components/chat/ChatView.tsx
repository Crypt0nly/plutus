import { useRef, useEffect } from "react";
import { useAppStore } from "../../stores/appStore";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { MessageSquare, KeyRound, FileEdit, GitBranch, Zap, Wrench } from "lucide-react";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

export function ChatView({ send }: Props) {
  const { messages, isProcessing, keyConfigured } = useAppStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = (content: string) => {
    useAppStore.getState().addMessage({ role: "user", content });
    send({ type: "chat", content });
  };

  return (
    <div className="flex flex-col h-full -m-6">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 ? (
          keyConfigured ? <EmptyState onSend={handleSend} /> : <SetupPrompt />
        ) : (
          messages.map((msg, i) => <MessageBubble key={i} message={msg} send={send} />)
        )}

        {isProcessing && (
          <div className="flex items-center gap-2 text-sm text-gray-500 animate-fade-in">
            <div className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span>Plutus is thinking...</span>
          </div>
        )}
      </div>

      {/* Input area */}
      <ChatInput onSend={handleSend} disabled={isProcessing || !keyConfigured} />
    </div>
  );
}

function SetupPrompt() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
      <div className="w-16 h-16 rounded-2xl bg-amber-500/20 flex items-center justify-center mb-6">
        <KeyRound className="w-8 h-8 text-amber-400" />
      </div>
      <h3 className="text-xl font-semibold text-gray-200 mb-2">
        API Key Required
      </h3>
      <p className="text-gray-500 max-w-md text-sm leading-relaxed mb-6">
        To get started, configure your API key for Claude, ChatGPT, or another
        LLM provider. Your key is stored locally and never leaves your machine.
      </p>
      <button
        onClick={() => useAppStore.getState().setView("settings")}
        className="px-5 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 text-white text-sm font-medium transition-colors"
      >
        Go to Settings
      </button>
    </div>
  );
}

function EmptyState({ onSend }: { onSend: (text: string) => void }) {
  const capabilities = [
    {
      icon: FileEdit,
      color: "text-emerald-400 bg-emerald-500/10",
      label: "Edit Code",
      description: "Create, edit, and manage files with surgical precision",
    },
    {
      icon: GitBranch,
      color: "text-blue-400 bg-blue-500/10",
      label: "Analyze Code",
      description: "Find functions, check complexity, trace dependencies",
    },
    {
      icon: Zap,
      color: "text-purple-400 bg-purple-500/10",
      label: "Run Tasks",
      description: "Execute commands and run parallel subprocesses",
    },
    {
      icon: Wrench,
      color: "text-pink-400 bg-pink-500/10",
      label: "Create Tools",
      description: "Build new capabilities on the fly when needed",
    },
  ];

  const suggestions = [
    "Analyze the code in my project and find potential issues",
    "Create a Python script that monitors disk usage",
    "Help me refactor this function to be more efficient",
    "Create a custom tool that validates JSON files",
    "Show me what files are in the current directory",
    "Write unit tests for my Python module",
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-plutus-500/20 to-purple-500/20 flex items-center justify-center mb-6 shadow-lg shadow-plutus-500/10">
        <MessageSquare className="w-8 h-8 text-plutus-400" />
      </div>
      <h3 className="text-xl font-semibold text-gray-200 mb-2">
        What can I help you with?
      </h3>
      <p className="text-gray-500 max-w-lg text-sm leading-relaxed mb-8">
        I'm an AI agent that can edit code, analyze projects, run commands, and even
        create new tools on the fly. Everything runs in isolated subprocesses for safety.
      </p>

      {/* Capabilities */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl mb-8">
        {capabilities.map((cap) => {
          const Icon = cap.icon;
          const [textColor, bgColor] = cap.color.split(" ");
          return (
            <div
              key={cap.label}
              className="flex flex-col items-center gap-2 p-3 rounded-xl bg-gray-800/30 border border-gray-800"
            >
              <div className={`w-8 h-8 rounded-lg ${bgColor} flex items-center justify-center`}>
                <Icon className={`w-4 h-4 ${textColor}`} />
              </div>
              <span className="text-xs font-medium text-gray-300">{cap.label}</span>
              <span className="text-[10px] text-gray-500 leading-tight">{cap.description}</span>
            </div>
          );
        })}
      </div>

      {/* Suggestions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-2xl w-full">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => onSend(suggestion)}
            className="text-left px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-800 hover:border-plutus-500/30 hover:bg-gray-800 text-sm text-gray-400 hover:text-gray-200 transition-all"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

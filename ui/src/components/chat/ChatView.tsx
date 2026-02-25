import { useRef, useEffect } from "react";
import { useAppStore } from "../../stores/appStore";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Globe, MousePointer, AppWindow, KeyRound, Zap, Brain, ArrowRight } from "lucide-react";

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

  const handleStop = () => {
    send({ type: "stop_task" });
  };

  return (
    <div className="flex h-full flex-col flex-1 min-h-0">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-1">
          {messages.length === 0 ? (
            keyConfigured ? <EmptyState onSend={handleSend} /> : <SetupPrompt />
          ) : (
            messages.map((msg, i) => <MessageBubble key={i} message={msg} send={send} />)
          )}

          {isProcessing && (
            <div className="flex items-center gap-3 py-4 px-1 animate-fade-in">
              <div className="w-7 h-7 rounded-full bg-plutus-600/15 flex items-center justify-center flex-shrink-0">
                <div className="dot-pulse flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full" />
                  <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full" />
                  <span className="w-1.5 h-1.5 bg-plutus-400 rounded-full" />
                </div>
              </div>
              <span className="text-sm text-gray-500">Thinking...</span>
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <ChatInput onSend={handleSend} onStop={handleStop} disabled={isProcessing || !keyConfigured} />
    </div>
  );
}

function SetupPrompt() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-24">
      <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-5">
        <KeyRound className="w-7 h-7 text-amber-400" />
      </div>
      <h3 className="text-xl font-semibold text-gray-100 mb-2">
        API Key Required
      </h3>
      <p className="text-gray-400 max-w-sm text-sm leading-relaxed mb-2">
        Configure your API key in Settings to get started.
      </p>
      <p className="text-gray-600 max-w-sm text-xs leading-relaxed mb-6">
        Your key is stored locally and never leaves your machine.
      </p>
      <button
        onClick={() => useAppStore.getState().setView("settings")}
        className="px-5 py-2.5 rounded-lg bg-plutus-600 hover:bg-plutus-500 text-white text-sm font-medium transition-colors"
      >
        Go to Settings
      </button>
    </div>
  );
}

function EmptyState({ onSend }: { onSend: (text: string) => void }) {
  const capabilities = [
    {
      icon: Globe,
      color: "text-blue-400",
      bg: "bg-blue-500/8 border-blue-500/10",
      label: "Browse the Web",
      description: "Navigate sites, read content, fill forms",
    },
    {
      icon: MousePointer,
      color: "text-violet-400",
      bg: "bg-violet-500/8 border-violet-500/10",
      label: "Control Your PC",
      description: "Click, type, open apps, manage files",
    },
    {
      icon: Brain,
      color: "text-emerald-400",
      bg: "bg-emerald-500/8 border-emerald-500/10",
      label: "Learn & Improve",
      description: "Creates reusable skills over time",
    },
    {
      icon: AppWindow,
      color: "text-amber-400",
      bg: "bg-amber-500/8 border-amber-500/10",
      label: "Automate Anything",
      description: "Chain actions, schedule tasks",
    },
  ];

  const suggestions = [
    "Open Chrome and search for the latest AI news",
    "Send a message on Telegram",
    "Open Notepad and write a quick to-do list",
    "Find and organize my Downloads folder",
    "Check my email for anything important",
    "Help me research a topic and summarize it",
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-16">
      {/* Hero */}
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-plutus-500/20 to-violet-500/20 border border-plutus-500/10 flex items-center justify-center mb-6">
        <Zap className="w-6 h-6 text-plutus-400" />
      </div>
      <h2 className="text-2xl font-semibold text-gray-100 mb-2 tracking-tight">
        What can I help you with?
      </h2>
      <p className="text-gray-500 max-w-md text-sm leading-relaxed mb-10">
        Describe what you need in plain English. I can browse the web,
        control apps, manage files, and automate tasks.
      </p>

      {/* Capabilities */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl w-full mb-10">
        {capabilities.map((cap) => {
          const Icon = cap.icon;
          return (
            <div
              key={cap.label}
              className={`flex flex-col items-center gap-2.5 p-4 rounded-xl border ${cap.bg} transition-colors hover:bg-gray-800/40`}
            >
              <Icon className={`w-5 h-5 ${cap.color}`} />
              <div>
                <span className="text-xs font-medium text-gray-200 block">{cap.label}</span>
                <span className="text-[11px] text-gray-500 leading-snug mt-0.5 block">{cap.description}</span>
              </div>
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
            className="group text-left px-4 py-3 rounded-xl border border-gray-800/60 bg-gray-900/40 hover:bg-gray-800/50 hover:border-gray-700/60 text-sm text-gray-400 hover:text-gray-200 transition-all flex items-center gap-3"
          >
            <span className="flex-1">{suggestion}</span>
            <ArrowRight className="w-3.5 h-3.5 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0 opacity-0 group-hover:opacity-100" />
          </button>
        ))}
      </div>
    </div>
  );
}

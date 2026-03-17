import { useRef, useEffect } from "react";
import { useAppStore } from "../../stores/appStore";
import { MessageBubble } from "./MessageBubble";
import { ChatInput, Attachment } from "./ChatInput";
import { Globe, MousePointer, AppWindow, KeyRound, Brain, ArrowRight, Sparkles } from "lucide-react";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

export function ChatView({ send }: Props) {
  const { keyConfigured, activeSessionId, sessionStates } = useAppStore();
  const messages = sessionStates[activeSessionId]?.messages ?? [];
  const isProcessing = sessionStates[activeSessionId]?.isProcessing ?? false;
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = (content: string, attachments?: Attachment[]) => {
    const displayParts: string[] = [content];
    if (attachments?.length) {
      const names = attachments.map((a) => a.name).join(", ");
      displayParts.push(`\n[Attached: ${names}]`);
    }
    useAppStore.getState().addMessage({ role: "user", content: displayParts.join("") }, activeSessionId);

    const wsPayload: Record<string, unknown> = { type: "chat", content, session_id: activeSessionId };
    if (attachments?.length) {
      wsPayload.attachments = attachments.map(({ name, type, data }) => ({
        name, type, data,
      }));
    }
    send(wsPayload);
  };

  const handleStop = () => {
    send({ type: "stop_task", session_id: activeSessionId });
  };

  return (
    <div className="flex h-full flex-col flex-1 min-h-0 relative">
      {/* Ambient background effect */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px]"
          style={{
            background: "radial-gradient(ellipse at 50% 0%, rgba(99, 102, 241, 0.04) 0%, transparent 70%)"
          }}
        />
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="relative flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-1">
          {messages.length === 0 ? (
            keyConfigured ? <EmptyState onSend={handleSend} /> : <SetupPrompt />
          ) : (
            messages.map((msg, i) => <MessageBubble key={i} message={msg} send={send} />)
          )}

          {isProcessing && (
            <div className="flex items-center gap-3 py-4 px-1 animate-fade-in">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{
                  background: "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(79, 70, 229, 0.08))",
                  border: "1px solid rgba(99, 102, 241, 0.15)"
                }}
              >
                <div className="dot-pulse flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                </div>
              </div>
              <span className="text-sm text-gray-500 font-medium">Thinking...</span>
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
      <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6"
        style={{
          background: "linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(217, 119, 6, 0.06))",
          border: "1px solid rgba(245, 158, 11, 0.2)",
          boxShadow: "0 8px 32px rgba(245, 158, 11, 0.1)"
        }}
      >
        <KeyRound className="w-7 h-7 text-amber-400" />
      </div>
      <h3 className="welcome-heading text-xl font-semibold mb-2 tracking-tight">
        API Key Required
      </h3>
      <p className="welcome-subtext max-w-sm text-sm leading-relaxed mb-2">
        Configure your API key in Settings to get started.
      </p>
      <p className="welcome-hint max-w-sm text-xs leading-relaxed mb-8">
        Your key is stored locally and never leaves your machine.
      </p>
      <button
        onClick={() => useAppStore.getState().setView("settings")}
        className="px-6 py-2.5 rounded-xl text-sm font-medium text-white transition-all duration-200 active:scale-[0.97]"
        style={{
          background: "linear-gradient(135deg, #6366f1, #4f46e5)",
          boxShadow: "0 4px 16px rgba(99, 102, 241, 0.3)"
        }}
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
      color: "#60a5fa",
      bg: "rgba(59, 130, 246, 0.08)",
      border: "rgba(59, 130, 246, 0.12)",
      label: "Browse the Web",
      description: "Navigate sites, read content, fill forms",
    },
    {
      icon: MousePointer,
      color: "#a78bfa",
      bg: "rgba(139, 92, 246, 0.08)",
      border: "rgba(139, 92, 246, 0.12)",
      label: "Control Your PC",
      description: "Click, type, open apps, manage files",
    },
    {
      icon: Brain,
      color: "#34d399",
      bg: "rgba(16, 185, 129, 0.08)",
      border: "rgba(16, 185, 129, 0.12)",
      label: "Learn & Improve",
      description: "Creates reusable skills over time",
    },
    {
      icon: AppWindow,
      color: "#fbbf24",
      bg: "rgba(245, 158, 11, 0.08)",
      border: "rgba(245, 158, 11, 0.12)",
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
    <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
      {/* Hero icon */}
      <div className="relative mb-6">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{
            background: "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.08))",
            border: "1px solid rgba(99, 102, 241, 0.15)",
            boxShadow: "0 8px 32px rgba(99, 102, 241, 0.15)"
          }}
        >
          <Sparkles className="w-6 h-6" style={{ color: "#818cf8" }} />
        </div>
        {/* Glow ring */}
        <div className="absolute inset-0 rounded-2xl animate-glow-pulse" />
      </div>

      <h2 className="welcome-heading text-2xl font-semibold mb-2 tracking-tight">
        What can I help you with?
      </h2>
      <p className="welcome-subtext max-w-md text-sm leading-relaxed mb-10">
        Describe what you need in plain English. I can browse the web,
        control apps, manage files, and automate tasks.
      </p>

      {/* Capabilities grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl w-full mb-10">
        {capabilities.map((cap) => {
          const Icon = cap.icon;
          return (
            <div
              key={cap.label}
              className="flex flex-col items-center gap-3 p-4 rounded-2xl transition-all duration-200 hover:scale-[1.02]"
              style={{
                background: cap.bg,
                border: `1px solid ${cap.border}`,
              }}
            >
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                style={{ background: `${cap.bg}`, border: `1px solid ${cap.border}` }}
              >
                <Icon className="w-4.5 h-4.5" style={{ color: cap.color }} />
              </div>
              <div>
                <span className="text-xs font-semibold text-gray-100 block">{cap.label}</span>
                <span className="text-[11px] text-gray-400 leading-snug mt-0.5 block">{cap.description}</span>
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
            className="prompt-chip group text-left px-4 py-3 rounded-xl text-sm transition-all duration-150 flex items-center gap-3"
          >
            <span className="flex-1 leading-relaxed">{suggestion}</span>
            <ArrowRight className="w-3.5 h-3.5 text-gray-600 group-hover:text-plutus-400 transition-colors flex-shrink-0 opacity-0 group-hover:opacity-100" />
          </button>
        ))}
      </div>
    </div>
  );
}

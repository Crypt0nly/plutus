import { useRef, useEffect } from "react";
import { useAppStore } from "../../stores/appStore";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Monitor, Mouse, Keyboard, AppWindow, KeyRound, Zap } from "lucide-react";

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
    <div className="flex flex-col flex-1 min-h-0 -m-6">
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
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span>Plutus is controlling your computer...</span>
          </div>
        )}
      </div>

      {/* Input area */}
      <ChatInput onSend={handleSend} onStop={handleStop} disabled={isProcessing || !keyConfigured} />
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
      <p className="text-gray-500 max-w-md text-sm leading-relaxed mb-4">
        To get started, configure your <strong className="text-gray-300">Anthropic API key</strong> for
        Claude computer use. Your key is stored locally and never leaves your machine.
      </p>
      <p className="text-gray-600 max-w-md text-xs leading-relaxed mb-6">
        Plutus uses Claude's native Computer Use Tool to see your screen and control your computer.
        An Anthropic API key is required for this to work.
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
      icon: Monitor,
      color: "text-blue-400 bg-blue-500/10",
      label: "See Your Screen",
      description: "Takes screenshots and understands what's on screen using Claude's vision",
    },
    {
      icon: Mouse,
      color: "text-purple-400 bg-purple-500/10",
      label: "Click & Navigate",
      description: "Clicks buttons, links, menus — anywhere on screen",
    },
    {
      icon: Keyboard,
      color: "text-emerald-400 bg-emerald-500/10",
      label: "Type & Shortcut",
      description: "Types text, presses keys, uses keyboard shortcuts",
    },
    {
      icon: AppWindow,
      color: "text-amber-400 bg-amber-500/10",
      label: "Open & Switch Apps",
      description: "Opens applications, switches between windows and tabs",
    },
  ];

  const suggestions = [
    "Open WhatsApp and send a message to Mom",
    "Take a screenshot and tell me what you see",
    "Open Chrome and search for the latest AI news",
    "Open Notepad and write a quick to-do list",
    "Find the Settings app and change the wallpaper",
    "Open Spotify and play some relaxing music",
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center mb-6 shadow-lg shadow-blue-500/10">
        <Zap className="w-8 h-8 text-blue-400" />
      </div>
      <h3 className="text-xl font-semibold text-gray-200 mb-2">
        What should I do on your computer?
      </h3>
      <p className="text-gray-500 max-w-lg text-sm leading-relaxed mb-8">
        I can see your screen, move the mouse, click buttons, type text, open apps,
        browse the web, and automate anything. Just describe what you need in plain English.
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
            className="text-left px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-800 hover:border-blue-500/30 hover:bg-gray-800 text-sm text-gray-400 hover:text-gray-200 transition-all"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

import { useRef, useEffect } from "react";
import { useAppStore } from "../../stores/appStore";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { MessageSquare, KeyRound } from "lucide-react";

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
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 ? (
          keyConfigured ? <EmptyState /> : <SetupPrompt />
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

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-20">
      <div className="w-16 h-16 rounded-2xl bg-plutus-600/20 flex items-center justify-center mb-6">
        <MessageSquare className="w-8 h-8 text-plutus-400" />
      </div>
      <h3 className="text-xl font-semibold text-gray-200 mb-2">
        What can I help you with?
      </h3>
      <p className="text-gray-500 max-w-md text-sm leading-relaxed">
        I can execute commands, manage files, browse the web, and automate tasks on your computer.
        Your guardrail settings control what I'm allowed to do.
      </p>
      <div className="mt-8 grid grid-cols-2 gap-3 max-w-lg">
        {[
          "Show me system information",
          "List files in my home directory",
          "What processes are using the most memory?",
          "Help me write a Python script",
        ].map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => {
              useAppStore.getState().addMessage({ role: "user", content: suggestion });
            }}
            className="text-left px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-800 hover:border-gray-700 hover:bg-gray-800 text-sm text-gray-400 hover:text-gray-200 transition-all"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

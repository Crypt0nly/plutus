import { useState, useRef, useEffect } from "react";
import { Send, Square, Paperclip } from "lucide-react";
import { useAppStore } from "../../stores/appStore";

interface Props {
  onSend: (content: string) => void;
  onStop?: () => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, onStop, disabled }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isProcessing } = useAppStore();

  // Auto-resize textarea — reset to single line then grow to fit content
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "24px"; // Reset to single line height
    const scrollH = el.scrollHeight;
    el.style.height = Math.min(scrollH, 160) + "px"; // Max ~6 lines
  }, [input]);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    // Reset height after sending
    if (textareaRef.current) {
      textareaRef.current.style.height = "24px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleStop = () => {
    if (onStop) onStop();
  };

  return (
    <div className="border-t border-gray-800/50 bg-gray-900/80 backdrop-blur-sm px-4 py-3">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-2 bg-gray-800/80 border border-gray-700/50 rounded-xl px-3 py-2 focus-within:border-plutus-500/40 focus-within:ring-1 focus-within:ring-plutus-500/20 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isProcessing
                ? "Plutus is working..."
                : "Message Plutus..."
            }
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent border-none outline-none text-sm text-gray-200 placeholder-gray-500 resize-none leading-6 disabled:opacity-50"
            style={{ height: "24px", minHeight: "24px", maxHeight: "160px" }}
          />
          {isProcessing ? (
            <button
              onClick={handleStop}
              className="flex-shrink-0 w-8 h-8 rounded-lg bg-red-500/90 hover:bg-red-500 flex items-center justify-center transition-colors"
              title="Stop current task"
            >
              <Square className="w-3 h-3 text-white fill-white" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={disabled || !input.trim()}
              className="flex-shrink-0 w-8 h-8 rounded-lg bg-plutus-600 hover:bg-plutus-500 flex items-center justify-center transition-colors disabled:opacity-20 disabled:cursor-not-allowed"
            >
              <Send className="w-3.5 h-3.5 text-white" />
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-600 mt-1.5 text-center">
          {isProcessing
            ? "Plutus is working on your task — press ■ to stop"
            : "Press Enter to send · Shift+Enter for new line"
          }
        </p>
      </div>
    </div>
  );
}

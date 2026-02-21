import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
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

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
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
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleStop = () => {
    if (onStop) {
      onStop();
    }
  };

  return (
    <div className="border-t border-gray-800 bg-gray-900/50 px-6 py-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-3 bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3 focus-within:border-plutus-500/50 focus-within:ring-2 focus-within:ring-plutus-500/20 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isProcessing ? "Plutus is working... click ■ to stop" : "Tell Plutus what to do..."}
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent border-none outline-none text-sm text-gray-200 placeholder-gray-500 resize-none max-h-48 disabled:opacity-50"
          />
          {isProcessing ? (
            <button
              onClick={handleStop}
              className="flex-shrink-0 w-8 h-8 rounded-lg bg-red-600 hover:bg-red-700 flex items-center justify-center transition-colors"
              title="Stop current task"
            >
              <Square className="w-3.5 h-3.5 text-white fill-white" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={disabled || !input.trim()}
              className="flex-shrink-0 w-8 h-8 rounded-lg bg-plutus-600 hover:bg-plutus-700 flex items-center justify-center transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Send className="w-4 h-4 text-white" />
            </button>
          )}
        </div>
        <p className="text-xs text-gray-600 mt-2 text-center">
          {isProcessing
            ? "Plutus is controlling your computer — press ■ to stop at any time"
            : "Plutus can see your screen, click, type, and control apps. Just tell it what to do."
          }
        </p>
      </div>
    </div>
  );
}

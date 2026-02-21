import { useState, useRef, useEffect } from "react";
import { Send, Paperclip } from "lucide-react";

interface Props {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  return (
    <div className="border-t border-gray-800 bg-gray-900/50 px-6 py-4">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-3 bg-gray-800 border border-gray-700 rounded-2xl px-4 py-3 focus-within:border-plutus-500/50 focus-within:ring-2 focus-within:ring-plutus-500/20 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Plutus..."
            disabled={disabled}
            rows={1}
            className="flex-1 bg-transparent border-none outline-none text-sm text-gray-200 placeholder-gray-500 resize-none max-h-48 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !input.trim()}
            className="flex-shrink-0 w-8 h-8 rounded-lg bg-plutus-600 hover:bg-plutus-700 flex items-center justify-center transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-2 text-center">
          Plutus can make mistakes. Review tool actions before approving.
        </p>
      </div>
    </div>
  );
}

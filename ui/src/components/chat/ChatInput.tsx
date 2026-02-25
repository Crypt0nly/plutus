import { useState, useRef, useEffect } from "react";
import { ArrowUp, Square } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { CommandCenter } from "./CommandCenter";

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

  const hasInput = input.trim().length > 0;

  return (
    <div className="bg-gray-950/80 backdrop-blur-md px-4 pt-2 pb-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative bg-gray-900 border border-gray-800 rounded-2xl shadow-lg shadow-black/20 transition-all focus-within:border-gray-700 focus-within:shadow-xl focus-within:shadow-black/30">
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
            className="w-full bg-transparent border-none outline-none text-sm text-gray-100 placeholder-gray-600 resize-none leading-6 px-4 pt-3.5 pb-12"
            style={{ height: "24px", minHeight: "24px", maxHeight: "160px" }}
          />
          {/* Bottom bar inside the input */}
          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-3 pb-2.5">
            <div className="flex items-center gap-1">
              <CommandCenter />
              <span className="text-[11px] text-gray-600 ml-1 select-none">
                {isProcessing
                  ? "Working on your task"
                  : "Enter to send"
                }
              </span>
            </div>
            {isProcessing ? (
              <button
                onClick={handleStop}
                className="w-7 h-7 rounded-lg bg-red-500/90 hover:bg-red-500 flex items-center justify-center transition-colors"
                title="Stop current task"
              >
                <Square className="w-3 h-3 text-white fill-white" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={disabled || !hasInput}
                className={`w-7 h-7 rounded-lg flex items-center justify-center transition-all ${
                  hasInput
                    ? "bg-plutus-600 hover:bg-plutus-500 text-white shadow-sm shadow-plutus-600/30"
                    : "bg-gray-800 text-gray-600 cursor-not-allowed"
                }`}
              >
                <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

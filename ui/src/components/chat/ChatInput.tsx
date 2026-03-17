import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowUp, Square, Paperclip, X, FileText, Image as ImageIcon } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { CommandCenter } from "./CommandCenter";

export interface Attachment {
  name: string;
  type: string;
  data: string;
  preview?: string;
}

interface Props {
  onSend: (content: string, attachments?: Attachment[]) => void;
  onStop?: () => void;
  disabled?: boolean;
}

const ACCEPTED_TYPES = [
  "image/jpeg", "image/png", "image/gif", "image/webp",
  "application/pdf",
].join(",");

const MAX_FILE_SIZE = 20 * 1024 * 1024;

export function ChatInput({ onSend, onStop, disabled }: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isFocused, setIsFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { activeSessionId, sessionStates } = useAppStore();
  const isProcessing = sessionStates[activeSessionId]?.isProcessing ?? false;

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "24px";
    const scrollH = el.scrollHeight;
    el.style.height = Math.min(scrollH, 160) + "px";
  }, [input]);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if ((!trimmed && attachments.length === 0) || disabled) return;
    onSend(trimmed || "(attached files)", attachments.length > 0 ? attachments : undefined);
    setInput("");
    setAttachments([]);
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

  const readFileAsBase64 = (file: File): Promise<Attachment> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(",")[1] || "";
        const att: Attachment = { name: file.name, type: file.type, data: base64 };
        if (file.type.startsWith("image/")) att.preview = result;
        resolve(att);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files) return;
    const newAttachments: Attachment[] = [];
    for (const file of Array.from(files)) {
      if (file.size > MAX_FILE_SIZE) continue;
      try {
        const att = await readFileAsBase64(file);
        newAttachments.push(att);
      } catch { /* skip */ }
    }
    setAttachments((prev: Attachment[]) => [...prev, ...newAttachments].slice(0, 10));
  }, []);

  const removeAttachment = (index: number) => {
    setAttachments((prev: Attachment[]) => prev.filter((_: Attachment, i: number) => i !== index));
  };

  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length > 0) {
        const dt = new DataTransfer();
        files.forEach((f) => dt.items.add(f));
        handleFileSelect(dt.files);
      }
    };
    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [handleFileSelect]);

  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const hasInput = input.trim().length > 0 || attachments.length > 0;

  return (
    <div className="flex-shrink-0 px-4 pt-2 pb-5 bg-gradient-to-t from-gray-950 via-gray-950/95 to-transparent">
      <div className="max-w-3xl mx-auto">
        <div
          className="relative rounded-2xl transition-all duration-200"
          style={{
            background: isDragging
              ? "rgba(99, 102, 241, 0.06)"
              : "rgb(var(--surface))",
            border: isDragging
              ? "1px solid rgba(99, 102, 241, 0.4)"
              : isFocused
              ? "1px solid rgba(99, 102, 241, 0.35)"
              : "1px solid rgb(var(--gray-700) / 0.5)",
            boxShadow: isFocused
              ? "0 8px 32px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(99, 102, 241, 0.1), 0 0 20px rgba(99, 102, 241, 0.06)"
              : "0 4px 24px rgba(0, 0, 0, 0.08)",
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="flex gap-2 px-3 pt-3 pb-1 flex-wrap">
              {attachments.map((att, i) => (
                <div
                  key={`${att.name}-${i}`}
                  className="relative group flex items-center gap-2 rounded-xl px-2.5 py-1.5 max-w-[200px]"
                  style={{
                    background: "rgb(var(--gray-800) / 0.6)",
                    border: "1px solid rgb(var(--gray-700) / 0.5)"
                  }}
                >
                  {att.preview ? (
                    <img src={att.preview} alt={att.name} className="w-8 h-8 rounded-lg object-cover flex-shrink-0" />
                  ) : (
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                      style={{ background: "rgb(var(--gray-800) / 0.8)" }}
                    >
                      {att.type === "application/pdf" ? (
                        <FileText className="w-4 h-4 text-red-400" />
                      ) : (
                        <ImageIcon className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  )}
                  <span className="text-[11px] text-gray-400 truncate">{att.name}</span>
                  <button
                    onClick={() => removeAttachment(i)}
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ background: "rgba(31, 41, 55, 1)", border: "1px solid rgba(75, 85, 99, 0.5)" }}
                  >
                    <X className="w-2.5 h-2.5 text-gray-300" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={isProcessing ? "Plutus is working..." : "Message Plutus..."}
            disabled={disabled}
            rows={1}
            className="w-full bg-transparent border-none outline-none text-sm text-gray-100 placeholder-gray-500 resize-none leading-6 pl-4 pr-4 pt-3.5 pb-14"
            style={{ height: "24px", minHeight: "24px", maxHeight: "160px" }}
          />

          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            onChange={(e) => {
              handleFileSelect(e.target.files);
              e.target.value = "";
            }}
            className="hidden"
          />

          {/* Bottom bar */}
          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-3 pb-3 pt-2 rounded-b-2xl"
            style={{ background: "rgb(var(--surface) / 0.95)" }}
          >
            <div className="flex items-center gap-1">
              <CommandCenter />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || isProcessing}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-200 transition-colors disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-800/50"
                title="Attach files (images, PDFs)"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <span className="text-[11px] text-gray-500 ml-1 select-none">
                {isProcessing ? "Working on your task" : "Enter to send · Shift+Enter for newline"}
              </span>
            </div>

            {isProcessing ? (
              <button
                onClick={onStop}
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-all active:scale-95"
                style={{
                  background: "rgba(239, 68, 68, 0.9)",
                  boxShadow: "0 2px 8px rgba(239, 68, 68, 0.3)"
                }}
                title="Stop current task"
              >
                <Square className="w-3 h-3 text-white fill-white" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={disabled || !hasInput}
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-all active:scale-95"
                style={hasInput ? {
                  background: "linear-gradient(135deg, #6366f1, #4f46e5)",
                  boxShadow: "0 2px 12px rgba(99, 102, 241, 0.4)"
                } : {
                  background: "rgb(var(--gray-800) / 0.6)",
                  cursor: "not-allowed"
                }}
              >
                <ArrowUp
                  className={`w-4 h-4 ${hasInput ? "text-white" : "text-gray-600"}`}
                  strokeWidth={2.5}
                />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

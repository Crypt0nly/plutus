import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowUp, Square, Paperclip, X, FileText, Image as ImageIcon } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { CommandCenter } from "./CommandCenter";

export interface Attachment {
  name: string;
  type: string; // MIME type
  data: string; // base64
  preview?: string; // data URL for image preview
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

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB

export function ChatInput({ onSend, onStop, disabled }: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const handleStop = () => {
    if (onStop) onStop();
  };

  const readFileAsBase64 = (file: File): Promise<Attachment> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Strip the data URL prefix to get raw base64
        const base64 = result.split(",")[1] || "";
        const att: Attachment = {
          name: file.name,
          type: file.type,
          data: base64,
        };
        // Create preview for images
        if (file.type.startsWith("image/")) {
          att.preview = result;
        }
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
      if (file.size > MAX_FILE_SIZE) {
        continue; // Skip oversized files
      }
      try {
        const att = await readFileAsBase64(file);
        newAttachments.push(att);
      } catch {
        // Skip files that fail to read
      }
    }
    setAttachments((prev: Attachment[]) => [...prev, ...newAttachments].slice(0, 10)); // Max 10
  }, []);

  const removeAttachment = (index: number) => {
    setAttachments((prev: Attachment[]) => prev.filter((_: Attachment, i: number) => i !== index));
  };

  // Handle paste events for images
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

  // Handle drag and drop
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const hasInput = input.trim().length > 0 || attachments.length > 0;

  return (
    <div className="bg-gray-950/80 backdrop-blur-md px-4 pt-2 pb-4">
      <div className="max-w-3xl mx-auto">
        <div
          className={`relative bg-gray-900 border rounded-2xl shadow-lg shadow-black/20 transition-all focus-within:border-gray-700 focus-within:shadow-xl focus-within:shadow-black/30 ${
            isDragging ? "border-plutus-500/50 bg-plutus-500/5" : "border-gray-800"
          }`}
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
                  className="relative group flex items-center gap-2 bg-gray-800/70 border border-gray-700/50 rounded-lg px-2.5 py-1.5 max-w-[200px]"
                >
                  {att.preview ? (
                    <img
                      src={att.preview}
                      alt={att.name}
                      className="w-8 h-8 rounded object-cover flex-shrink-0"
                    />
                  ) : (
                    <div className="w-8 h-8 rounded bg-gray-700/50 flex items-center justify-center flex-shrink-0">
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
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-gray-700 border border-gray-600 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
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
            placeholder={
              isProcessing
                ? "Plutus is working..."
                : "Message Plutus..."
            }
            disabled={disabled}
            rows={1}
            className="w-full bg-transparent border-none outline-none text-sm text-gray-100 placeholder-gray-600 resize-none leading-6 pl-4 pr-4 pt-3.5 pb-14"
            style={{ height: "24px", minHeight: "24px", maxHeight: "160px" }}
          />

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            multiple
            onChange={(e) => {
              handleFileSelect(e.target.files);
              e.target.value = ""; // Reset so same file can be selected again
            }}
            className="hidden"
          />

          {/* Bottom bar inside the input — bg ensures text never shows through */}
          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-3 pb-2.5 pt-1.5 bg-gray-900 rounded-b-2xl">
            <div className="flex items-center gap-1">
              <CommandCenter />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || isProcessing}
                className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:text-gray-300 hover:bg-gray-800/60 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title="Attach files (images, PDFs)"
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <span className="text-[11px] text-gray-600 ml-0.5 select-none">
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

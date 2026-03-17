/**
 * SessionsView — shows all active connector sessions (Telegram, WhatsApp, etc.)
 * in a two-pane layout: a list on the left and the chat history on the right.
 *
 * User sessions (non-connector) are excluded — those live in the normal Chat view.
 */
import { useEffect, useRef, useState } from "react";
import { MessageSquare, Loader2, Wifi, WifiOff } from "lucide-react";
import { useAppStore, DEFAULT_SESSION_ID } from "../../stores/appStore";
import { MessageBubble } from "../chat/MessageBubble";
import { ChatInput, type Attachment } from "../chat/ChatInput";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

// Connector display metadata
const CONNECTOR_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  telegram: {
    label: "Telegram",
    color: "#38bdf8",
    bg: "rgba(56, 189, 248, 0.08)",
    border: "rgba(56, 189, 248, 0.15)",
  },
  whatsapp: {
    label: "WhatsApp",
    color: "#34d399",
    bg: "rgba(52, 211, 153, 0.08)",
    border: "rgba(52, 211, 153, 0.15)",
  },
  discord: {
    label: "Discord",
    color: "#818cf8",
    bg: "rgba(129, 140, 248, 0.08)",
    border: "rgba(129, 140, 248, 0.15)",
  },
  email: {
    label: "Email",
    color: "#fbbf24",
    bg: "rgba(251, 191, 36, 0.08)",
    border: "rgba(251, 191, 36, 0.15)",
  },
};

function getConnectorKey(session: { id: string; connector_name?: string | null }): string {
  if (session.connector_name) return session.connector_name.toLowerCase();
  // Fall back to parsing the session id (e.g. "session_telegram")
  const parts = session.id.split("_");
  return parts[parts.length - 1].toLowerCase();
}

export default function SessionsView({ send }: Props) {
  const {
    sessions,
    sessionStates,
  } = useAppStore();

  const scrollRef = useRef<HTMLDivElement>(null);

  // Only show connector sessions — use local state so we never change
  // activeSessionId (which belongs to the main chat view).
  const connectorSessions = sessions.filter(
    (s) => s.is_connector && s.id !== DEFAULT_SESSION_ID
  );

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    connectorSessions[0]?.id ?? null
  );

  // When connector sessions list changes, ensure selectedSessionId is valid
  useEffect(() => {
    if (connectorSessions.length === 0) {
      setSelectedSessionId(null);
      return;
    }
    if (!selectedSessionId || !connectorSessions.find((s) => s.id === selectedSessionId)) {
      setSelectedSessionId(connectorSessions[0].id);
    }
  }, [connectorSessions.map((s) => s.id).join(",")]);

  const selectedSession = connectorSessions.find((s) => s.id === selectedSessionId) ?? null;

  // Scroll to bottom when messages change
  const messages = selectedSession
    ? (sessionStates[selectedSession.id]?.messages ?? [])
    : [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const isProcessing = selectedSession
    ? (sessionStates[selectedSession.id]?.isProcessing ?? false)
    : false;

  const handleSend = (content: string, attachments?: Attachment[]) => {
    if (!selectedSession) return;
    useAppStore.getState().addMessage(
      { role: "user", content },
      selectedSession.id
    );
    const payload: Record<string, unknown> = {
      type: "chat",
      content,
      session_id: selectedSession.id,
    };
    if (attachments?.length) {
      payload.attachments = attachments.map(({ name, type, data }) => ({
        name, type, data,
      }));
    }
    send(payload);
  };

  const handleStop = () => {
    if (!selectedSession) return;
    send({ type: "stop_task", session_id: selectedSession.id });
  };

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      {/* ── Left pane: connector list ──────────────────────────────────── */}
      <div
        className="w-56 flex-shrink-0 flex flex-col border-r"
        style={{ borderColor: "rgba(255,255,255,0.06)" }}
      >
        <div className="px-4 pt-5 pb-3">
          <h2 className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">
            Active Sessions
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
          {connectorSessions.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <WifiOff className="w-5 h-5 text-gray-700 mx-auto mb-2" />
              <p className="text-[11px] text-gray-600 leading-relaxed">
                No connector sessions active. Enable connectors in the{" "}
                <span className="text-plutus-400">Connectors</span> tab.
              </p>
            </div>
          ) : (
            connectorSessions.map((session) => {
              const key = getConnectorKey(session);
              const meta = CONNECTOR_META[key] ?? {
                label: session.display_name,
                color: "#9ca3af",
                bg: "rgba(156,163,175,0.08)",
                border: "rgba(156,163,175,0.15)",
              };
              const isSelected = session.id === selectedSessionId;
              const processing = sessionStates[session.id]?.isProcessing ?? false;
              const msgCount = sessionStates[session.id]?.messages?.length ?? 0;

              return (
                <button
                  key={session.id}
                  onClick={() => setSelectedSessionId(session.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 ${
                    isSelected
                      ? "bg-gray-800/80"
                      : "hover:bg-gray-800/40"
                  }`}
                  style={
                    isSelected
                      ? { border: `1px solid ${meta.border}` }
                      : { border: "1px solid transparent" }
                  }
                >
                  {/* Icon */}
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-base"
                    style={{ background: meta.bg, border: `1px solid ${meta.border}` }}
                  >
                    {session.icon || "🔌"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="text-[13px] font-medium truncate"
                        style={{ color: isSelected ? meta.color : "#d1d5db" }}
                      >
                        {meta.label}
                      </span>
                      {/* Online dot */}
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ background: "#34d399" }}
                        title="Session active"
                      />
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      {processing ? (
                        <Loader2
                          className="w-3 h-3 animate-spin"
                          style={{ color: meta.color }}
                        />
                      ) : (
                        <Wifi className="w-3 h-3 text-gray-600" />
                      )}
                      <span className="text-[11px] text-gray-500">
                        {processing ? "Processing…" : `${msgCount} messages`}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* ── Right pane: chat history ───────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {selectedSession ? (
          <>
            {/* Header */}
            <div
              className="flex items-center gap-3 px-5 py-3 border-b flex-shrink-0"
              style={{ borderColor: "rgba(255,255,255,0.06)" }}
            >
              {(() => {
                const key = getConnectorKey(selectedSession);
                const meta = CONNECTOR_META[key] ?? {
                  label: selectedSession.display_name,
                  color: "#9ca3af",
                  bg: "rgba(156,163,175,0.08)",
                  border: "rgba(156,163,175,0.15)",
                };
                return (
                  <>
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0"
                      style={{ background: meta.bg, border: `1px solid ${meta.border}` }}
                    >
                      {selectedSession.icon || "🔌"}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-100">
                        {meta.label}
                      </p>
                      <p className="text-[11px] text-gray-500">
                        Dedicated connector session · messages are isolated from main chat
                      </p>
                    </div>
                  </>
                );
              })()}
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
              <div className="max-w-3xl mx-auto px-6 py-6 space-y-1">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-24 text-center">
                    <MessageSquare className="w-8 h-8 text-gray-700 mb-3" />
                    <p className="text-sm text-gray-500 font-medium">No messages yet</p>
                    <p className="text-[12px] text-gray-600 mt-1 max-w-xs leading-relaxed">
                      Messages from this connector will appear here. You can also
                      send a message directly from this panel.
                    </p>
                  </div>
                ) : (
                  messages.map((msg, i) => (
                    <MessageBubble key={i} message={msg} send={send} />
                  ))
                )}
                {isProcessing && (
                  <div className="flex items-center gap-3 py-4 px-1 animate-fade-in">
                    <div
                      className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{
                        background:
                          "linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(79, 70, 229, 0.08))",
                        border: "1px solid rgba(99, 102, 241, 0.15)",
                      }}
                    >
                      <div className="dot-pulse flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#818cf8" }} />
                      </div>
                    </div>
                    <span className="text-sm text-gray-500 font-medium">Thinking…</span>
                  </div>
                )}
              </div>
            </div>

            {/* Input */}
            <ChatInput
              onSend={handleSend}
              onStop={handleStop}
              disabled={isProcessing}
            />
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <WifiOff className="w-8 h-8 text-gray-700 mx-auto mb-3" />
              <p className="text-sm text-gray-500">No connector sessions available</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

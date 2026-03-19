/**
 * SessionsView — shows all active connector sessions (Telegram, WhatsApp, etc.)
 * in a two-pane layout: a list on the left and the chat history on the right.
 *
 * Only connectors that are configured/enabled are shown. An "Add Connector"
 * card at the bottom lets the user navigate to the Connectors settings page.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { MessageSquare, Loader2, Wifi, WifiOff, Plus, Trash2 } from "lucide-react";
import { useAppStore, DEFAULT_SESSION_ID } from "../../stores/appStore";
import { ConnectorLogo, CONNECTOR_LOGO_MAP } from "../connectors/ConnectorLogos";
import { MessageBubble } from "../chat/MessageBubble";
import { ChatInput, type Attachment } from "../chat/ChatInput";
import { api } from "../../lib/api";

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
  const parts = session.id.split("_");
  return parts[parts.length - 1].toLowerCase();
}

export default function SessionsView({ send }: Props) {
  const { sessions, sessionStates, setView } = useAppStore();

  const scrollRef = useRef<HTMLDivElement>(null);

  // Set of connector names that are configured (have credentials saved).
  const [configuredConnectors, setConfiguredConnectors] = useState<Set<string>>(new Set());
  const [loadingConnectors, setLoadingConnectors] = useState(true);

  const fetchConfigured = useCallback(async () => {
    try {
      const data = await api.getConnectors();
      const connectors: any[] = data.connectors ?? [];
      // A connector is "active" if it has been configured by the user.
      const active = new Set(
        connectors
          .filter((c) => c.configured === true)
          .map((c) => (c.name as string).toLowerCase())
      );
      setConfiguredConnectors(active);
    } catch {
      // If the API is unavailable, fall back to showing all connector sessions.
      setConfiguredConnectors(new Set(Object.keys(CONNECTOR_META)));
    } finally {
      setLoadingConnectors(false);
    }
  }, []);

  useEffect(() => {
    fetchConfigured();
  }, [fetchConfigured]);

  // Only show connector sessions whose connector is configured.
  const connectorSessions = sessions.filter(
    (s) =>
      s.is_connector &&
      s.id !== DEFAULT_SESSION_ID &&
      (loadingConnectors || configuredConnectors.has(getConnectorKey(s)))
  );

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    connectorSessions[0]?.id ?? null
  );

  // Keep selection valid when the list changes.
  useEffect(() => {
    if (connectorSessions.length === 0) {
      setSelectedSessionId(null);
      return;
    }
    if (!selectedSessionId || !connectorSessions.find((s) => s.id === selectedSessionId)) {
      setSelectedSessionId(connectorSessions[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectorSessions.map((s) => s.id).join(",")]);

  const selectedSession = connectorSessions.find((s) => s.id === selectedSessionId) ?? null;

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
    useAppStore.getState().addMessage({ role: "user", content }, selectedSession.id);
    const payload: Record<string, unknown> = {
      type: "chat",
      content,
      session_id: selectedSession.id,
    };
    if (attachments?.length) {
      payload.attachments = attachments.map(({ name, type, data }) => ({ name, type, data }));
    }
    send(payload);
  };

  const handleStop = () => {
    if (!selectedSession) return;
    send({ type: "stop_task", session_id: selectedSession.id });
  };

  const [confirmClear, setConfirmClear] = useState(false);

  const handleClearChat = () => {
    if (!selectedSession) return;
    if (!confirmClear) {
      // First click: show confirmation
      setConfirmClear(true);
      setTimeout(() => setConfirmClear(false), 3000);
      return;
    }
    // Second click within 3 s: send clear request
    setConfirmClear(false);
    send({ type: "clear_session_history", session_id: selectedSession.id });
    // Optimistically clear the local message list
    useAppStore.getState().clearMessages(selectedSession.id);
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

        <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
          {loadingConnectors ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-4 h-4 animate-spin text-gray-600" />
            </div>
          ) : connectorSessions.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <WifiOff className="w-5 h-5 text-gray-700 mx-auto mb-2" />
              <p className="text-[11px] text-gray-600 leading-relaxed">
                No connectors configured yet.
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
                    isSelected ? "bg-gray-800/80" : "hover:bg-gray-800/40"
                  }`}
                  style={
                    isSelected
                      ? { border: `1px solid ${meta.border}` }
                      : { border: "1px solid transparent" }
                  }
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 overflow-hidden"
                    style={{ background: CONNECTOR_LOGO_MAP[key] ? "transparent" : meta.bg, border: CONNECTOR_LOGO_MAP[key] ? "none" : `1px solid ${meta.border}` }}
                  >
                    {CONNECTOR_LOGO_MAP[key]
                      ? <ConnectorLogo name={key} size={32} />
                      : <span className="text-base">{session.icon || "🔌"}</span>
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="text-[13px] font-medium truncate"
                        style={{ color: isSelected ? meta.color : "#d1d5db" }}
                      >
                        {meta.label}
                      </span>
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ background: "#34d399" }}
                        title="Session active"
                      />
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      {processing ? (
                        <Loader2 className="w-3 h-3 animate-spin" style={{ color: meta.color }} />
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

        {/* ── Add Connector card ─────────────────────────────────────────── */}
        <div className="px-2 pb-4 pt-1 border-t" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
          <button
            onClick={() => setView("connectors")}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-150 hover:bg-gray-800/40 group"
            style={{
              border: "1px dashed rgba(99,102,241,0.25)",
              background: "rgba(99,102,241,0.03)",
            }}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors"
              style={{
                background: "rgba(99,102,241,0.08)",
                border: "1px solid rgba(99,102,241,0.2)",
              }}
            >
              <Plus className="w-4 h-4 text-indigo-400 group-hover:text-indigo-300" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-[13px] font-medium text-gray-400 group-hover:text-gray-200 transition-colors block">
                Add Connector
              </span>
              <span className="text-[11px] text-gray-600 group-hover:text-gray-500 transition-colors block mt-0.5">
                Telegram, WhatsApp, Discord…
              </span>
            </div>
          </button>
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
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-100">{meta.label}</p>
    
                 <p className="text-[11px] text-gray-500">
                        Dedicated connector session · messages are isolated from main chat
                      </p>
                    </div>
                    {/* Clear Chat button */}
                    <button
                      onClick={handleClearChat}
                      title={confirmClear ? "Click again to confirm" : "Clear chat history"}
                      className={`ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all duration-200 flex-shrink-0 ${
                        confirmClear
                          ? "bg-red-500/20 text-red-400 border border-red-500/30"
                          : "bg-gray-800/60 text-gray-500 hover:text-gray-300 hover:bg-gray-700/60 border border-transparent"
                      }`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      {confirmClear ? "Confirm clear?" : "Clear chat"}
                    </button>
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
                      Messages from this connector will appear here. You can also send a
                      message directly from this panel.
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
            <ChatInput onSend={handleSend} onStop={handleStop} disabled={isProcessing} />
          </>
        ) : (
          /* Empty state when no connector is configured yet */
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-xs">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{
                  background: "rgba(99,102,241,0.08)",
                  border: "1px solid rgba(99,102,241,0.15)",
                }}
              >
                <Plus className="w-6 h-6 text-indigo-400" />
              </div>
              <p className="text-sm font-semibold text-gray-300 mb-1">No connectors yet</p>
              <p className="text-[12px] text-gray-500 leading-relaxed mb-5">
                Connect Telegram, WhatsApp, Discord, or a custom connector to chat with
                Plutus from anywhere.
              </p>
              <button
                onClick={() => setView("connectors")}
                className="px-5 py-2 rounded-xl text-sm font-medium text-white transition-all duration-200 active:scale-[0.97]"
                style={{
                  background: "linear-gradient(135deg, #6366f1, #4f46e5)",
                  boxShadow: "0 4px 16px rgba(99, 102, 241, 0.3)",
                }}
              >
                Set up a Connector
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

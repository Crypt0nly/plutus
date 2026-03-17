/**
 * SessionTabBar — shows all active sessions as horizontal tabs.
 *
 * Features:
 * - Clicking a tab switches the active session (all chat state is per-session)
 * - "+" button creates a new user session
 * - Connector sessions (Telegram, WhatsApp, etc.) show a small connector badge
 * - Close button on non-connector, non-main sessions
 * - Spinner on tabs whose session is currently processing
 */

import { Plus, X, Loader2 } from "lucide-react";
import { useAppStore, DEFAULT_SESSION_ID } from "../../stores/appStore";

interface SessionTabBarProps {
  send: (data: Record<string, unknown>) => void;
}

export function SessionTabBar({ send }: SessionTabBarProps) {
  const {
    sessions,
    activeSessionId,
    setActiveSessionId,
    addSession,
    removeSession,
    sessionStates,
  } = useAppStore();

  // Only show the tab bar when there is more than one session
  // (or always show it so users know multi-session exists)
  const showBar = sessions.length > 0;
  if (!showBar) return null;

  const handleNewSession = () => {
    send({ type: "new_session", display_name: "New Chat", icon: "💬" });
  };

  const handleCloseSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    send({ type: "close_session", session_id: sessionId });
    removeSession(sessionId);
    // If we closed the active session, switch to main
    if (activeSessionId === sessionId) {
      setActiveSessionId(DEFAULT_SESSION_ID);
    }
  };

  return (
    <div
      className="flex items-center gap-0.5 px-2 pt-1.5 pb-0 overflow-x-auto scrollbar-hide border-b"
      style={{
        borderColor: "rgba(99, 102, 241, 0.12)",
        background: "rgba(15, 15, 25, 0.6)",
        backdropFilter: "blur(8px)",
        minHeight: "38px",
      }}
    >
      {sessions.map((session) => {
        const isActive = session.id === activeSessionId;
        const state = sessionStates[session.id];
        const isProcessing = state?.isProcessing ?? false;
        const canClose =
          !session.is_connector && session.id !== DEFAULT_SESSION_ID;

        return (
          <button
            key={session.id}
            onClick={() => setActiveSessionId(session.id)}
            className={`
              group relative flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs font-medium
              transition-all duration-150 whitespace-nowrap flex-shrink-0
              ${
                isActive
                  ? "text-white"
                  : "text-gray-500 hover:text-gray-300"
              }
            `}
            style={
              isActive
                ? {
                    background:
                      "linear-gradient(180deg, rgba(99,102,241,0.15) 0%, rgba(99,102,241,0.05) 100%)",
                    borderBottom: "2px solid rgba(99,102,241,0.7)",
                    paddingBottom: "calc(0.375rem - 2px)",
                  }
                : {
                    background: "transparent",
                    borderBottom: "2px solid transparent",
                  }
            }
            title={session.display_name}
          >
            {/* Icon */}
            <span className="text-sm leading-none">{session.icon}</span>

            {/* Name */}
            <span className="max-w-[100px] truncate">{session.display_name}</span>

            {/* Processing spinner */}
            {isProcessing && (
              <Loader2
                className="w-3 h-3 animate-spin flex-shrink-0"
                style={{ color: "#818cf8" }}
              />
            )}

            {/* Connector badge */}
            {session.is_connector && (
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ background: "#34d399" }}
                title="Connector session (persistent)"
              />
            )}

            {/* Close button */}
            {canClose && (
              <span
                role="button"
                onClick={(e) => handleCloseSession(e, session.id)}
                className="
                  w-4 h-4 rounded flex items-center justify-center flex-shrink-0
                  opacity-0 group-hover:opacity-100 transition-opacity
                  hover:bg-white/10 text-gray-500 hover:text-gray-200
                "
                title="Close session"
              >
                <X className="w-2.5 h-2.5" />
              </span>
            )}
          </button>
        );
      })}

      {/* New session button */}
      <button
        onClick={handleNewSession}
        className="
          flex items-center justify-center w-6 h-6 rounded-md ml-1 flex-shrink-0
          text-gray-600 hover:text-gray-300 hover:bg-white/5
          transition-all duration-150
        "
        title="New chat session"
      >
        <Plus className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

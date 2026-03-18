import { useCallback, useEffect } from "react";
import { useAppStore } from "./stores/appStore";
import { useWebSocket } from "./hooks/useWebSocket";
import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { ChatView } from "./components/chat/ChatView";
import { DashboardView } from "./components/dashboard/DashboardView";
import { GuardrailsView } from "./components/guardrails/GuardrailsView";
import { SettingsView } from "./components/settings/SettingsView";
import { ToolsView } from "./components/tools/ToolsView";
import { WorkersView } from "./components/workers/WorkersView";
import { ToolCreatorView } from "./components/tool-creator/ToolCreatorView";
import SkillsView from "./components/skills/SkillsView";
import { MemoryView } from "./components/memory/MemoryView";
import ConnectorsView from "./components/connectors/ConnectorsView";
import SessionsView from "./components/sessions/SessionsView";
import { OnboardingWizard } from "./components/onboarding/OnboardingWizard";
import { UpdateBanner } from "./components/layout/UpdateBanner";
import { ConnectionBanner } from "./components/layout/ConnectionBanner";
import { ConversationPanel } from "./components/layout/ConversationPanel";
import { PanelLeft } from "lucide-react";
import type { WSMessage } from "./lib/types";
import { api } from "./lib/api";
import { useTheme } from "./hooks/useTheme";

function HistoryPillToggle() {
  const { historyPanelOpen, toggleHistoryPanel } = useAppStore();

  return (
    <button
      onClick={toggleHistoryPanel}
      title={historyPanelOpen ? "Hide conversations" : "Show conversations"}
      className={`absolute left-0 top-1/2 -translate-y-1/2 z-20
        w-5 h-12 flex items-center justify-center
        rounded-r-full border border-l-0
        transition-all duration-200
        ${
          historyPanelOpen
            ? "bg-plutus-500/15 border-plutus-500/30 text-plutus-400"
            : "bg-gray-900/80 border-gray-700/50 text-gray-500 hover:text-gray-300 hover:bg-gray-800/80"
        }`}
    >
      <PanelLeft className="w-3.5 h-3.5" />
    </button>
  );
}

export default function App() {
  const {
    view,
    setView,
    addMessage,
    setProcessing,
    setConnected,
    setCurrentTier,
    setConversationId,
    setKeyConfigured,
    clearMessages,
    onboardingCompleted,
    setOnboardingCompleted,
    setUpdateInfo,
    theme,
    // Multi-session
    setSessions,
    addSession,
    removeSession,
    setActiveSessionId,
  } = useAppStore();

  useTheme(theme);

  const handleWSMessage = useCallback(
    (msg: any) => {
      // All messages from the backend carry an optional session_id.
      // We route chat events to the correct session; global events (connection,
      // updates, workers) are handled without a session context.
      const sid: string | undefined = msg.session_id;

      switch (msg.type) {
        case "thinking":
          setProcessing(true, sid);
          break;

        case "text": {
          // Connector bridges send role: "user" for incoming user messages.
          // All other text events default to "assistant".
          const textRole = msg.role === "user" ? "user" : "assistant";
          addMessage({ role: textRole, content: msg.content }, sid);
          break;
        }

        case "tool_call": {
          const toolName = msg.tool || "";
          const args = msg.arguments || {};

          // Computer use actions (computer.screenshot, computer.click, etc.)
          if (toolName.startsWith("computer.")) {
            const action = toolName.replace("computer.", "");
            const actionLabels: Record<string, string> = {
              screenshot: "Taking screenshot...",
              click: `Clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              left_click: `Clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              right_click: `Right-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              double_click: `Double-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              type: `Typing: "${(args.text || "").slice(0, 50)}${(args.text || "").length > 50 ? "..." : ""}"`,
              key: `Pressing: ${args.text}`,
              scroll: `Scrolling ${args.coordinate ? `at (${args.coordinate[0]}, ${args.coordinate[1]})` : ""}`,
              move: `Moving to (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              wait: "Waiting...",
              triple_click: `Triple-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
            };

            addMessage({
              role: "assistant",
              content: actionLabels[action] || action,
              tool_calls: [{ id: msg.id || "", name: toolName, arguments: args }],
            }, sid);
          } else {
            // Standard tool calls — show friendly operation label
            const operation = args.operation || args.action || "";
            const friendlyName = operation
              ? operation.replace(/_/g, " ")
              : toolName.replace(/_/g, " ");

            addMessage({
              role: "assistant",
              content: `Using tool: **${friendlyName}**`,
              tool_calls: [{ id: msg.id || "", name: toolName, arguments: args }],
            }, sid);
          }
          break;
        }

        case "tool_result": {
          if (msg.screenshot && msg.image_base64) {
            addMessage({
              role: "tool",
              content: `__SCREENSHOT__:${msg.image_base64}`,
              tool_call_id: msg.id,
            }, sid);
          } else if (msg.error) {
            addMessage({
              role: "tool",
              content: `[ERROR] ${msg.result || "Unknown error"}`,
              tool_call_id: msg.id,
            }, sid);
          } else {
            addMessage({
              role: "tool",
              content: msg.result || "Done",
              tool_call_id: msg.id,
            }, sid);
          }
          break;
        }

        case "tool_approval_needed":
          addMessage({
            role: "system",
            content: `Approval needed for **${msg.tool}**: ${msg.reason}`,
            approval_id: msg.approval_id,
          }, sid);
          break;

        case "mode":
          // Mode indicator — no longer show separate mode banners
          break;

        case "iteration":
          addMessage({
            role: "system",
            content: `Step ${msg.number}/${msg.max}`,
          }, sid);
          break;

        case "error":
          addMessage({ role: "system", content: `Error: ${msg.message}` }, sid);
          setProcessing(false, sid);
          break;

        case "done":
          setProcessing(false, sid);
          break;

        case "cancelled":
        case "task_stopped":
          addMessage({ role: "system", content: `${msg.message || "Task stopped"}` }, sid);
          setProcessing(false, sid);
          break;

        case "conversation_started":
          setConversationId(msg.conversation_id, sid);
          break;

        case "conversation_resumed":
          // Ensure the active session matches where the conversation is being loaded.
          // sid comes from the backend (which echoes back the session_id we sent).
          if (sid) setActiveSessionId(sid);
          setConversationId(msg.conversation_id, sid);
          // Only clear isProcessing if this session is NOT currently working.
          // If the user switches away and back while Plutus is still running,
          // we must preserve isProcessing=true so the dot-pulse stays visible.
          // We only clear it to remove stale flags from previously finished tasks.
          if (!useAppStore.getState().sessionStates[sid]?.isProcessing) {
            setProcessing(false, sid);
          }
          clearMessages(sid);
          msg.messages.forEach((m: any) => {
            // Remap internal/system messages that were stored as "user" role
            if (m.role === "user" && typeof m.content === "string") {
              if (m.content.startsWith("[HEARTBEAT]")) {
                addMessage({ ...m, role: "system" }, sid);
                return;
              }
              if (m.content.startsWith("[SYSTEM NOTIFICATION]")) {
                addMessage({ ...m, role: "system" }, sid);
                return;
              }
              if (m.content.startsWith("[SYSTEM]")) {
                addMessage({ ...m, role: "system" }, sid);
                return;
              }
            }
            addMessage(m, sid);
          });
          // Navigate to chat view so the loaded messages are visible
          setView("chat");
          break;

        // ── Session management events ──────────────────────────────────
        case "sessions_list":
          if (Array.isArray(msg.sessions)) {
            setSessions(
              msg.sessions.map((s: any) => ({
                id: s.session_id || s.id,
                display_name: s.display_name,
                icon: s.icon,
                is_connector: s.is_connector,
                connector_name: s.connector_name,
                conversation_id: s.conversation_id,
                is_processing: s.is_processing ?? false,
                created_at: s.created_at,
                last_active: s.last_active,
              }))
            );
          }
          break;

        case "session_created": {
          const s = msg.session;
          if (s) {
            const newId = s.session_id || s.id;
            addSession({
              id: newId,
              display_name: s.display_name,
              icon: s.icon,
              is_connector: s.is_connector,
              connector_name: s.connector_name,
              conversation_id: s.conversation_id,
              is_processing: false,
              created_at: s.created_at,
              last_active: s.last_active,
            });
            // Seed the sessionState with the conversation_id from the session
            // object so the spinner can activate as soon as thinking fires,
            // without waiting for a separate conversation_started event.
            if (s.conversation_id) {
              setConversationId(s.conversation_id, newId);
            }
            // Only auto-switch for user-created sessions, not connector sessions.
            // Connector sessions are pre-created at startup and should never
            // hijack the user's active chat.
            if (!s.is_connector) {
              setActiveSessionId(newId);
            }
            // Fire the one-shot callback registered by ChatView so the first
            // message is sent to the correct session even if the user switched
            // chats while waiting for session_created.
            const cb = useAppStore.getState().pendingSessionCallback;
            if (cb) {
              useAppStore.getState().setPendingSessionCallback(null);
              cb(newId);
            }
          }
          break;
        }

        case "session_closed":
          if (msg.session_id) {
            removeSession(msg.session_id);
          }
          break;

        case "session_history_cleared":
          // Backend confirmed the clear — ensure the frontend message list is empty
          clearMessages(sid);
          break;

        case "heartbeat":
          addMessage({
            role: "system",
            content: `Heartbeat #${msg.beat}/${msg.max}`,
          }, sid);
          setProcessing(true, sid);
          break;

        case "heartbeat_paused":
          addMessage({
            role: "system",
            content: `Heartbeat paused: ${msg.reason} (after ${msg.count} beats)`,
          }, sid);
          break;

        case "attachment": {
          // File or image sent by the agent — show inline in chat
          if (msg.is_image && msg.image_base64) {
            const caption = msg.caption ? `\n${msg.caption}` : "";
            addMessage({
              role: "tool",
              content: `__ATTACHMENT_IMAGE__:${msg.file_name}:${msg.image_base64}${caption}`,
            }, sid);
          } else {
            const sizeKB = Math.round((msg.file_size || 0) / 1024);
            const caption = msg.caption ? ` — ${msg.caption}` : "";
            addMessage({
              role: "tool",
              content: `__ATTACHMENT_FILE__:${msg.file_name}:${sizeKB}:${msg.file_path}${caption}`,
            }, sid);
          }
          break;
        }

        case "plan_update":
          break;

        // ── Worker events ─────────────────────────────────────────────
        case "worker_result": {
          // A background worker finished — show its result in chat with special prefix
          const workerName = msg.name || "Worker";
          const workerModel = msg.model || "";
          const workerResult = msg.result || "(no output)";
          addMessage({
            role: "assistant",
            content: `__WORKER_RESULT__:${workerName}:${workerModel}:${workerResult}`,
          }, sid);
          break;
        }

        case "worker_started": {
          // A worker started running — subtle notification
          const w = msg.worker || {};
          addMessage({
            role: "system",
            content: `__WORKER_STARTED__:${w.name || w.task_id}:${w.model || "auto"}`,
          }, sid);
          break;
        }

        case "worker_completed":
        case "worker_status":
          // These are handled by the workers panel, not chat
          break;
      }
    },
    [addMessage, setProcessing, setConversationId, clearMessages, setSessions, addSession, removeSession, setActiveSessionId]
  );

  const { send, connected } = useWebSocket(handleWSMessage);

  useEffect(() => {
    setConnected(connected);
  }, [connected, setConnected]);

  // Load initial status (including onboarding state)
  useEffect(() => {
    api.getStatus().then((status: any) => {
      if (status?.guardrails?.tier) {
        setCurrentTier(status.guardrails.tier);
      }
      if (status?.key_configured !== undefined) {
        setKeyConfigured(status.key_configured);
      }
      setOnboardingCompleted(status?.onboarding_completed ?? true);
    }).catch(() => {
      // If status fails, assume onboarding is done (don't block the UI)
      setOnboardingCompleted(true);
    });
  }, [setCurrentTier, setKeyConfigured, setOnboardingCompleted]);

  // Check for updates on mount, then every 6 hours
  useEffect(() => {
    const check = () => {
      api.checkForUpdate().then((res) => {
        if (res.error) {
          console.warn("[update-check] Backend error:", res.error);
        }
        if (res.update_available) {
          setUpdateInfo({
            available: true,
            dismissed: res.dismissed ?? false,
            currentVersion: res.current_version,
            latestVersion: res.latest_version,
            releaseName: res.release_name || "",
            releaseNotes: res.release_notes || "",
            releaseUrl: res.release_url || "",
            publishedAt: res.published_at || "",
          });
        }
      }).catch((e) => {
        console.warn("[update-check] Failed:", e);
      });
    };
    // Initial check after a short delay so the app loads fast
    const initial = setTimeout(check, 2_000);
    const interval = setInterval(check, 6 * 60 * 60 * 1000);
    return () => {
      clearTimeout(initial);
      clearInterval(interval);
    };
  }, [setUpdateInfo]);

  // Show loading state while checking onboarding status
  if (onboardingCompleted === null) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-950">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-plutus-500 to-plutus-700 flex items-center justify-center font-bold text-lg shadow-lg shadow-plutus-600/20 ring-1 ring-white/10">
            P
          </div>
          <div className="w-6 h-6 border-2 border-plutus-500/30 border-t-plutus-500 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  // Show onboarding wizard for first-time users
  if (!onboardingCompleted) {
    return <OnboardingWizard />;
  }

  const viewComponents: Record<string, React.ReactNode> = {
    chat: <ChatView send={send} />,
    sessions: <SessionsView send={send} />,
    dashboard: <DashboardView />,
    guardrails: <GuardrailsView />,
    settings: <SettingsView />,
    tools: <ToolsView />,
    workers: <WorkersView />,
    "tool-creator": <ToolCreatorView />,
    skills: <SkillsView />,
    memory: <MemoryView />,
    connectors: <ConnectorsView />,
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar send={send} />
      <ConversationPanel send={send} />
      <div className="relative flex-1 flex flex-col min-w-0">
        {view === "chat" && <HistoryPillToggle />}
        <ConnectionBanner />
        <UpdateBanner />
        <Header />
        <main className={`flex-1 flex flex-col ${(view === "chat" || view === "sessions") ? "overflow-hidden" : "overflow-y-auto p-6"}`}>
          {viewComponents[view] || viewComponents.chat}
        </main>
      </div>
    </div>
  );
}

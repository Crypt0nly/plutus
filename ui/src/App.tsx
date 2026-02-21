import { useCallback, useEffect } from "react";
import { useAppStore } from "./stores/appStore";
import { useWebSocket } from "./hooks/useWebSocket";
import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { ChatView } from "./components/chat/ChatView";
import { DashboardView } from "./components/dashboard/DashboardView";
import { GuardrailsView } from "./components/guardrails/GuardrailsView";
import { SettingsView } from "./components/settings/SettingsView";
import type { WSMessage } from "./lib/types";
import { api } from "./lib/api";

export default function App() {
  const {
    view,
    addMessage,
    setProcessing,
    setConnected,
    setCurrentTier,
    setConversationId,
    setKeyConfigured,
    clearMessages,
  } = useAppStore();

  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case "thinking":
          setProcessing(true);
          break;

        case "text":
          addMessage({ role: "assistant", content: msg.content });
          break;

        case "tool_call":
          addMessage({
            role: "assistant",
            content: `Using tool: **${msg.tool}**`,
            tool_calls: [{ id: msg.id, name: msg.tool, arguments: msg.arguments }],
          });
          break;

        case "tool_approval_needed":
          addMessage({
            role: "system",
            content: `Approval needed for **${msg.tool}**: ${msg.reason}`,
          });
          break;

        case "tool_result":
          addMessage({
            role: "tool",
            content: msg.result,
            tool_call_id: msg.id,
          });
          break;

        case "error":
          addMessage({ role: "system", content: `Error: ${msg.message}` });
          setProcessing(false);
          break;

        case "done":
          setProcessing(false);
          break;

        case "conversation_started":
          setConversationId(msg.conversation_id);
          break;

        case "conversation_resumed":
          setConversationId(msg.conversation_id);
          clearMessages();
          msg.messages.forEach((m) => addMessage(m));
          break;

        case "heartbeat":
          addMessage({
            role: "system",
            content: `Heartbeat #${msg.beat}/${msg.max}`,
          });
          setProcessing(true);
          break;

        case "heartbeat_paused":
          addMessage({
            role: "system",
            content: `Heartbeat paused: ${msg.reason} (after ${msg.count} beats)`,
          });
          break;

        case "plan_update":
          // Plan updates flow through tool_call/tool_result already;
          // this is an extra event for the UI to refresh plan display
          break;
      }
    },
    [addMessage, setProcessing, setConversationId, clearMessages]
  );

  const { send, connected } = useWebSocket(handleWSMessage);

  useEffect(() => {
    setConnected(connected);
  }, [connected, setConnected]);

  // Load initial status
  useEffect(() => {
    api.getStatus().then((status: any) => {
      if (status?.guardrails?.tier) {
        setCurrentTier(status.guardrails.tier);
      }
      if (status?.key_configured !== undefined) {
        setKeyConfigured(status.key_configured);
      }
    }).catch(() => {});
  }, [setCurrentTier, setKeyConfigured]);

  const viewComponents = {
    chat: <ChatView send={send} />,
    dashboard: <DashboardView />,
    guardrails: <GuardrailsView />,
    settings: <SettingsView />,
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-hidden">{viewComponents[view]}</main>
      </div>
    </div>
  );
}

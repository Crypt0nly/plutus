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
import PCControlView from "./components/pc-control/PCControlView";
import SkillsView from "./components/skills/SkillsView";
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
    (msg: any) => {
      switch (msg.type) {
        case "thinking":
          setProcessing(true);
          break;

        case "text":
          addMessage({ role: "assistant", content: msg.content });
          break;

        case "tool_call": {
          // Handle both standard tool calls and computer use actions
          const toolName = msg.tool || "";
          const args = msg.arguments || {};

          // Computer use actions (computer.screenshot, computer.click, etc.)
          if (toolName.startsWith("computer.")) {
            const action = toolName.replace("computer.", "");
            const actionLabels: Record<string, string> = {
              screenshot: "📸 Taking screenshot...",
              click: `🖱️ Clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              left_click: `🖱️ Clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              right_click: `🖱️ Right-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              double_click: `🖱️ Double-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              type: `⌨️ Typing: "${(args.text || "").slice(0, 50)}${(args.text || "").length > 50 ? "..." : ""}"`,
              key: `⌨️ Pressing: ${args.text}`,
              scroll: `📜 Scrolling ${args.coordinate ? `at (${args.coordinate[0]}, ${args.coordinate[1]})` : ""} ${args.delta_x || args.delta_y ? `by (${args.delta_x || 0}, ${args.delta_y || 0})` : ""}`,
              move: `🖱️ Moving to (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
              wait: "⏳ Waiting...",
              triple_click: `🖱️ Triple-clicking at (${args.coordinate?.[0]}, ${args.coordinate?.[1]})`,
            };

            addMessage({
              role: "assistant",
              content: actionLabels[action] || `🖥️ ${action}`,
              tool_calls: [{ id: msg.id || "", name: toolName, arguments: args }],
            });
          } else {
            addMessage({
              role: "assistant",
              content: `Using tool: **${toolName}**`,
              tool_calls: [{ id: msg.id || "", name: toolName, arguments: args }],
            });
          }
          break;
        }

        case "tool_result": {
          // Handle screenshot results with images
          if (msg.screenshot && msg.image_base64) {
            addMessage({
              role: "tool",
              content: `__SCREENSHOT__:${msg.image_base64}`,
              tool_call_id: msg.id,
            });
          } else if (msg.error) {
            addMessage({
              role: "tool",
              content: `[ERROR] ${msg.result || "Unknown error"}`,
              tool_call_id: msg.id,
            });
          } else {
            addMessage({
              role: "tool",
              content: msg.result || "Done",
              tool_call_id: msg.id,
            });
          }
          break;
        }

        case "tool_approval_needed":
          addMessage({
            role: "system",
            content: `Approval needed for **${msg.tool}**: ${msg.reason}`,
          });
          break;

        case "mode":
          // Computer use mode indicator
          addMessage({
            role: "system",
            content: msg.mode === "computer_use"
              ? "🖥️ Computer Use mode — I can see and control your screen"
              : "💻 Standard mode — code and file operations",
          });
          break;

        case "iteration":
          // Progress indicator for computer use loops
          addMessage({
            role: "system",
            content: `Step ${msg.number}/${msg.max}`,
          });
          break;

        case "error":
          addMessage({ role: "system", content: `Error: ${msg.message}` });
          setProcessing(false);
          break;

        case "done":
          setProcessing(false);
          break;

        case "cancelled":
        case "task_stopped":
          addMessage({ role: "system", content: `⏹️ ${msg.message || "Task stopped"}` });
          setProcessing(false);
          break;

        case "conversation_started":
          setConversationId(msg.conversation_id);
          break;

        case "conversation_resumed":
          setConversationId(msg.conversation_id);
          clearMessages();
          msg.messages.forEach((m: any) => addMessage(m));
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

  const viewComponents: Record<string, React.ReactNode> = {
    chat: <ChatView send={send} />,
    dashboard: <DashboardView />,
    guardrails: <GuardrailsView />,
    settings: <SettingsView />,
    tools: <ToolsView />,
    workers: <WorkersView />,
    "tool-creator": <ToolCreatorView />,
    "pc-control": <PCControlView />,
    skills: <SkillsView />,
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {viewComponents[view] || viewComponents.chat}
        </main>
      </div>
    </div>
  );
}

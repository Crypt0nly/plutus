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
            });
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
            });
          }
          break;
        }

        case "tool_result": {
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
            approval_id: msg.approval_id,
          });
          break;

        case "mode":
          // Mode indicator — no longer show separate mode banners
          break;

        case "iteration":
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
          addMessage({ role: "system", content: `${msg.message || "Task stopped"}` });
          setProcessing(false);
          break;

        case "conversation_started":
          setConversationId(msg.conversation_id);
          break;

        case "conversation_resumed":
          setConversationId(msg.conversation_id);
          clearMessages();
          msg.messages.forEach((m: any) => {
            // Remap internal/system messages that were stored as "user" role
            if (m.role === "user" && typeof m.content === "string") {
              if (m.content.startsWith("[HEARTBEAT]")) {
                addMessage({ ...m, role: "system" });
                return;
              }
              if (m.content.startsWith("[SYSTEM NOTIFICATION]")) {
                addMessage({ ...m, role: "system" });
                return;
              }
              if (m.content.startsWith("[SYSTEM]")) {
                addMessage({ ...m, role: "system" });
                return;
              }
            }
            addMessage(m);
          });
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

        case "attachment": {
          // File or image sent by the agent — show inline in chat
          if (msg.is_image && msg.image_base64) {
            const caption = msg.caption ? `\n${msg.caption}` : "";
            addMessage({
              role: "tool",
              content: `__ATTACHMENT_IMAGE__:${msg.file_name}:${msg.image_base64}${caption}`,
            });
          } else {
            const sizeKB = Math.round((msg.file_size || 0) / 1024);
            const caption = msg.caption ? ` — ${msg.caption}` : "";
            addMessage({
              role: "tool",
              content: `__ATTACHMENT_FILE__:${msg.file_name}:${sizeKB}:${msg.file_path}${caption}`,
            });
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
          });
          break;
        }

        case "worker_started": {
          // A worker started running — subtle notification
          const w = msg.worker || {};
          addMessage({
            role: "system",
            content: `__WORKER_STARTED__:${w.name || w.task_id}:${w.model || "auto"}`,
          });
          break;
        }

        case "worker_completed":
        case "worker_status":
          // These are handled by the workers panel, not chat
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
    skills: <SkillsView />,
    memory: <MemoryView />,
    connectors: <ConnectorsView />,
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar send={send} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        <main className="flex-1 flex flex-col overflow-hidden p-6">
          {viewComponents[view] || viewComponents.chat}
        </main>
      </div>
    </div>
  );
}

import { PanelLeftClose } from "lucide-react";
import { useAppStore } from "../../stores/appStore";
import { ConversationHistory } from "../chat/ConversationHistory";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

export function ConversationPanel({ send }: Props) {
  const { view, historyPanelOpen, setHistoryPanelOpen } = useAppStore();

  const visible = view === "chat" && historyPanelOpen;

  return (
    <div
      className={`shrink-0 h-full transition-all duration-300 ease-out overflow-hidden ${
        visible ? "w-72 opacity-100" : "w-0 opacity-0"
      }`}
    >
      <div className="w-72 h-full flex flex-col bg-gray-900 border-r border-gray-700/30">
        {/* Panel header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <h2 className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">
            History
          </h2>
          <button
            onClick={() => setHistoryPanelOpen(false)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-gray-200 hover:bg-gray-800/50 transition-colors"
            title="Close panel"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>

        {/* Divider */}
        <div className="sidebar-divider mx-3 h-px" />

        {/* Conversation list */}
        <div className="flex-1 min-h-0 flex flex-col">
          <ConversationHistory send={send} />
        </div>
      </div>
    </div>
  );
}

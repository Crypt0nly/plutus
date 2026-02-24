import { useEffect, useState, useRef, useCallback } from "react";
import {
  MessageSquare,
  Trash2,
  Pencil,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  Clock,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import type { Conversation } from "../../lib/types";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

export function ConversationHistory({ send }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const { conversationId, setConversationId, clearMessages, setView } =
    useAppStore();

  const fetchConversations = useCallback(() => {
    api
      .getConversations(50)
      .then((data) => setConversations(data as unknown as Conversation[]))
      .catch(() => {});
  }, []);

  // Fetch conversations on mount and when conversationId changes
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations, conversationId]);

  // Refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchConversations, 30000);
    return () => clearInterval(interval);
  }, [fetchConversations]);

  // Focus edit input when editing starts
  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const handleLoadConversation = (conv: Conversation) => {
    if (conv.id === conversationId) return;
    send({ type: "resume_conversation", conversation_id: conv.id });
    setView("chat");
  };

  const handleDelete = async (convId: string) => {
    try {
      await api.deleteConversation(convId);
      if (convId === conversationId) {
        clearMessages();
        setConversationId(null);
      }
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      setConfirmDeleteId(null);
    } catch (e) {
      console.error("Failed to delete conversation:", e);
    }
  };

  const handleRename = async (convId: string) => {
    const trimmed = editTitle.trim();
    if (!trimmed) {
      setEditingId(null);
      return;
    }
    try {
      await api.renameConversation(convId, trimmed);
      setConversations((prev) =>
        prev.map((c) => (c.id === convId ? { ...c, title: trimmed } : c))
      );
    } catch (e) {
      console.error("Failed to rename:", e);
    }
    setEditingId(null);
  };

  const startEditing = (conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title || getDefaultTitle(conv));
    setConfirmDeleteId(null);
  };

  const getDefaultTitle = (conv: Conversation): string => {
    return `Chat ${new Date(conv.created_at * 1000).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    })}`;
  };

  const formatTimeAgo = (timestamp: number): string => {
    const seconds = Math.floor(Date.now() / 1000 - timestamp);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return new Date(timestamp * 1000).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  };

  // Group conversations: Today, Yesterday, This Week, Older
  const grouped = groupConversations(conversations);

  if (conversations.length === 0) return null;

  return (
    <div className="mt-1">
      {/* Toggle header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-[10px] font-semibold text-gray-600 uppercase tracking-wider hover:text-gray-400 transition-colors"
      >
        <span>History</span>
        <div className="flex items-center gap-1">
          <span className="text-[9px] font-normal normal-case text-gray-600">
            {conversations.length}
          </span>
          {expanded ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="space-y-2 max-h-[40vh] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-800 scrollbar-track-transparent">
          {grouped.map(
            (group) =>
              group.items.length > 0 && (
                <div key={group.label}>
                  <p className="text-[9px] text-gray-600 px-3 py-0.5">
                    {group.label}
                  </p>
                  <div className="space-y-0.5">
                    {group.items.map((conv) => {
                      const isActive = conv.id === conversationId;
                      const isEditing = editingId === conv.id;
                      const isConfirmingDelete = confirmDeleteId === conv.id;

                      return (
                        <div
                          key={conv.id}
                          className={`group relative flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all cursor-pointer ${
                            isActive
                              ? "bg-plutus-600/15 text-plutus-300"
                              : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
                          }`}
                          onClick={() =>
                            !isEditing &&
                            !isConfirmingDelete &&
                            handleLoadConversation(conv)
                          }
                        >
                          <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-50" />

                          {isEditing ? (
                            <div className="flex-1 flex items-center gap-1 min-w-0">
                              <input
                                ref={editInputRef}
                                className="flex-1 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-200 focus:outline-none focus:border-plutus-500/50 min-w-0"
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter")
                                    handleRename(conv.id);
                                  if (e.key === "Escape")
                                    setEditingId(null);
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRename(conv.id);
                                }}
                                className="p-0.5 text-emerald-400 hover:text-emerald-300"
                              >
                                <Check className="w-3 h-3" />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingId(null);
                                }}
                                className="p-0.5 text-gray-500 hover:text-gray-300"
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </div>
                          ) : isConfirmingDelete ? (
                            <div className="flex-1 flex items-center justify-between min-w-0">
                              <span className="text-xs text-red-400 truncate">
                                Delete?
                              </span>
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDelete(conv.id);
                                  }}
                                  className="px-1.5 py-0.5 text-[10px] bg-red-500/20 text-red-400 rounded hover:bg-red-500/30"
                                >
                                  Yes
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConfirmDeleteId(null);
                                  }}
                                  className="px-1.5 py-0.5 text-[10px] bg-gray-700 text-gray-400 rounded hover:bg-gray-600"
                                >
                                  No
                                </button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs truncate font-medium">
                                  {conv.title || getDefaultTitle(conv)}
                                </p>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                  <Clock className="w-2.5 h-2.5 text-gray-600" />
                                  <span className="text-[10px] text-gray-600">
                                    {formatTimeAgo(conv.last_activity)}
                                  </span>
                                  {conv.message_count > 0 && (
                                    <span className="text-[10px] text-gray-600">
                                      · {conv.message_count} msgs
                                    </span>
                                  )}
                                </div>
                              </div>

                              {/* Action buttons — visible on hover */}
                              <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    startEditing(conv);
                                  }}
                                  className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-700/50"
                                  title="Rename"
                                >
                                  <Pencil className="w-3 h-3" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConfirmDeleteId(conv.id);
                                    setEditingId(null);
                                  }}
                                  className="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10"
                                  title="Delete"
                                >
                                  <Trash2 className="w-3 h-3" />
                                </button>
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )
          )}
        </div>
      )}
    </div>
  );
}

interface ConversationGroup {
  label: string;
  items: Conversation[];
}

function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const now = Date.now() / 1000;
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayTs = todayStart.getTime() / 1000;
  const yesterdayTs = todayTs - 86400;
  const weekTs = todayTs - 7 * 86400;

  const groups: ConversationGroup[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "This Week", items: [] },
    { label: "Older", items: [] },
  ];

  for (const conv of conversations) {
    const ts = conv.last_activity || conv.created_at;
    if (ts >= todayTs) {
      groups[0].items.push(conv);
    } else if (ts >= yesterdayTs) {
      groups[1].items.push(conv);
    } else if (ts >= weekTs) {
      groups[2].items.push(conv);
    } else {
      groups[3].items.push(conv);
    }
  }

  return groups;
}

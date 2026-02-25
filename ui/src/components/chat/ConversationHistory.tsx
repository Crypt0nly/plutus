import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import {
  Trash2,
  Pencil,
  Check,
  X,
  Search,
  MoreHorizontal,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import type { Conversation } from "../../lib/types";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

export function ConversationHistory({ send }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const { conversationId, setConversationId, clearMessages, setView } =
    useAppStore();

  const fetchConversations = useCallback(() => {
    api
      .getConversations(50)
      .then((data) => setConversations(data as unknown as Conversation[]))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations, conversationId]);

  useEffect(() => {
    const interval = setInterval(fetchConversations, 30000);
    return () => clearInterval(interval);
  }, [fetchConversations]);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  // Close menu on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    if (menuOpenId) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpenId]);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter((c) => {
      const title = c.title || getDefaultTitle(c);
      return title.toLowerCase().includes(q);
    });
  }, [conversations, searchQuery]);

  const grouped = useMemo(
    () => groupConversations(filteredConversations),
    [filteredConversations]
  );

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
      setMenuOpenId(null);
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
    setMenuOpenId(null);
  };

  if (conversations.length === 0) return null;

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* Search bar — compact */}
      <div className="px-2 pt-1 pb-1.5">
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded-md transition-all duration-200 ${
            searchFocused
              ? "bg-gray-800 ring-1 ring-plutus-500/30"
              : "bg-gray-800/50 hover:bg-gray-800/80"
          }`}
        >
          <Search className="w-3 h-3 text-gray-500 shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            className="flex-1 bg-transparent text-[11px] text-gray-300 placeholder-gray-600 focus:outline-none min-w-0"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="p-0.5 rounded text-gray-500 hover:text-gray-300 transition-colors"
            >
              <X className="w-2.5 h-2.5" />
            </button>
          )}
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-1.5 pb-1.5 sidebar-scroll">
        {filteredConversations.length === 0 ? (
          <div className="px-3 py-4 text-center">
            <Search className="w-4 h-4 text-gray-700 mx-auto mb-1.5" />
            <p className="text-[11px] text-gray-600">
              {searchQuery ? "No matches found" : "No conversations yet"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {grouped.map(
              (group) =>
                group.items.length > 0 && (
                  <div key={group.label}>
                    {/* Group header */}
                    <div className="flex items-center gap-2 px-1.5 mb-0.5">
                      <span className="text-[9px] font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap">
                        {group.label}
                      </span>
                      <div className="flex-1 h-px bg-gray-800/60" />
                    </div>

                    {/* Conversation items */}
                    <div className="space-y-0.5">
                      {group.items.map((conv) => {
                        const isActive = conv.id === conversationId;
                        const isEditing = editingId === conv.id;
                        const isConfirmingDelete = confirmDeleteId === conv.id;
                        const isMenuOpen = menuOpenId === conv.id;

                        return (
                          <div
                            key={conv.id}
                            className="conv-item animate-fade-in"
                          >
                            {isEditing ? (
                              /* Editing mode */
                              <div className="flex items-center gap-1.5 px-2 py-2 rounded-lg bg-gray-800/80 border border-gray-700/50">
                                <input
                                  ref={editInputRef}
                                  className="flex-1 bg-gray-900/50 border border-gray-700 rounded-md px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-plutus-500/50 min-w-0"
                                  value={editTitle}
                                  onChange={(e) => setEditTitle(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") handleRename(conv.id);
                                    if (e.key === "Escape") setEditingId(null);
                                  }}
                                  onClick={(e) => e.stopPropagation()}
                                />
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRename(conv.id);
                                  }}
                                  className="p-1 rounded-md text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10 transition-colors"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setEditingId(null);
                                  }}
                                  className="p-1 rounded-md text-gray-500 hover:text-gray-300 hover:bg-gray-700/50 transition-colors"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            ) : isConfirmingDelete ? (
                              /* Delete confirmation */
                              <div className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-red-500/5 border border-red-500/20">
                                <span className="text-xs text-red-400 font-medium">
                                  Delete this chat?
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDelete(conv.id);
                                    }}
                                    className="px-2 py-1 text-[11px] font-medium bg-red-500/20 text-red-400 rounded-md hover:bg-red-500/30 transition-colors"
                                  >
                                    Delete
                                  </button>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setConfirmDeleteId(null);
                                    }}
                                    className="px-2 py-1 text-[11px] font-medium bg-gray-700/50 text-gray-400 rounded-md hover:bg-gray-700 transition-colors"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              /* Normal conversation card — compact single row */
                              <div
                                onClick={() => handleLoadConversation(conv)}
                                className={`group relative flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-md cursor-pointer transition-all duration-150 ${
                                  isActive
                                    ? "bg-plutus-600/10 conv-active"
                                    : "hover:bg-gray-800/60"
                                }`}
                              >
                                {/* Active indicator bar */}
                                {isActive && (
                                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-full bg-plutus-500 shadow-sm shadow-plutus-500/50" />
                                )}

                                {/* Title + meta inline */}
                                <div className="flex-1 min-w-0">
                                  <p
                                    className={`text-xs truncate font-medium leading-snug ${
                                      isActive
                                        ? "text-plutus-300"
                                        : "text-gray-400 group-hover:text-gray-200"
                                    }`}
                                  >
                                    {conv.title || getDefaultTitle(conv)}
                                  </p>
                                  <span
                                    className={`text-[10px] leading-none ${
                                      isActive ? "text-plutus-500/60" : "text-gray-600"
                                    }`}
                                  >
                                    {formatTimeAgo(conv.last_activity)}
                                    {conv.message_count > 0 && ` · ${conv.message_count} msgs`}
                                  </span>
                                </div>

                                {/* Context menu trigger */}
                                <div className="relative shrink-0" ref={isMenuOpen ? menuRef : undefined}>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setMenuOpenId(isMenuOpen ? null : conv.id);
                                    }}
                                    className={`p-0.5 rounded transition-all ${
                                      isMenuOpen
                                        ? "text-gray-300 bg-gray-700/50"
                                        : "text-gray-700 opacity-0 group-hover:opacity-100 hover:text-gray-300 hover:bg-gray-700/50"
                                    }`}
                                  >
                                    <MoreHorizontal className="w-3.5 h-3.5" />
                                  </button>

                                  {/* Dropdown menu */}
                                  {isMenuOpen && (
                                    <div className="absolute right-0 top-full mt-1 w-32 py-1 bg-gray-800 border border-gray-700/80 rounded-lg shadow-xl shadow-black/30 z-50 animate-fade-in">
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          startEditing(conv);
                                        }}
                                        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700/60 hover:text-gray-100 transition-colors"
                                      >
                                        <Pencil className="w-3 h-3" />
                                        Rename
                                      </button>
                                      <div className="h-px bg-gray-700/50 my-1" />
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setConfirmDeleteId(conv.id);
                                          setMenuOpenId(null);
                                        }}
                                        className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
                                      >
                                        <Trash2 className="w-3 h-3" />
                                        Delete
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </div>
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
    </div>
  );
}

function getDefaultTitle(conv: Conversation): string {
  return `Chat ${new Date(conv.created_at * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })}`;
}

function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 172800) return "yesterday";
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

interface ConversationGroup {
  label: string;
  items: Conversation[];
}

function groupConversations(conversations: Conversation[]): ConversationGroup[] {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayTs = todayStart.getTime() / 1000;
  const yesterdayTs = todayTs - 86400;
  const weekTs = todayTs - 7 * 86400;
  const monthTs = todayTs - 30 * 86400;

  const groups: ConversationGroup[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "This Week", items: [] },
    { label: "This Month", items: [] },
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
    } else if (ts >= monthTs) {
      groups[3].items.push(conv);
    } else {
      groups[4].items.push(conv);
    }
  }

  return groups;
}

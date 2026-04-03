import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import {
  Trash2,
  Pencil,
  Check,
  X,
  Search,
  MoreHorizontal,
  Loader2,
  MessageSquare,
  ChevronDown,
  Plug,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore, PENDING_NEW_SESSION_ID, DEFAULT_SESSION_ID } from "../../stores/appStore";
import { ConnectorLogo, CONNECTOR_LOGO_MAP } from "../connectors/ConnectorLogos";
import type { Conversation } from "../../lib/types";

interface Props {
  send: (data: Record<string, unknown>) => void;
}

// Connector display metadata
const CONNECTOR_META: Record<string, { label: string; color: string }> = {
  telegram: { label: "Telegram", color: "#38bdf8" },
  whatsapp: { label: "WhatsApp", color: "#34d399" },
  discord: { label: "Discord", color: "#818cf8" },
  email: { label: "Email", color: "#fbbf24" },
};

function getConnectorKey(session: { id: string; connector_name?: string | null }): string {
  if (session.connector_name) return session.connector_name.toLowerCase();
  const parts = session.id.split("_");
  return parts[parts.length - 1].toLowerCase();
}

export function ConversationHistory({ send }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [connectorsOpen, setConnectorsOpen] = useState(true);
  const editInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const {
    activeSessionId,
    sessionStates,
    sessions,
    setConversationId,
    clearMessages,
    setView,
    setActiveSessionId,
    connected,
    conversationRefreshTick,
  } = useAppStore();
  const conversationId = sessionStates[activeSessionId]?.conversationId ?? null;

  // Connector sessions from the sessions store
  const connectorSessions = useMemo(
    () => sessions.filter((s) => s.is_connector),
    [sessions]
  );

  // Build a set of conversation IDs that are currently being processed
  const processingConvIds = useMemo(() => {
    const ids = new Set<string>();
    for (const state of Object.values(sessionStates)) {
      if (state.isProcessing && state.conversationId) {
        ids.add(state.conversationId);
      }
    }
    return ids;
  }, [sessionStates]);

  const fetchConversations = useCallback(() => {
    if (!connected) return;
    api
      .getConversations(50)
      .then((data) => setConversations(data as unknown as Conversation[]))
      .catch(() => {});
  }, [connected]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations, conversationId, conversationRefreshTick]);

  const anyProcessing = useMemo(
    () => Object.values(sessionStates).some((s) => s.isProcessing),
    [sessionStates]
  );
  useEffect(() => {
    if (!anyProcessing) fetchConversations();
  }, [anyProcessing, fetchConversations]);

  useEffect(() => {
    if (!connected) return;
    const interval = setInterval(fetchConversations, 30000);
    return () => clearInterval(interval);
  }, [fetchConversations, connected]);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    if (menuOpenId) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpenId]);

  // Filter out connector conversations from the main list
  const nonConnectorConversations = useMemo(() => {
    return conversations.filter((c) => !c.metadata?.connector_name);
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return nonConnectorConversations;
    const q = searchQuery.toLowerCase();
    return nonConnectorConversations.filter((c) => {
      const title = c.title || getDefaultTitle(c);
      return title.toLowerCase().includes(q);
    });
  }, [nonConnectorConversations, searchQuery]);

  const grouped = useMemo(
    () => groupConversations(filteredConversations),
    [filteredConversations]
  );

  const handleLoadConversation = (conv: Conversation) => {
    if (conv.id === conversationId) return;
    // Always target a non-connector session.  If the user is currently
    // viewing a connector session (e.g. Telegram) and clicks a conversation
    // from history, we must NOT send resume_conversation to the connector's
    // session — that would hijack the connector agent's active conversation
    // and cause subsequent connector messages to land in the wrong thread.
    const currentIsConnector = sessions.find(
      (s) => s.id === activeSessionId && s.is_connector
    );
    const targetSession =
      activeSessionId === PENDING_NEW_SESSION_ID || currentIsConnector
        ? DEFAULT_SESSION_ID
        : activeSessionId;
    send({
      type: "resume_conversation",
      conversation_id: conv.id,
      session_id: targetSession,
    });
    if (activeSessionId === PENDING_NEW_SESSION_ID || currentIsConnector) {
      useAppStore.getState().setPendingNewSession(false);
      useAppStore.getState().setActiveSessionId(DEFAULT_SESSION_ID);
    }
    setView("chat");
  };

  const handleConnectorClick = (sessionId: string) => {
    setActiveSessionId(sessionId);
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

  const hasConnectors = connectorSessions.length > 0;
  const hasConversations = conversations.length > 0;

  if (!hasConnectors && !hasConversations) return null;

  return (
    <div className="flex flex-col min-h-0 flex-1">
      {/* Search bar */}
      <div className="px-3 pt-1 pb-3">
        <div
          className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-all duration-200 ${
            searchFocused
              ? "bg-gray-800 ring-1 ring-plutus-500/30"
              : "bg-gray-800/50 hover:bg-gray-800/80"
          }`}
        >
          <Search className="w-3.5 h-3.5 text-gray-500 shrink-0" />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            className="flex-1 bg-transparent text-xs text-gray-300 placeholder-gray-600 focus:outline-none min-w-0"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="p-0.5 rounded text-gray-500 hover:text-gray-300 transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Scrollable area for connector dropdown + conversation list */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-2 pb-2 sidebar-scroll">
        {/* ── Connector Chats dropdown ─────────────────────────────────── */}
        {hasConnectors && (
          <div className="mb-2">
            {/* Dropdown header */}
            <button
              onClick={() => setConnectorsOpen(!connectorsOpen)}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-gray-800/40 transition-colors group"
            >
              <Plug className="w-3 h-3 text-gray-600" />
              <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider flex-1 text-left">
                Connector Chats
              </span>
              <span className="text-[10px] text-gray-600 tabular-nums mr-1">
                {connectorSessions.length}
              </span>
              <ChevronDown
                className={`w-3 h-3 text-gray-600 transition-transform duration-200 ${
                  connectorsOpen ? "" : "-rotate-90"
                }`}
              />
            </button>

            {/* Connector list (collapsible) */}
            <div
              className={`overflow-hidden transition-all duration-200 ease-in-out ${
                connectorsOpen ? "max-h-96 opacity-100" : "max-h-0 opacity-0"
              }`}
            >
              <div className="space-y-0.5 pt-1">
                {connectorSessions.map((session) => {
                  const key = getConnectorKey(session);
                  const meta = CONNECTOR_META[key] ?? {
                    label: session.display_name || key,
                    color: "#9ca3af",
                  };
                  const isActive = session.id === activeSessionId;
                  const processing =
                    sessionStates[session.id]?.isProcessing ?? false;
                  const msgCount =
                    sessionStates[session.id]?.messages?.length ?? 0;

                  return (
                    <button
                      key={session.id}
                      onClick={() => handleConnectorClick(session.id)}
                      className={`w-full flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 rounded-md text-left transition-all duration-150 ${
                        isActive
                          ? "bg-plutus-600/10"
                          : "hover:bg-gray-800/60"
                      }`}
                    >
                      {/* Active indicator */}
                      {isActive && (
                        <div className="absolute left-0 w-[2px] h-4 rounded-r-full bg-plutus-500 shadow-sm shadow-plutus-500/50" />
                      )}

                      {/* Connector icon */}
                      <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
                        {CONNECTOR_LOGO_MAP[key] ? (
                          <ConnectorLogo name={key} size={16} />
                        ) : (
                          <Plug
                            className="w-3.5 h-3.5"
                            style={{ color: meta.color }}
                          />
                        )}
                      </div>

                      {/* Label + status */}
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-xs font-medium truncate leading-snug ${
                            isActive
                              ? "text-plutus-300"
                              : "text-gray-400"
                          }`}
                        >
                          {meta.label}
                        </p>
                        <span className="text-[10px] text-gray-600 leading-none">
                          {processing ? "Processing..." : msgCount > 0 ? `${msgCount} msgs` : "No messages"}
                        </span>
                      </div>

                      {/* Status indicators */}
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        {processing ? (
                          <Loader2
                            className="w-3 h-3 animate-spin"
                            style={{ color: meta.color }}
                          />
                        ) : (
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: "#34d399" }}
                            title="Connected"
                          />
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Divider between connectors and regular chats */}
            {hasConversations && (
              <div className="h-px bg-gray-800/60 mt-2" />
            )}
          </div>
        )}

        {/* ── Regular conversation list ───────────────────────────────── */}
        {filteredConversations.length === 0 ? (
          nonConnectorConversations.length === 0 ? null : (
            <div className="px-3 py-4 text-center">
              <Search className="w-4 h-4 text-gray-700 mx-auto mb-1.5" />
              <p className="text-[11px] text-gray-600">No matches found</p>
            </div>
          )
        ) : (
          <div className="space-y-3">
            {grouped.map(
              (group) =>
                group.items.length > 0 && (
                  <div key={group.label}>
                    {/* Group header */}
                    <div className="flex items-center gap-2 px-2 mb-1">
                      <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap">
                        {group.label}
                      </span>
                      <div className="flex-1 h-px bg-gray-800/60" />
                    </div>

                    {/* Conversation items */}
                    <div className="space-y-0.5">
                      {group.items.map((conv) => {
                        const isActive = conv.id === conversationId;
                        const isWorking = processingConvIds.has(conv.id);
                        const isEditing = editingId === conv.id;
                        const isConfirmingDelete = confirmDeleteId === conv.id;
                        const isMenuOpen = menuOpenId === conv.id;

                        return (
                          <div
                            key={conv.id}
                            className="conv-item animate-fade-in"
                          >
                            {isEditing ? (
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
                              <div
                                onClick={() => handleLoadConversation(conv)}
                                className={`group relative flex items-center gap-2 pl-2.5 pr-1.5 py-1.5 rounded-md cursor-pointer transition-all duration-150 ${
                                  isActive
                                    ? "bg-plutus-600/10 conv-active"
                                    : "hover:bg-gray-800/60"
                                }`}
                              >
                                {isActive && (
                                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-full bg-plutus-500 shadow-sm shadow-plutus-500/50" />
                                )}

                                <span className="flex-shrink-0 opacity-40">
                                  <MessageSquare className="w-3.5 h-3.5" />
                                </span>

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

                                {isWorking ? (
                                  <span
                                    className="flex-shrink-0"
                                    title="Plutus is working in this chat"
                                  >
                                    <Loader2
                                      className="w-3.5 h-3.5 animate-spin"
                                      style={{ color: "#818cf8" }}
                                    />
                                  </span>
                                ) : null}

                                <div
                                  className="relative shrink-0"
                                  ref={isMenuOpen ? menuRef : undefined}
                                >
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setMenuOpenId(isMenuOpen ? null : conv.id);
                                    }}
                                    className={`p-0.5 rounded transition-all ${
                                      isMenuOpen
                                        ? "text-gray-300 bg-gray-700/50"
                                        : isWorking
                                          ? "hidden"
                                          : "text-gray-700 opacity-0 group-hover:opacity-100 hover:text-gray-300 hover:bg-gray-700/50"
                                    }`}
                                  >
                                    <MoreHorizontal className="w-3.5 h-3.5" />
                                  </button>

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

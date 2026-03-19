import { create } from "zustand";
import type { Message, Tier, ApprovalRequest } from "../lib/types";
import type { ThemeMode } from "../hooks/useTheme";
import { getStoredTheme } from "../hooks/useTheme";

export type View =
  | "chat"
  | "dashboard"
  | "guardrails"
  | "settings"
  | "tools"
  | "workers"
  | "tool-creator"
  | "skills"
  | "memory"
  | "connectors"
  | "sessions"
  | "onboarding";

interface ChatMessage extends Message {
  isStreaming?: boolean;
  toolResults?: Map<string, string>;
}

// ── Session types ─────────────────────────────────────────────────────────────

export interface SessionInfo {
  id: string;
  display_name: string;
  icon: string;
  is_connector: boolean;
  connector_name?: string | null;
  conversation_id?: string | null;
  is_processing: boolean;
  created_at: string;
  last_active: string;
}

interface SessionState {
  messages: ChatMessage[];
  isProcessing: boolean;
  conversationId: string | null;
}

export const DEFAULT_SESSION_ID = "session_main";
// Sentinel used while the user has clicked "New Chat" but hasn't sent a
// message yet. The active session is switched to this ID immediately so
// the chat view shows the empty state. It is replaced by the real session
// ID once the backend confirms session_created.
export const PENDING_NEW_SESSION_ID = "__pending_new__";

function emptySessionState(): SessionState {
  return { messages: [], isProcessing: false, conversationId: null };
}

// ── Store interface ───────────────────────────────────────────────────────────

interface AppState {
  // Navigation
  view: View;
  setView: (v: View) => void;

  // ── Multi-session ──────────────────────────────────────────────────────────
  sessions: SessionInfo[];
  setSessions: (sessions: SessionInfo[]) => void;
  addSession: (session: SessionInfo) => void;
  removeSession: (sessionId: string) => void;
  updateSession: (sessionId: string, patch: Partial<SessionInfo>) => void;

  activeSessionId: string;
  setActiveSessionId: (id: string) => void;

  sessionStates: Record<string, SessionState>;
  getSessionState: (sessionId: string) => SessionState;

  // ── Chat (operates on the active session) ─────────────────────────────────
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage, sessionId?: string) => void;
  appendToLastAssistant: (content: string, sessionId?: string) => void;
  clearMessages: (sessionId?: string) => void;
  isProcessing: boolean;
  setProcessing: (v: boolean, sessionId?: string) => void;

  conversationId: string | null;
  setConversationId: (id: string | null, sessionId?: string) => void;

  // Guardrails
  currentTier: Tier;
  setCurrentTier: (t: Tier) => void;
  pendingApprovals: ApprovalRequest[];
  addApproval: (a: ApprovalRequest) => void;
  removeApproval: (id: string) => void;

  // API Key status
  keyConfigured: boolean;
  setKeyConfigured: (v: boolean) => void;

  // Connection
  connected: boolean;
  setConnected: (v: boolean) => void;

  // Onboarding
  onboardingCompleted: boolean | null;
  setOnboardingCompleted: (v: boolean) => void;

  // Lazy session creation — set when user clicks "New Chat" but before
  // any message is sent. ChatView reads this flag and creates the session
  // on the first send, then clears the flag.
  pendingNewSession: boolean;
  setPendingNewSession: (v: boolean) => void;

  // One-shot callback invoked by App.tsx when session_created arrives.
  // ChatView registers this so it can send the first message to the correct
  // new session ID regardless of whether the user switched chats in the
  // meantime (avoids the polling-activeSessionId race condition).
  pendingSessionCallback: ((newSessionId: string) => void) | null;
  setPendingSessionCallback: (cb: ((newSessionId: string) => void) | null) => void;

  // Conversation history panel
  historyPanelOpen: boolean;
  setHistoryPanelOpen: (v: boolean) => void;
  toggleHistoryPanel: () => void;

  // Theme
  theme: ThemeMode;
  setTheme: (t: ThemeMode) => void;

  // WhatsApp pairing code (shown when WhatsApp is connecting)
  whatsappPairingCode: string | null;
  setWhatsappPairingCode: (code: string | null) => void;

  // Updates
  updateInfo: {
    available: boolean;
    dismissed: boolean;
    currentVersion: string;
    latestVersion: string;
    releaseName: string;
    releaseNotes: string;
    releaseUrl: string;
    publishedAt: string;
  } | null;
  setUpdateInfo: (info: AppState["updateInfo"]) => void;
}

// ── Store implementation ──────────────────────────────────────────────────────

export const useAppStore = create<AppState>((set, get) => ({
  // Navigation
  view: "chat",
  setView: (view) => set({ view }),

  // ── Multi-session ──────────────────────────────────────────────────────────
  sessions: [
    {
      id: DEFAULT_SESSION_ID,
      display_name: "Main",
      icon: "🏠",
      is_connector: false,
      is_processing: false,
      created_at: new Date().toISOString(),
      last_active: new Date().toISOString(),
    },
  ],
  setSessions: (sessions) => set({ sessions }),
  addSession: (session) =>
    set((s) => ({
      sessions: s.sessions.some((x) => x.id === session.id)
        ? s.sessions
        : [...s.sessions, session],
    })),
  removeSession: (sessionId) =>
    set((s) => ({
      sessions: s.sessions.filter((x) => x.id !== sessionId),
    })),
  updateSession: (sessionId, patch) =>
    set((s) => ({
      sessions: s.sessions.map((x) =>
        x.id === sessionId ? { ...x, ...patch } : x
      ),
    })),

  activeSessionId: DEFAULT_SESSION_ID,
  setActiveSessionId: (id) => {
    const state = get();
    if (!state.sessionStates[id]) {
      set((s) => ({
        activeSessionId: id,
        sessionStates: {
          ...s.sessionStates,
          [id]: emptySessionState(),
        },
      }));
    } else {
      set({ activeSessionId: id });
    }
  },

  sessionStates: {
    [DEFAULT_SESSION_ID]: emptySessionState(),
  },
  getSessionState: (sessionId) => {
    return get().sessionStates[sessionId] ?? emptySessionState();
  },

  // ── Chat (derived from active session) ────────────────────────────────────
  get messages() {
    const { activeSessionId, sessionStates } = get();
    return (sessionStates[activeSessionId] ?? emptySessionState()).messages;
  },
  addMessage: (msg, sessionId) => {
    const sid = sessionId ?? get().activeSessionId;
    set((s) => {
      const prev = s.sessionStates[sid] ?? emptySessionState();
      return {
        sessionStates: {
          ...s.sessionStates,
          [sid]: { ...prev, messages: [...prev.messages, msg] },
        },
      };
    });
  },
  appendToLastAssistant: (content, sessionId) => {
    const sid = sessionId ?? get().activeSessionId;
    set((s) => {
      const prev = s.sessionStates[sid] ?? emptySessionState();
      const msgs = [...prev.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = {
          ...last,
          content: (last.content || "") + content,
        };
      }
      return {
        sessionStates: {
          ...s.sessionStates,
          [sid]: { ...prev, messages: msgs },
        },
      };
    });
  },
  clearMessages: (sessionId) => {
    const sid = sessionId ?? get().activeSessionId;
    set((s) => {
      const prev = s.sessionStates[sid] ?? emptySessionState();
      return {
        sessionStates: {
          ...s.sessionStates,
          [sid]: { ...prev, messages: [] },
        },
      };
    });
  },

  get isProcessing() {
    const { activeSessionId, sessionStates } = get();
    return (sessionStates[activeSessionId] ?? emptySessionState()).isProcessing;
  },
  setProcessing: (v, sessionId) => {
    const sid = sessionId ?? get().activeSessionId;
    set((s) => {
      const prev = s.sessionStates[sid] ?? emptySessionState();
      return {
        sessionStates: {
          ...s.sessionStates,
          [sid]: { ...prev, isProcessing: v },
        },
      };
    });
  },

  get conversationId() {
    const { activeSessionId, sessionStates } = get();
    return (sessionStates[activeSessionId] ?? emptySessionState()).conversationId;
  },
  setConversationId: (id, sessionId) => {
    const sid = sessionId ?? get().activeSessionId;
    set((s) => {
      const prev = s.sessionStates[sid] ?? emptySessionState();
      return {
        sessionStates: {
          ...s.sessionStates,
          [sid]: { ...prev, conversationId: id },
        },
      };
    });
  },

  // Guardrails
  currentTier: "assistant",
  setCurrentTier: (currentTier) => set({ currentTier }),
  pendingApprovals: [],
  addApproval: (a) =>
    set((s) => ({ pendingApprovals: [...s.pendingApprovals, a] })),
  removeApproval: (id) =>
    set((s) => ({
      pendingApprovals: s.pendingApprovals.filter((a) => a.id !== id),
    })),

  // API Key status
  keyConfigured: true,
  setKeyConfigured: (keyConfigured) => set({ keyConfigured }),

  // Connection
  connected: false,
  setConnected: (connected) => set({ connected }),

  // Onboarding
  onboardingCompleted: null,
  setOnboardingCompleted: (onboardingCompleted) => set({ onboardingCompleted }),

  // Lazy session creation
  pendingNewSession: false,
  setPendingNewSession: (pendingNewSession) => set({ pendingNewSession }),
  pendingSessionCallback: null,
  setPendingSessionCallback: (pendingSessionCallback) => set({ pendingSessionCallback }),

  // Conversation history panel
  historyPanelOpen: false,
  setHistoryPanelOpen: (historyPanelOpen) => set({ historyPanelOpen }),
  toggleHistoryPanel: () =>
    set((s) => ({ historyPanelOpen: !s.historyPanelOpen })),

  // Theme
  theme: getStoredTheme(),
  setTheme: (theme) => set({ theme }),

  // WhatsApp pairing code
  whatsappPairingCode: null,
  setWhatsappPairingCode: (whatsappPairingCode) => set({ whatsappPairingCode }),

  // Updates
  updateInfo: null,
  setUpdateInfo: (updateInfo) => set({ updateInfo }),
}));

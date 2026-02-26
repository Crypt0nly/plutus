import { create } from "zustand";
import type { Message, Tier, ApprovalRequest } from "../lib/types";

export type View = "chat" | "dashboard" | "guardrails" | "settings" | "tools" | "workers" | "tool-creator" | "skills" | "memory" | "connectors" | "onboarding";

interface ChatMessage extends Message {
  // Extended with UI-specific fields
  isStreaming?: boolean;
  toolResults?: Map<string, string>;
}

interface AppState {
  // Navigation
  view: View;
  setView: (v: View) => void;

  // Chat
  messages: ChatMessage[];
  addMessage: (msg: ChatMessage) => void;
  appendToLastAssistant: (content: string) => void;
  clearMessages: () => void;
  isProcessing: boolean;
  setProcessing: (v: boolean) => void;

  // Conversations
  conversationId: string | null;
  setConversationId: (id: string | null) => void;

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
  onboardingCompleted: boolean | null; // null = not yet loaded
  setOnboardingCompleted: (v: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Navigation
  view: "chat",
  setView: (view) => set({ view }),

  // Chat
  messages: [],
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  appendToLastAssistant: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content: (last.content || "") + content };
      }
      return { messages: msgs };
    }),
  clearMessages: () => set({ messages: [] }),
  isProcessing: false,
  setProcessing: (isProcessing) => set({ isProcessing }),

  // Conversations
  conversationId: null,
  setConversationId: (conversationId) => set({ conversationId }),

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
  keyConfigured: true, // assume true until proven otherwise
  setKeyConfigured: (keyConfigured) => set({ keyConfigured }),

  // Connection
  connected: false,
  setConnected: (connected) => set({ connected }),

  // Onboarding
  onboardingCompleted: null,
  setOnboardingCompleted: (onboardingCompleted) => set({ onboardingCompleted }),
}));

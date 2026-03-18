import { create } from 'zustand'

interface Message { role: 'user' | 'assistant' | 'system'; content: string; timestamp?: string }
interface AgentState { status: 'online' | 'offline' | 'busy'; bridgeConnected: boolean; currentTask: string | null }

interface AgentStore {
  messages: Message[]
  conversations: Array<{ id: string; title: string }>
  currentConversationId: string | null
  agentState: AgentState
  isLoading: boolean
  addMessage: (msg: Message) => void
  setMessages: (msgs: Message[]) => void
  setConversationId: (id: string | null) => void
  setAgentState: (state: Partial<AgentState>) => void
  setLoading: (loading: boolean) => void
  clearMessages: () => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  messages: [],
  conversations: [],
  currentConversationId: null,
  agentState: { status: 'offline', bridgeConnected: false, currentTask: null },
  isLoading: false,

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  setConversationId: (id) => set({ currentConversationId: id }),
  setAgentState: (state) => set((s) => ({ agentState: { ...s.agentState, ...state } })),
  setLoading: (loading) => set({ isLoading: loading }),
  clearMessages: () => set({ messages: [] }),
}))

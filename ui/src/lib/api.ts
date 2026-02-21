/** API client for the Plutus backend. */

const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Status
  getStatus: () => request<Record<string, unknown>>("/status"),

  // Guardrails
  getGuardrails: () => request<Record<string, unknown>>("/guardrails"),
  setTier: (tier: string) =>
    request<Record<string, string>>("/guardrails/tier", {
      method: "PUT",
      body: JSON.stringify({ tier }),
    }),
  setToolOverride: (toolName: string, enabled: boolean, requireApproval: boolean) =>
    request<Record<string, string>>("/guardrails/override", {
      method: "PUT",
      body: JSON.stringify({
        tool_name: toolName,
        enabled,
        require_approval: requireApproval,
      }),
    }),

  // Approvals
  getApprovals: () => request<Record<string, unknown>[]>("/approvals"),
  resolveApproval: (approvalId: string, approved: boolean) =>
    request<Record<string, unknown>>("/approvals/resolve", {
      method: "POST",
      body: JSON.stringify({ approval_id: approvalId, approved }),
    }),

  // Audit
  getAudit: (limit = 50, offset = 0) =>
    request<{ entries: Record<string, unknown>[]; total: number }>(
      `/audit?limit=${limit}&offset=${offset}`
    ),

  // Conversations
  getConversations: (limit = 20) =>
    request<Record<string, unknown>[]>(`/conversations?limit=${limit}`),
  deleteConversation: (id: string) =>
    request<Record<string, string>>(`/conversations/${id}`, { method: "DELETE" }),
  getMessages: (convId: string) =>
    request<Record<string, unknown>[]>(`/conversations/${convId}/messages`),

  // Tools
  getTools: () => request<Record<string, unknown>[]>("/tools"),

  // API Keys
  getKeyStatus: () =>
    request<{
      providers: Record<string, boolean>;
      current_provider: string;
      current_provider_configured: boolean;
    }>("/keys/status"),
  setKey: (provider: string, key: string) =>
    request<{ message: string; key_configured: boolean }>("/keys", {
      method: "POST",
      body: JSON.stringify({ provider, key }),
    }),
  deleteKey: (provider: string) =>
    request<Record<string, string>>(`/keys/${provider}`, { method: "DELETE" }),

  // Config
  getConfig: () => request<Record<string, unknown>>("/config"),
  updateConfig: (patch: Record<string, unknown>) =>
    request<Record<string, string>>("/config", {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),
};

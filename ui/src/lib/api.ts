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
  getConversations: (limit = 50) =>
    request<Record<string, unknown>[]>(`/conversations?limit=${limit}`),
  deleteConversation: (id: string) =>
    request<Record<string, string>>(`/conversations/${id}`, { method: "DELETE" }),
  renameConversation: (id: string, title: string) =>
    request<Record<string, string>>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  getMessages: (convId: string) =>
    request<Record<string, unknown>[]>(`/conversations/${convId}/messages`),
  cleanupConversations: () =>
    request<Record<string, any>>("/conversations/cleanup", { method: "POST" }),

  // Tools
  getTools: () => request<Record<string, unknown>[]>("/tools"),
  getToolsDetails: () => request<Record<string, any>>("/tools/details"),

  // Workers
  getWorkers: () => request<Record<string, any>>("/workers"),
  getWorkerStatus: (taskId: string) =>
    request<Record<string, any>>(`/workers/${taskId}`),
  cancelWorker: (taskId: string) =>
    request<Record<string, any>>(`/workers/${taskId}/cancel`, { method: "POST" }),
  updateWorkerConfig: (patch: Record<string, any>) =>
    request<Record<string, any>>("/workers/config", {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Scheduler
  getScheduler: () => request<Record<string, any>>("/scheduler"),
  getScheduledJobs: () => request<Record<string, any>>("/scheduler/jobs"),
  getScheduledJob: (jobId: string) =>
    request<Record<string, any>>(`/scheduler/jobs/${jobId}`),
  pauseJob: (jobId: string) =>
    request<Record<string, any>>(`/scheduler/jobs/${jobId}/pause`, { method: "POST" }),
  resumeJob: (jobId: string) =>
    request<Record<string, any>>(`/scheduler/jobs/${jobId}/resume`, { method: "POST" }),
  deleteJob: (jobId: string) =>
    request<Record<string, any>>(`/scheduler/jobs/${jobId}`, { method: "DELETE" }),
  getSchedulerHistory: (limit = 50, jobId?: string) =>
    request<Record<string, any>>(
      `/scheduler/history?limit=${limit}${jobId ? `&job_id=${jobId}` : ""}`
    ),

  // Model Routing
  getModelRouting: () => request<Record<string, any>>("/models"),
  updateModelRouting: (patch: Record<string, any>) =>
    request<Record<string, any>>("/models/config", {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Custom Tools
  getCustomTools: () => request<Record<string, any>>("/custom-tools"),
  createCustomTool: (toolName: string, description: string, code: string, register = true) =>
    request<Record<string, any>>("/custom-tools", {
      method: "POST",
      body: JSON.stringify({ tool_name: toolName, description, code, register }),
    }),
  deleteCustomTool: (name: string) =>
    request<Record<string, string>>(`/custom-tools/${name}`, { method: "DELETE" }),

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

  // Setup / Onboarding
  completeSetup: () =>
    request<{ message: string }>("/setup/complete", { method: "POST" }),

  // Config
  getConfig: () => request<Record<string, unknown>>("/config"),
  updateConfig: (patch: Record<string, unknown>) =>
    request<Record<string, string>>("/config", {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Heartbeat
  getHeartbeatStatus: () => request<Record<string, any>>("/heartbeat"),
  updateHeartbeat: (body: Record<string, any>) =>
    request<Record<string, any>>("/heartbeat", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  startHeartbeat: () =>
    request<Record<string, any>>("/heartbeat/start", { method: "POST" }),
  stopHeartbeat: () =>
    request<Record<string, any>>("/heartbeat/stop", { method: "POST" }),

  // Plans
  getPlans: (conversationId?: string, limit = 20) =>
    request<Record<string, any>[]>(
      `/plans?limit=${limit}${conversationId ? `&conversation_id=${conversationId}` : ""}`
    ),
  getActivePlan: (conversationId?: string) =>
    request<Record<string, any> | null>(
      `/plans/active${conversationId ? `?conversation_id=${conversationId}` : ""}`
    ),
  getPlan: (planId: string) =>
    request<Record<string, any>>(`/plans/${planId}`),
  deletePlan: (planId: string) =>
    request<Record<string, string>>(`/plans/${planId}`, { method: "DELETE" }),

  // PC Control
  getPCStatus: () => request<Record<string, any>>("/pc/status"),
  getPCContext: () => request<Record<string, any>>("/pc/context"),
  getPCWorkflows: () => request<Record<string, any>>("/pc/workflows"),
  getPCShortcuts: () => request<Record<string, any>>("/pc/shortcuts"),
  // Skills
  getSkills: (category?: string) =>
    request<Record<string, any>>(category ? `/skills?category=${category}` : "/skills"),
  getSkillDetail: (skillName: string) =>
    request<Record<string, any>>(`/skills/${skillName}`),
  exportSkill: (skillName: string) =>
    request<Record<string, any>>(`/skills/${skillName}/export`),
  importSkill: (skillData: Record<string, any>) =>
    request<Record<string, any>>("/skills/import", {
      method: "POST",
      body: JSON.stringify({ skill_data: skillData }),
    }),
  deleteSkill: (skillName: string) =>
    request<Record<string, any>>(`/skills/${skillName}`, { method: "DELETE" }),
  getSavedSkills: () =>
    request<Record<string, any>>("/skills/saved"),

  // Memory
  getMemoryStats: () => request<Record<string, any>>("/memory/stats"),
  getFacts: (category?: string, limit = 50) =>
    request<Record<string, any>>(
      `/memory/facts?limit=${limit}${category ? `&category=${category}` : ""}`
    ),
  deleteFact: (factId: number) =>
    request<Record<string, string>>(`/memory/facts/${factId}`, { method: "DELETE" }),
  getGoals: (conversationId?: string, limit = 50) =>
    request<Record<string, any>>(
      `/memory/goals?limit=${limit}${conversationId ? `&conversation_id=${conversationId}` : ""}`
    ),
  getActiveGoals: (conversationId?: string) =>
    request<Record<string, any>>(
      `/memory/goals/active${conversationId ? `?conversation_id=${conversationId}` : ""}`
    ),
  getConversationSummary: (convId: string) =>
    request<Record<string, any>>(`/conversations/${convId}/summary`),
  getCheckpoints: (convId: string, limit = 10) =>
    request<Record<string, any>>(`/conversations/${convId}/checkpoints?limit=${limit}`),

  // Self-Improvement
  getImprovementLog: (limit = 50) =>
    request<Record<string, any>>(`/improvement/log?limit=${limit}`),
  getImprovementStats: () =>
    request<Record<string, any>>("/improvement/stats"),

  // Connectors
  getConnectors: () =>
    request<Record<string, any>>("/connectors"),
  getConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}`),
  updateConnectorConfig: (name: string, config: Record<string, any>) =>
    request<Record<string, any>>(`/connectors/${name}/config`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  testConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}/test`, {
      method: "POST",
    }),
  sendConnectorMessage: (name: string, text: string, params: Record<string, any> = {}) =>
    request<Record<string, any>>(`/connectors/${name}/send`, {
      method: "POST",
      body: JSON.stringify({ text, params }),
    }),
  startConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}/start`, {
      method: "POST",
    }),
  stopConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}/stop`, {
      method: "POST",
    }),
  disconnectConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}`, {
      method: "DELETE",
    }),
  getBridgeStatus: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}/bridge-status`),
  setConnectorAutoStart: (name: string, auto_start: boolean) =>
    request<Record<string, any>>(`/connectors/${name}/auto-start`, {
      method: "PUT",
      body: JSON.stringify({ auto_start }),
    }),
};

/** API client for the Plutus backend. */

const BASE = "/api";

// Token getter — set by the Clerk-aware wrapper in main.tsx
let _getToken: (() => Promise<string | null>) | null = null;

export function setTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_getToken) {
    const token = await _getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...headers, ...(options?.headers as Record<string, string> || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

/** Like request<T> but returns `fallback` instead of throwing on 404. */
async function safeRequest<T>(path: string, fallback: T, options?: RequestInit): Promise<T> {
  try {
    return await request<T>(path, options);
  } catch (e) {
    if (e instanceof Error && e.message.includes("404")) return fallback;
    throw e;
  }
}

export const api = {
  // Status
  getStatus: () => request<Record<string, unknown>>("/health/status"),

  // Guardrails
  getGuardrails: () => safeRequest<Record<string, unknown>>("/guardrails", { tier: "standard", tool_overrides: {} }),
  setTier: (tier: string) =>
    safeRequest<Record<string, string>>("/guardrails/tier", { message: "ok" }, {
      method: "PUT",
      body: JSON.stringify({ tier }),
    }),
  setToolOverride: (toolName: string, enabled: boolean, requireApproval: boolean) =>
    safeRequest<Record<string, string>>("/guardrails/override", { message: "ok" }, {
      method: "PUT",
      body: JSON.stringify({
        tool_name: toolName,
        enabled,
        require_approval: requireApproval,
      }),
    }),

  // Approvals
  getApprovals: () => safeRequest<Record<string, unknown>[]>("/approvals", []),
  resolveApproval: (approvalId: string, approved: boolean) =>
    safeRequest<Record<string, unknown>>("/approvals/resolve", {}, {
      method: "POST",
      body: JSON.stringify({ approval_id: approvalId, approved }),
    }),

  // Audit
  getAudit: (limit = 50, offset = 0) =>
    safeRequest<{ entries: Record<string, unknown>[]; total: number }>(
      `/audit?limit=${limit}&offset=${offset}`, { entries: [], total: 0 }
    ),

  // Conversations — mapped to cloud backend /chat endpoints
  getConversations: (limit = 50) =>
    safeRequest<Record<string, unknown>[]>(`/chat/history?limit=${limit}`, []),
  deleteConversation: (id: string) =>
    safeRequest<Record<string, string>>(`/chat/${id}`, {}, { method: "DELETE" }),
  renameConversation: (id: string, title: string) =>
    safeRequest<Record<string, string>>(`/chat/${id}`, {}, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  getMessages: (convId: string) =>
    safeRequest<Record<string, unknown>[]>(`/chat/${convId}`, []),
  cleanupConversations: () =>
    safeRequest<Record<string, any>>("/chat/cleanup", { message: "ok" }, { method: "POST" }),

  // Tools — mapped to cloud backend /agents/skills
  getTools: () => safeRequest<Record<string, unknown>[]>("/agents/skills", []),
  getToolsDetails: () => safeRequest<Record<string, any>>("/agents/skills", {}),

  // Workers — not available in cloud
  getWorkers: () => safeRequest<Record<string, any>>("/workers", { tasks: [] }),
  getWorkerStatus: (taskId: string) =>
    safeRequest<Record<string, any>>(`/workers/${taskId}`, {}),
  cancelWorker: (taskId: string) =>
    safeRequest<Record<string, any>>(`/workers/${taskId}/cancel`, {}, { method: "POST" }),
  updateWorkerConfig: (patch: Record<string, any>) =>
    safeRequest<Record<string, any>>("/workers/config", {}, {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Scheduler — mapped to cloud backend /agents/scheduled-tasks
  getScheduler: () => safeRequest<Record<string, any>>("/agents/scheduled-tasks", { running: false }),
  getScheduledJobs: () => safeRequest<Record<string, any>>("/agents/scheduled-tasks", { jobs: [] }),
  getScheduledJob: (jobId: string) =>
    safeRequest<Record<string, any>>(`/agents/scheduled-tasks/${jobId}`, {}),
  pauseJob: (jobId: string) =>
    safeRequest<Record<string, any>>(`/scheduler/jobs/${jobId}/pause`, {}, { method: "POST" }),
  resumeJob: (jobId: string) =>
    safeRequest<Record<string, any>>(`/scheduler/jobs/${jobId}/resume`, {}, { method: "POST" }),
  deleteJob: (jobId: string) =>
    safeRequest<Record<string, any>>(`/scheduler/jobs/${jobId}`, {}, { method: "DELETE" }),
  getSchedulerHistory: (limit = 50, jobId?: string) =>
    safeRequest<Record<string, any>>(
      `/scheduler/history?limit=${limit}${jobId ? `&job_id=${jobId}` : ""}`, { history: [] }
    ),

  // Model Routing — not available in cloud
  getModelRouting: () => safeRequest<Record<string, any>>("/models", { provider: "anthropic" }),
  updateModelRouting: (patch: Record<string, any>) =>
    safeRequest<Record<string, any>>("/models/config", {}, {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Custom Tools — not available in cloud
  getCustomTools: () => safeRequest<Record<string, any>>("/custom-tools", { tools: [] }),
  createCustomTool: (toolName: string, description: string, code: string, register = true) =>
    safeRequest<Record<string, any>>("/custom-tools", {}, {
      method: "POST",
      body: JSON.stringify({ tool_name: toolName, description, code, register }),
    }),
  deleteCustomTool: (name: string) =>
    safeRequest<Record<string, string>>(`/custom-tools/${name}`, {}, { method: "DELETE" }),

  // API Keys — in cloud mode, keys are managed server-side
  getKeyStatus: () =>
    safeRequest<{
      providers: Record<string, boolean>;
      current_provider: string;
      current_provider_configured: boolean;
    }>("/keys/status", {
      providers: { anthropic: true, openai: true },
      current_provider: "anthropic",
      current_provider_configured: true,
    }),
  setKey: (provider: string, key: string) =>
    safeRequest<{ message: string; key_configured: boolean }>("/keys", { message: "ok", key_configured: true }, {
      method: "POST",
      body: JSON.stringify({ provider, key }),
    }),
  deleteKey: (provider: string) =>
    safeRequest<Record<string, string>>(`/keys/${provider}`, {}, { method: "DELETE" }),

  // Setup / Onboarding — always complete in cloud
  completeSetup: () =>
    safeRequest<{ message: string }>("/setup/complete", { message: "ok" }, { method: "POST" }),

  // Config
  getConfig: () => safeRequest<Record<string, unknown>>("/config", {}),
  updateConfig: (patch: Record<string, unknown>) =>
    safeRequest<Record<string, string>>("/config", {}, {
      method: "PATCH",
      body: JSON.stringify({ patch }),
    }),

  // Heartbeat — not available in cloud
  getHeartbeatStatus: () => safeRequest<Record<string, any>>("/heartbeat", { enabled: false }),
  updateHeartbeat: (body: Record<string, any>) =>
    safeRequest<Record<string, any>>("/heartbeat", {}, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  startHeartbeat: () =>
    safeRequest<Record<string, any>>("/heartbeat/start", {}, { method: "POST" }),
  stopHeartbeat: () =>
    safeRequest<Record<string, any>>("/heartbeat/stop", {}, { method: "POST" }),

  // Keep Alive — not available in cloud
  getKeepAliveStatus: () => safeRequest<Record<string, any>>("/keep-alive", { enabled: false }),
  setKeepAlive: (enabled: boolean) =>
    safeRequest<Record<string, any>>("/keep-alive", {}, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),

  // Plans — not available in cloud
  getPlans: (conversationId?: string, limit = 20) =>
    safeRequest<Record<string, any>[]>(
      `/plans?limit=${limit}${conversationId ? `&conversation_id=${conversationId}` : ""}`, []
    ),
  getActivePlan: (conversationId?: string) =>
    safeRequest<Record<string, any> | null>(
      `/plans/active${conversationId ? `?conversation_id=${conversationId}` : ""}`, null
    ),
  getPlan: (planId: string) =>
    safeRequest<Record<string, any>>(`/plans/${planId}`, {}),
  deletePlan: (planId: string) =>
    safeRequest<Record<string, string>>(`/plans/${planId}`, {}, { method: "DELETE" }),

  // PC Control — not available in cloud
  getPCStatus: () => safeRequest<Record<string, any>>("/pc/status", { available: false }),
  getPCContext: () => safeRequest<Record<string, any>>("/pc/context", {}),
  getPCWorkflows: () => safeRequest<Record<string, any>>("/pc/workflows", { workflows: [] }),
  getPCShortcuts: () => safeRequest<Record<string, any>>("/pc/shortcuts", { shortcuts: [] }),

  // Skills — mapped to cloud backend /agents/skills
  getSkills: (category?: string) =>
    safeRequest<Record<string, any>>(category ? `/agents/skills?category=${category}` : "/agents/skills", { skills: [] }),
  getSkillDetail: (skillName: string) =>
    safeRequest<Record<string, any>>(`/agents/skills/${skillName}`, {}),
  exportSkill: (skillName: string) =>
    safeRequest<Record<string, any>>(`/agents/skills/${skillName}/export`, {}),
  importSkill: (skillData: Record<string, any>) =>
    safeRequest<Record<string, any>>("/agents/skills/import", {}, {
      method: "POST",
      body: JSON.stringify({ skill_data: skillData }),
    }),
  deleteSkill: (skillName: string) =>
    safeRequest<Record<string, any>>(`/agents/skills/${skillName}`, {}, { method: "DELETE" }),
  getSavedSkills: () =>
    safeRequest<Record<string, any>>("/agents/skills/saved", { skills: [] }),

  // Memory — mapped to cloud backend /agents/memory
  getMemoryStats: () => safeRequest<Record<string, any>>("/agents/memory", { total_facts: 0 }),
  getFacts: (category?: string, limit = 50) =>
    safeRequest<Record<string, any>>(
      `/agents/memory?limit=${limit}${category ? `&category=${category}` : ""}`, { facts: [] }
    ),
  deleteFact: (factId: number) =>
    safeRequest<Record<string, string>>(`/agents/memory/${factId}`, {}, { method: "DELETE" }),
  getGoals: (conversationId?: string, limit = 50) =>
    safeRequest<Record<string, any>>(
      `/memory/goals?limit=${limit}${conversationId ? `&conversation_id=${conversationId}` : ""}`, { goals: [] }
    ),
  getActiveGoals: (conversationId?: string) =>
    safeRequest<Record<string, any>>(
      `/memory/goals/active${conversationId ? `?conversation_id=${conversationId}` : ""}`, { goals: [] }
    ),
  getConversationSummary: (convId: string) =>
    safeRequest<Record<string, any>>(`/conversations/${convId}/summary`, {}),
  getCheckpoints: (convId: string, limit = 10) =>
    safeRequest<Record<string, any>>(`/conversations/${convId}/checkpoints?limit=${limit}`, { checkpoints: [] }),

  // Self-Improvement — not available in cloud
  getImprovementLog: (limit = 50) =>
    safeRequest<Record<string, any>>(`/improvement/log?limit=${limit}`, { log: [] }),
  getImprovementStats: () =>
    safeRequest<Record<string, any>>("/improvement/stats", {}),

  // Connectors — mapped to cloud backend bridge
  getConnectors: () =>
    safeRequest<Record<string, any>>("/connectors", { connectors: [] }),
  getConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}`, {}),
  updateConnectorConfig: (name: string, config: Record<string, any>) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/config`, {}, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  testConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/test`, {}, {
      method: "POST",
    }),
  sendConnectorMessage: (name: string, text: string, params: Record<string, any> = {}) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/send`, {}, {
      method: "POST",
      body: JSON.stringify({ text, params }),
    }),
  startConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/start`, {}, {
      method: "POST",
    }),
  stopConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/stop`, {}, {
      method: "POST",
    }),
  disconnectConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}`, {}, {
      method: "DELETE",
    }),
  getBridgeStatus: (name: string) =>
    safeRequest<Record<string, any>>(`/bridge/status`, { connected: false }),
  setConnectorAutoStart: (name: string, auto_start: boolean) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/auto-start`, {}, {
      method: "PUT",
      body: JSON.stringify({ auto_start }),
    }),
  authorizeConnector: (name: string) =>
    safeRequest<Record<string, any>>(`/connectors/${name}/authorize`, {}, {
      method: "POST",
    }),
  createCustomConnector: (data: {
    connector_id: string;
    display_name?: string;
    description?: string;
    base_url: string;
    auth_type?: string;
    credentials?: Record<string, string>;
    default_headers?: Record<string, string>;
  }) =>
    safeRequest<Record<string, any>>("/connectors/custom", {}, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // WSL — not available in cloud
  getWSLStatus: () =>
    safeRequest<{
      platform: string;
      is_windows: boolean;
      wsl_installed: boolean;
      enabled: boolean;
      setup_completed: boolean;
      preferred_distro: string;
    }>("/wsl/status", {
      platform: "linux",
      is_windows: false,
      wsl_installed: false,
      enabled: false,
      setup_completed: false,
      preferred_distro: "",
    }),
  enableWSL: (enabled: boolean) =>
    safeRequest<{ message: string }>("/wsl/enable", { message: "ok" }, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  completeWSLSetup: () =>
    safeRequest<{ message: string }>("/wsl/setup-complete", { message: "ok" }, { method: "POST" }),
  getWSLSetupGuide: () =>
    safeRequest<{
      needed: boolean;
      steps: { id: string; title: string; description: string; command: string | null; note: string }[];
      prerequisites?: { id: string; label: string; detail: string }[];
      troubleshooting?: { id: string; problem: string; solution: string }[];
    }>("/wsl/setup-guide", { needed: false, steps: [], prerequisites: [], troubleshooting: [] }),

  // Updates — not available in cloud
  checkForUpdate: () =>
    safeRequest<{
      update_available: boolean;
      current_version: string;
      latest_version: string;
      error?: string;
      dismissed?: boolean;
      release_name?: string;
      release_notes?: string;
      release_url?: string;
      published_at?: string;
    }>("/updates/check", {
      update_available: false,
      current_version: "cloud",
      latest_version: "cloud",
    }),
  dismissUpdate: (version: string) =>
    safeRequest<{ message: string }>("/updates/dismiss", { message: "ok" }, {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  applyUpdate: () =>
    safeRequest<{
      success: boolean;
      previous_version: string;
      new_version?: string;
      restart_required?: boolean;
      error?: string;
    }>("/updates/apply", {
      success: false,
      previous_version: "cloud",
    }, { method: "POST" }),

  // Browser selection — not available in cloud
  detectBrowsers: () =>
    safeRequest<{ browsers: { kind: string; name: string; path: string; version: string; is_default: boolean }[] }>(
      "/browser/detect", { browsers: [] }
    ),
  launchBrowserForCDP: (opts: {
    executable_path: string;
    cdp_port?: number;
    use_profile?: boolean;
  }) =>
    safeRequest<{ message: string; port: number }>("/browser/launch", { message: "ok", port: 0 }, {
      method: "POST",
      body: JSON.stringify({ patch: opts }),
    }),
};

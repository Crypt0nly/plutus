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

  // Keep Alive
  getKeepAliveStatus: () => request<Record<string, any>>("/keep-alive"),
  setKeepAlive: (enabled: boolean) =>
    request<Record<string, any>>("/keep-alive", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),

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
  authorizeConnector: (name: string) =>
    request<Record<string, any>>(`/connectors/${name}/authorize`, {
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
    request<Record<string, any>>("/connectors/custom", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // WSL
  getWSLStatus: () =>
    request<{
      platform: string;
      is_windows: boolean;
      wsl_installed: boolean;
      enabled: boolean;
      setup_completed: boolean;
      preferred_distro: string;
    }>("/wsl/status"),
  enableWSL: (enabled: boolean) =>
    request<{ message: string }>("/wsl/enable", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  completeWSLSetup: () =>
    request<{ message: string }>("/wsl/setup-complete", { method: "POST" }),
  getWSLSetupGuide: () =>
    request<{
      needed: boolean;
      wsl_detected?: boolean;
      message?: string;
      prerequisites?: {
        id: string;
        label: string;
        detail: string;
      }[];
      steps: {
        id: string;
        title: string;
        description: string;
        substeps?: string[];
        command: string | null;
        command_verify?: string;
        note: string;
        warning?: string | null;
      }[];
      troubleshooting?: {
        id: string;
        problem: string;
        solution: string;
      }[];
    }>("/wsl/setup-guide"),

  // Updates
  checkForUpdate: () =>
    request<{
      update_available: boolean;
      dismissed?: boolean;
      current_version: string;
      latest_version: string;
      release_name?: string;
      release_notes?: string;
      release_url?: string;
      published_at?: string;
      error?: string;
    }>("/updates/check"),
  dismissUpdate: (version: string) =>
    request<{ message: string }>("/updates/dismiss", {
      method: "POST",
      body: JSON.stringify({ version }),
    }),
  applyUpdate: () =>
    request<{
      success: boolean;
      error?: string;
      previous_version: string;
      new_version?: string;
      steps?: { step: string; success: boolean; output: string }[];
      restart_required?: boolean;
    }>("/updates/apply", { method: "POST" }),

  // Browser selection
  detectBrowsers: () =>
    request<{
      browsers: {
        kind: string;
        name: string;
        path: string;
        version: string;
        is_default: boolean;
      }[];
    }>("/browser/detect"),
  launchBrowserForCDP: (opts: {
    executable_path: string;
    cdp_port?: number;
    use_profile?: boolean;
  }) =>
    request<{ message: string; port: number }>("/browser/launch", {
      method: "POST",
      body: JSON.stringify({ patch: opts }),
    }),

  // Workspace sync
  getWorkspaceInfo: () =>
    request<{ path: string; default_path: string; custom_path: string; total_size_bytes: number; file_count: number }>(
      "/workspace"
    ),
  setWorkspaceDir: (workspace_dir: string) =>
    request<{ path: string; custom_path: string }>("/workspace", {
      method: "PATCH",
      body: JSON.stringify({ workspace_dir }),
    }),
  getWorkspaceManifest: () =>
    request<{ files: { path: string; size: number; mtime: number }[]; total: number }>(
      "/workspace/manifest"
    ),
  workspacePush: (token: string) => {
    const cloudUrl = extractCloudUrlFromToken(token);
    if (!cloudUrl) {
      const raw = extractRawUrlFromToken(token);
      if (raw && (raw.includes("localhost") || raw.includes("127.0.0.1"))) {
        return Promise.reject(new Error(
          "Token embeds localhost — please regenerate the token in cloud Settings → Workspace after setting SERVER_BASE_URL on the cloud server"
        ));
      }
      return Promise.reject(new Error("Invalid or legacy token — please regenerate a new token from cloud Settings → Workspace"));
    }
    return fetch(`${cloudUrl}/api/workspace/manifest`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(async (remote) => {
        const localManifest = await request<{
          files: { path: string; size: number; mtime: number }[];
        }>("/workspace/manifest");
        const remoteMap: Record<string, { mtime: number }> = {};
        for (const f of remote.files || []) remoteMap[f.path] = f;
        const toUpload = (localManifest.files || []).filter(
          (f) => !remoteMap[f.path] || f.mtime > remoteMap[f.path].mtime + 1
        );
        let uploaded = 0;
        for (const f of toUpload) {
          const fileData = await request<{ content: string; binary?: boolean }>(`/workspace/files/${f.path}`);
          // Both text and binary files are uploaded via the same JSON endpoint.
          // Binary files carry base64-encoded content with binary:true so the
          // cloud can decode and write raw bytes.
          await fetch(`${cloudUrl}/api/workspace/files`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              path: f.path,
              content: fileData.content,
              binary: fileData.binary ?? false,
            }),
          });
          uploaded++;
        }
        // After uploading files to the cloud server workspace, trigger
        // a cloud workspace → sandbox pull so the agent can see the files
        // immediately without requiring a separate manual pull.
        if (uploaded > 0) {
          try {
            await fetch(`${cloudUrl}/api/workspace/pull`, {
              method: "POST",
              headers: { Authorization: `Bearer ${token}` },
            });
          } catch {
            // Non-fatal — files are on the server, sandbox will pick them up
            // on the next periodic sync or when a new sandbox is started.
          }
        }
        return { uploaded, total: toUpload.length };
      });
  },
  workspacePull: (token: string) => {
    const cloudUrl = extractCloudUrlFromToken(token);
    if (!cloudUrl) {
      const raw = extractRawUrlFromToken(token);
      if (raw && (raw.includes("localhost") || raw.includes("127.0.0.1"))) {
        return Promise.reject(new Error(
          "Token embeds localhost — please regenerate the token in cloud Settings → Workspace after setting SERVER_BASE_URL on the cloud server"
        ));
      }
      return Promise.reject(new Error("Invalid or legacy token — please regenerate a new token from cloud Settings → Workspace"));
    }
    return fetch(`${cloudUrl}/api/workspace/manifest`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(async (remote) => {
        const localManifest = await request<{
          files: { path: string; size: number; mtime: number }[];
        }>("/workspace/manifest");
        // Build a map of local files keyed by path for fast duplicate detection.
        // Files that already exist locally with an equal or newer mtime are skipped.
        const localMap: Record<string, { mtime: number }> = {};
        for (const f of localManifest.files || []) localMap[f.path] = f;
        const toDownload = (remote.files || []).filter(
          (f: { path: string; mtime: number }) =>
            !localMap[f.path] || f.mtime > localMap[f.path].mtime + 1
        );
        let downloaded = 0;
        let skipped = 0;
        const failed: string[] = [];
        for (const f of toDownload) {
          try {
            const resp = await fetch(`${cloudUrl}/api/workspace/files/${f.path}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (!resp.ok) {
              // File listed in manifest but not found on server — skip silently.
              skipped++;
              continue;
            }
            const data = await resp.json();
            await request("/workspace/files", {
              method: "POST",
              body: JSON.stringify({
                path: f.path,
                content: data.content,
                binary: data.binary ?? false,
              }),
            });
            downloaded++;
          } catch {
            failed.push(f.path);
          }
        }
        return { downloaded, skipped, failed: failed.length, total: toDownload.length };
      });
  },
  getWorkspaceSyncStatus: (token: string) => {
    const cloudUrl = extractCloudUrlFromToken(token);
    if (!cloudUrl) {
      const raw = extractRawUrlFromToken(token);
      if (raw && (raw.includes("localhost") || raw.includes("127.0.0.1"))) {
        return Promise.reject(new Error(
          "Token embeds localhost — please regenerate the token in cloud Settings → Workspace"
        ));
      }
      return Promise.reject(new Error("Invalid or legacy token — please regenerate a new token from cloud Settings → Workspace"));
    }
    return Promise.all([
      request<{ files: { path: string; mtime: number }[] }>("/workspace/manifest"),
      fetch(`${cloudUrl}/api/workspace/manifest`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => r.json()),
    ]).then(([local, remote]) => {
      const localMap: Record<string, number> = {};
      for (const f of local.files || []) localMap[f.path] = f.mtime;
      const remoteMap: Record<string, number> = {};
      for (const f of remote.files || []) remoteMap[f.path] = f.mtime;
      const allPaths = new Set([...Object.keys(localMap), ...Object.keys(remoteMap)]);
      let local_only = 0, cloud_only = 0, newer_local = 0, newer_cloud = 0, in_sync = 0;
      for (const p of allPaths) {
        const lm = localMap[p];
        const rm = remoteMap[p];
        if (!rm) local_only++;
        else if (!lm) cloud_only++;
        else if (lm > rm + 1) newer_local++;
        else if (rm > lm + 1) newer_cloud++;
        else in_sync++;
      }
      return { local_only, cloud_only, newer_local, newer_cloud, in_sync };
    });
  },
};

/**
 * Extract the cloud server URL embedded in a Plutus sync token.
 *
 * New token format:  plutus_<base64url(server_url)>.<hex_secret>
 * Legacy format:     plutus_<hex>  (no embedded URL — returns null)
 *
 * Returns null if the token is legacy, malformed, or embeds a localhost URL
 * (which means the token was generated before SERVER_BASE_URL was configured).
 */
export function extractCloudUrlFromToken(token: string): string | null {
  if (!token.startsWith("plutus_")) return null;
  const rest = token.slice(7); // strip "plutus_"
  const dotIdx = rest.indexOf(".");
  if (dotIdx === -1) return null; // legacy token — no embedded URL
  const b64 = rest.slice(0, dotIdx);
  try {
    // Re-add stripped padding
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    const url = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    // Reject tokens that embed a loopback address — they were generated before
    // SERVER_BASE_URL was properly configured on the cloud server.
    if (
      url.includes("localhost") ||
      url.includes("127.0.0.1") ||
      url.includes("0.0.0.0")
    ) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

/**
 * Like extractCloudUrlFromToken but also returns the raw decoded URL even
 * when it is a loopback address — used only for diagnostic display.
 */
export function extractRawUrlFromToken(token: string): string | null {
  if (!token.startsWith("plutus_")) return null;
  const rest = token.slice(7);
  const dotIdx = rest.indexOf(".");
  if (dotIdx === -1) return null;
  const b64 = rest.slice(0, dotIdx);
  try {
    const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    return atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  } catch {
    return null;
  }
}

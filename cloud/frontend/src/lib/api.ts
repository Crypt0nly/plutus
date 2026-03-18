const BASE_URL = import.meta.env.VITE_API_URL || '';

type GetToken = () => Promise<string | null>;

export async function getAuthHeaders(getToken: GetToken): Promise<HeadersInit> {
  const token = await getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function apiFetch<T>(getToken: GetToken, path: string, init?: RequestInit): Promise<T> {
  const headers = await getAuthHeaders(getToken);
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers: { ...headers, ...init?.headers } });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function sendMessage(
  getToken: GetToken,
  message: string,
  conversationId?: string,
) {
  return apiFetch(getToken, '/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message, ...(conversationId ? { conversation_id: conversationId } : {}) }),
  });
}

export function getChatHistory(getToken: GetToken) {
  return apiFetch(getToken, '/api/chat/history');
}

export function getAgentStatus(getToken: GetToken) {
  return apiFetch(getToken, '/api/agents/status');
}

export function getBridgeStatus(getToken: GetToken) {
  return apiFetch(getToken, '/api/bridge/status');
}

export function getSyncStatus(getToken: GetToken) {
  return apiFetch(getToken, '/api/sync/status');
}

export function pushSync(getToken: GetToken, changes: unknown) {
  return apiFetch(getToken, '/api/sync/push', {
    method: 'POST',
    body: JSON.stringify({ changes }),
  });
}

export function pullSync(getToken: GetToken, sinceVersion: number) {
  return apiFetch(getToken, `/api/sync/pull?since_version=${sinceVersion}`);
}

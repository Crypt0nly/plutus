/** Core types for the Plutus UI. */

export type Tier = "observer" | "assistant" | "operator" | "autonomous";

export interface TierInfo {
  id: Tier;
  label: string;
  description: string;
  level: number;
  tools: Record<string, ToolPolicy>;
}

export interface ToolPolicy {
  permission: "denied" | "requires_approval" | "allowed";
  allowed_operations: string[] | null;
  denied_patterns: string[] | null;
}

export interface ToolInfo {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface Message {
  id?: number;
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  tool_calls?: ToolCallData[] | null;
  tool_call_id?: string | null;
  created_at?: number;
}

export interface ToolCallData {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ApprovalRequest {
  id: string;
  tool_name: string;
  operation: string | null;
  params: Record<string, unknown>;
  reason: string;
  created_at: number;
}

export interface AuditEntry {
  id: string;
  timestamp: number;
  tool_name: string;
  operation: string | null;
  params: Record<string, unknown>;
  decision: string;
  tier: string;
  reason: string;
  result_summary: string | null;
}

export interface Conversation {
  id: string;
  created_at: number;
  title: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentStatus {
  version: string;
  status: string;
  guardrails: {
    tier: Tier;
    tier_label: string;
    tier_description: string;
    pending_approvals: number;
    audit_summary: {
      total_entries: number;
      by_decision: Record<string, number>;
      by_tool: Record<string, number>;
    };
  } | null;
  tools: string[];
}

export interface PlanStep {
  index: number;
  description: string;
  details: string;
  status: "pending" | "in_progress" | "done" | "failed" | "skipped";
  result: string | null;
  started_at: number | null;
  finished_at: number | null;
}

export interface Plan {
  id: string;
  conversation_id: string | null;
  title: string;
  goal: string | null;
  status: "draft" | "active" | "completed" | "failed" | "cancelled";
  steps: PlanStep[];
  created_at: number;
  updated_at: number;
}

/** WebSocket message types */
export type WSMessage =
  | { type: "thinking"; message: string }
  | { type: "text"; content: string }
  | { type: "tool_call"; id: string; tool: string; arguments: Record<string, unknown> }
  | { type: "tool_approval_needed"; tool: string; arguments: Record<string, unknown>; reason: string }
  | { type: "tool_result"; id: string; tool: string; result: string; denied?: boolean; rejected?: boolean }
  | { type: "error"; message: string }
  | { type: "done" }
  | { type: "conversation_started"; conversation_id: string }
  | { type: "conversation_resumed"; conversation_id: string; messages: Message[] }
  | { type: "approval_resolved"; approval_id: string; approved: boolean; success: boolean }
  | { type: "heartbeat"; beat: number; max: number }
  | { type: "heartbeat_paused"; reason: string; count: number }
  | { type: "heartbeat_status"; [key: string]: any }
  | { type: "plan_update"; result: string }
  | { type: "pong" };

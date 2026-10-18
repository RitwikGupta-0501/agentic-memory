export interface ChatMessage {
  id: string;
  role: "user" | "agent" | "error";
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface SessionSummary {
  id: string;
  created_at?: number;
  updated_at?: number;
  episode_count?: number;
  user_id?: string;
  tenant_id?: string;
}

export type MemoryTier = "all" | "working" | "episodic" | "semantic" | "procedural";

export type IsolationMode = "tenant_shared" | "user_strict" | "team_open";

export interface GraphNodeData {
  id: string;
  label: string;
  name?: string;
  type?: string;
  role?: string;
  content?: string;
  session_id?: string;
  tier: "working" | "episodic" | "semantic" | "procedural" | "concept" | "unknown";
  labels?: string[];
  properties: Record<string, any>;
  scope?: string;
  user_id?: string;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  predicate: string;
  valid_from?: number;
  valid_to?: number | null;
  is_invalidated: boolean;
  properties?: Record<string, any>;
}

export interface CytoscapeElement {
  data: GraphNodeData | GraphEdgeData;
}

export interface GraphDataResponse {
  nodes: Array<{ data: GraphNodeData }>;
  edges: Array<{ data: GraphEdgeData }>;
  error?: string;
}

export interface HealthStatus {
  status: string;
  falkordb_connected: boolean;
  falkordb_host?: string;
  falkordb_port?: number;
  default_tenant?: string;
  llm_provider?: string;
}

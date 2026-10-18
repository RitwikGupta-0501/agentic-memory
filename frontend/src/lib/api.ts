import { GraphDataResponse, HealthStatus, SessionSummary, ChatMessage, IsolationMode } from "./types";

const API_BASE = "";

export async function fetchSessions(
  tenantId: string = "tenant-default",
  userId?: string,
  isolationMode: IsolationMode = "tenant_shared"
): Promise<SessionSummary[]> {
  try {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      isolation_mode: isolationMode,
    });
    if (userId) params.append("user_id", userId);
    const res = await fetch(`${API_BASE}/api/v1/memory/sessions?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) return data;
    }
  } catch (e) {
    console.warn("fetchSessions endpoint not available or failed:", e);
  }
  return [];
}

export async function fetchSessionEpisodes(
  sessionId: string,
  tenantId: string = "tenant-default",
  userId?: string,
  isolationMode: IsolationMode = "tenant_shared"
): Promise<ChatMessage[]> {
  try {
    const params = new URLSearchParams({
      session_id: sessionId,
      tenant_id: tenantId,
      isolation_mode: isolationMode,
    });
    if (userId) params.append("user_id", userId);
    const res = await fetch(`${API_BASE}/api/v1/memory/episodes?${params.toString()}`);
    if (res.ok) {
      const episodes = await res.json();
      if (Array.isArray(episodes)) {
        return episodes.map((ep: any) => ({
          id: ep.id || `ep_${Math.random()}`,
          role: ep.role === "agent" ? "agent" : ep.role === "user" ? "user" : "agent",
          content: ep.content || "",
          timestamp: ep.timestamp ? Math.round(ep.timestamp * 1000) : Date.now(),
        }));
      }
    }
  } catch (e) {
    console.error("Failed to fetch session episodes:", e);
  }
  return [];
}

export async function fetchHealth(): Promise<HealthStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.error("Failed to fetch health status:", e);
    return null;
  }
}

export async function fetchGraphData(
  tenantId: string = "tenant-default",
  userId?: string,
  includeInvalidated: boolean = true,
  isolationMode: IsolationMode = "tenant_shared"
): Promise<GraphDataResponse> {
  try {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      include_invalidated: String(includeInvalidated),
      isolation_mode: isolationMode,
    });
    if (userId) params.append("user_id", userId);

    const res = await fetch(`${API_BASE}/api/v1/memory/graph?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`Graph API returned ${res.status}`);
    }
    const data = await res.json();
    return data;
  } catch (e) {
    console.error("Failed to fetch graph data:", e);
    return { nodes: [], edges: [], error: String(e) };
  }
}

export async function fetchTimeTravelGraph(
  tenantId: string = "tenant-default",
  asOf?: number,
  includeInvalidated: boolean = true,
  userId?: string
): Promise<any> {
  try {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      include_invalidated: String(includeInvalidated),
    });
    if (asOf !== undefined) params.append("as_of", String(asOf));
    if (userId) params.append("user_id", userId);

    const res = await fetch(`${API_BASE}/api/v1/memory/semantic/cytoscape?${params.toString()}`);
    if (!res.ok) throw new Error(`Cytoscape snapshot error ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error("Failed to fetch time travel graph:", e);
    return null;
  }
}

export async function linkSessions(
  childSessionId: string,
  parentSessionId: string,
  tenantId: string = "tenant-default",
  userId?: string
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/memory/sessions/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        child_session_id: childSessionId,
        parent_session_id: parentSessionId,
        tenant_id: tenantId,
        user_id: userId,
      }),
    });
    return res.ok;
  } catch (e) {
    console.error("Failed to link sessions:", e);
    return false;
  }
}

export async function resetGuardrails(tenantId: string = "tenant-default"): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/memory/procedural/guardrail/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function streamChatMessage({
  prompt,
  tenantId,
  sessionId,
  parentSessionId,
  userId,
  isolationMode = "tenant_shared",
  onThought,
  onAnswer,
  onError,
  onDone,
}: {
  prompt: string;
  tenantId: string;
  sessionId: string;
  parentSessionId?: string;
  userId?: string;
  isolationMode?: IsolationMode;
  onThought?: (message: string) => void;
  onAnswer: (answer: string) => void;
  onError: (err: string) => void;
  onDone: () => void;
}): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/agents/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        tenant_id: tenantId,
        session_id: sessionId,
        parent_session_id: parentSessionId,
        user_id: userId,
        isolation_mode: isolationMode,
      }),
    });

    if (!res.ok) {
      throw new Error(`Agent service returned HTTP ${res.status}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No readable response body stream");

    const decoder = new TextDecoder();
    let buffer = "";
    let receivedAnswer = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const payload = JSON.parse(trimmed.slice(6));
            // Match any event containing an answer payload (agent_answer, task_completed, final_answer)
            if (payload.answer) {
              receivedAnswer = true;
              onAnswer(payload.answer);
            } else if (payload.type === "error") {
              onError(payload.message || "An error occurred during task execution.");
            } else if (onThought && payload.message) {
              onThought(payload.message);
            }
          } catch {
            // Non-JSON or SSE ping line
          }
        }
      }
    }

    // Fallback: If SSE stream ended without an answer (e.g. proxy buffering), query /api/v1/agents/run
    if (!receivedAnswer) {
      try {
        const runRes = await fetch(`${API_BASE}/api/v1/agents/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompt,
            tenant_id: tenantId,
            session_id: sessionId,
            parent_session_id: parentSessionId,
            user_id: userId,
            isolation_mode: isolationMode,
          }),
        });
        if (runRes.ok) {
          const runData = await runRes.json();
          if (runData.answer) {
            onAnswer(runData.answer);
          } else if (runData.status === "ERROR") {
            onError(runData.message || "Agent execution error");
          }
        }
      } catch (fallbackErr) {
        console.warn("Fallback query to /api/v1/agents/run failed:", fallbackErr);
      }
    }

    onDone();
  } catch (err: any) {
    onError(err.message || String(err));
    onDone();
  }
}

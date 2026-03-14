/**
 * SURVEYOR — API client utility.
 *
 * Thin wrapper around fetch for communicating with the FastAPI backend.
 */

const BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ── Types ────────────────────────────────────────────────────

export interface Study {
  id: string;
  title: string;
  description: string | null;
  status: "draft" | "active" | "paused" | "completed";
  created_at: string;
  updated_at: string;
}

export interface StudyListItem {
  id: string;
  title: string;
  status: "draft" | "active" | "paused" | "completed";
  created_at: string;
}

export interface Agent {
  id: string;
  study_id: string;
  name: string;
  status: "draft" | "active" | "paused";
  system_prompt: string;
  welcome_message: string | null;
  pipeline_type: "modular" | "voice_to_voice";
  llm_model: string;
  stt_provider: string;
  stt_model: string | null;
  tts_provider: string;
  tts_model: string | null;
  tts_voice: string | null;
  language: string;
  max_duration_seconds: number | null;
  participant_id_mode: "random" | "predefined" | "input";
  widget_key: string;
  widget_title: string | null;
  widget_description: string | null;
  widget_primary_color: string | null;
  widget_listening_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentListItem {
  id: string;
  study_id: string;
  name: string;
  status: "draft" | "active" | "paused";
  pipeline_type: "modular" | "voice_to_voice";
  llm_model: string;
  language: string;
  widget_key: string;
  participant_id_mode: "random" | "predefined" | "input";
  created_at: string;
}

export interface WidgetConfig {
  widget_key: string;
  widget_title: string | null;
  widget_description: string | null;
  widget_primary_color: string;
  widget_listening_message: string | null;
  participant_id_mode: "random" | "predefined" | "input";
  welcome_message: string | null;
  language: string;
}

export interface ParticipantIdentifier {
  id: string;
  agent_id: string;
  identifier: string;
  label: string | null;
  used: boolean;
  session_id: string | null;
  created_at: string;
  updated_at: string;
}

// ── Session Types ─────────────────────────────────────────────

export interface SessionItem {
  id: string;
  agent_id: string;
  status: "active" | "completed" | "timed_out" | "error";
  duration_seconds: number | null;
  total_tokens: number | null;
  participant_id: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptEntry {
  id: string;
  session_id: string;
  role: "user" | "agent" | "system";
  content: string;
  sequence: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  spoken_at: string;
  created_at: string;
}

export interface SessionDetail extends SessionItem {
  entries: TranscriptEntry[];
}

// ── Analytics Types ──────────────────────────────────────────

export interface AgentStats {
  agent_id: string;
  agent_name: string;
  total_sessions: number;
  completed_sessions: number;
  error_sessions: number;
  timed_out_sessions: number;
  active_sessions: number;
  avg_duration_seconds: number | null;
  total_utterances: number;
  completion_rate: number;
}

export interface StudyAnalytics {
  study_id: string;
  total_sessions: number;
  completed_sessions: number;
  error_sessions: number;
  timed_out_sessions: number;
  active_sessions: number;
  avg_duration_seconds: number | null;
  total_utterances: number;
  completion_rate: number;
  agents: AgentStats[];
}

export interface SessionStats {
  total_sessions: number;
  completed_sessions: number;
  error_sessions: number;
  timed_out_sessions: number;
  active_sessions: number;
  avg_duration_seconds: number | null;
  total_utterances: number;
  completion_rate: number;
}

// ── Studies ──────────────────────────────────────────────────

export const studies = {
  list: () => request<StudyListItem[]>("/studies"),

  get: (id: string) => request<Study>(`/studies/${id}`),

  create: (data: { title: string; description?: string }) =>
    request<Study>("/studies", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<Pick<Study, "title" | "description" | "status">>) =>
    request<Study>(`/studies/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/studies/${id}`, { method: "DELETE" }),

  analytics: (id: string) =>
    request<StudyAnalytics>(`/studies/${id}/analytics`),
};

// ── Agents ───────────────────────────────────────────────────

export type AgentCreatePayload = Omit<
  Agent,
  "id" | "study_id" | "widget_key" | "created_at" | "updated_at"
>;

export type AgentUpdatePayload = Partial<AgentCreatePayload>;

export const agents = {
  list: (studyId: string) =>
    request<AgentListItem[]>(`/studies/${studyId}/agents`),

  get: (studyId: string, agentId: string) =>
    request<Agent>(`/studies/${studyId}/agents/${agentId}`),

  create: (studyId: string, data: Partial<AgentCreatePayload> & { name: string }) =>
    request<Agent>(`/studies/${studyId}/agents`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (studyId: string, agentId: string, data: AgentUpdatePayload) =>
    request<Agent>(`/studies/${studyId}/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (studyId: string, agentId: string) =>
    request<void>(`/studies/${studyId}/agents/${agentId}`, {
      method: "DELETE",
    }),
};

// ── Widget Config (public) ───────────────────────────────────

export const widget = {
  config: (widgetKey: string) =>
    request<WidgetConfig>(`/widget/${widgetKey}`),
};

// ── Participant Identifiers ──────────────────────────────────

export const participants = {
  list: (studyId: string, agentId: string) =>
    request<ParticipantIdentifier[]>(
      `/studies/${studyId}/agents/${agentId}/participants`
    ),

  create: (studyId: string, agentId: string, data: { identifier: string; label?: string }) =>
    request<ParticipantIdentifier>(
      `/studies/${studyId}/agents/${agentId}/participants`,
      { method: "POST", body: JSON.stringify(data) }
    ),

  bulkCreate: (studyId: string, agentId: string, identifiers: string[]) =>
    request<ParticipantIdentifier[]>(
      `/studies/${studyId}/agents/${agentId}/participants/bulk`,
      { method: "POST", body: JSON.stringify({ identifiers }) }
    ),

  delete: (studyId: string, agentId: string, participantId: string) =>
    request<void>(
      `/studies/${studyId}/agents/${agentId}/participants/${participantId}`,
      { method: "DELETE" }
    ),
};

// ── Sessions ────────────────────────────────────────────────────

export interface SessionListParams {
  status?: string;
  date_from?: string;
  date_to?: string;
  sort_by?: string;
  sort_order?: string;
  session_ids?: string;
}

export const sessions = {
  list: (studyId: string, agentId: string, params?: SessionListParams) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.date_from) searchParams.set("date_from", params.date_from);
    if (params?.date_to) searchParams.set("date_to", params.date_to);
    if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
    if (params?.sort_order) searchParams.set("sort_order", params.sort_order);
    const qs = searchParams.toString();
    return request<SessionItem[]>(
      `/studies/${studyId}/agents/${agentId}/sessions${qs ? `?${qs}` : ""}`
    );
  },

  get: (studyId: string, agentId: string, sessionId: string) =>
    request<SessionDetail>(
      `/studies/${studyId}/agents/${agentId}/sessions/${sessionId}`
    ),

  stats: (studyId: string, agentId: string) =>
    request<SessionStats>(
      `/studies/${studyId}/agents/${agentId}/sessions/stats/summary`
    ),

  terminate: (studyId: string, agentId: string, sessionId: string) =>
    request<void>(
      `/studies/${studyId}/agents/${agentId}/sessions/${sessionId}/terminate`,
      { method: "POST" }
    ),

  exportCsvUrl: (studyId: string, agentId: string, params?: SessionListParams) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.date_from) searchParams.set("date_from", params.date_from);
    if (params?.date_to) searchParams.set("date_to", params.date_to);
    if (params?.session_ids) searchParams.set("session_ids", params.session_ids);
    const qs = searchParams.toString();
    return `${BASE}/studies/${studyId}/agents/${agentId}/sessions/export/csv${qs ? `?${qs}` : ""}`;
  },

  exportJsonUrl: (studyId: string, agentId: string, params?: SessionListParams) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.date_from) searchParams.set("date_from", params.date_from);
    if (params?.date_to) searchParams.set("date_to", params.date_to);
    if (params?.session_ids) searchParams.set("session_ids", params.session_ids);
    const qs = searchParams.toString();
    return `${BASE}/studies/${studyId}/agents/${agentId}/sessions/export/json${qs ? `?${qs}` : ""}`;
  },
};

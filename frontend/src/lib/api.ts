/**
 * OASIS — API client utility.
 *
 * Thin wrapper around fetch for communicating with the FastAPI backend.
 */

import { formatApiError } from "./apiErrors";

export { formatApiError, localDateEndIso, localDateStartIso, isValidWidgetHexColor, parseWidgetHexColor } from "./apiErrors";

const BASE = "/api";

// ── Auth token management ─────────────────────────────────────
const TOKEN_KEY = "oasis_auth_token";

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options?.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 204) return undefined as T;

  if (res.status === 401) {
    // Token expired or invalid — clear it and redirect to login
    clearAuthToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Authentication required");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(formatApiError(body.detail, `API error: ${res.status}`));
  }

  return res.json();
}

// ── Auth API ──────────────────────────────────────────────────

export interface AuthStatusResponse {
  auth_enabled: boolean;
  authenticated: boolean;
  username: string | null;
}

export interface LoginResponse {
  token: string;
  username: string;
  expires_in: number;
}

export const auth = {
  login: (username: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  status: () => request<AuthStatusResponse>("/auth/status"),
};

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
  modality: "voice" | "text";
  avatar: string | null;
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
  turn_detection: "local" | "remote";
  language: string;
  max_duration_seconds: number | null;
  participant_id_mode: "random" | "predefined" | "input";
  widget_key: string;
  widget_title: string | null;
  widget_description: string | null;
  widget_primary_color: string | null;
  widget_listening_message: string | null;
  widget_show_progress: boolean;
  interview_mode: "free_form" | "structured";
  interview_guide: {
    questions: {
      text: string;
      probes: string[];
      max_follow_ups: number;
      transition: string;
    }[];
    closing_message: string;
  } | null;
  silence_timeout_seconds: number | null;
  silence_prompt: string | null;
  twilio_phone_number: string | null;
  store_audio: boolean;
  track_engagement: boolean;
  engagement_config: EngagementConfig | null;
  adaptive_enabled: boolean;
  adaptive_policy: AdaptivePolicy | null;
  created_at: string;
  updated_at: string;
}

export interface EngagementWeights {
  length: number;
  latency: number;
  rate: number;
  fillers: number;
  energy: number;
}

export interface EngagementConfig {
  window_size: number;
  low_threshold: number;
  high_threshold: number;
  long_latency_ms: number;
  short_answer_words: number;
  weights: EngagementWeights;
}

export const DEFAULT_ENGAGEMENT_CONFIG: EngagementConfig = {
  window_size: 3,
  low_threshold: 0.34,
  high_threshold: 0.67,
  long_latency_ms: 4000,
  short_answer_words: 3,
  weights: { length: 0.35, latency: 0.25, rate: 0.15, fillers: 0.15, energy: 0.1 },
};

// Text interviews: latency is reading + typing time, so thresholds are much
// wider, and only length / latency / lexical hedging contribute to the score.
export const DEFAULT_ENGAGEMENT_CONFIG_TEXT: EngagementConfig = {
  window_size: 3,
  low_threshold: 0.34,
  high_threshold: 0.67,
  long_latency_ms: 45000,
  short_answer_words: 3,
  weights: { length: 0.5, latency: 0.2, rate: 0, fillers: 0.3, energy: 0 },
};

// ── Adaptive behavior ─────────────────────────────────────────

export type AdaptiveTrigger =
  | "sustained_disengagement"
  | "positive_engagement_streak"
  | "recovery_after_dip"
  | "long_latency"
  | "very_short_answer"
  | "high_filler";

export type AdaptiveActionId =
  | "offer_break"
  | "soften_next_probe"
  | "encourage_elaboration"
  | "acknowledge_effort"
  | "privacy_check"
  | "match_style"
  | "slow_down"
  | "reset_pace";

export interface AdaptiveRule {
  on: AdaptiveTrigger;
  action: AdaptiveActionId;
  custom_instruction: string | null;
  cooldown_seconds: number;
  params: Record<string, number>;
}

export interface AdaptivePolicy {
  mode: "shadow" | "live";
  rules: AdaptiveRule[];
}

export const ADAPTIVE_TRIGGER_LABELS: Record<AdaptiveTrigger, string> = {
  sustained_disengagement: "Sustained disengagement",
  positive_engagement_streak: "Positive engagement streak",
  recovery_after_dip: "Recovery after a dip",
  long_latency: "Long response delay (turn)",
  very_short_answer: "Very short answer (turn)",
  high_filler: "High filler / hedging (turn)",
};

// Labels and default instruction texts mirror the backend's ACTION_CATALOG
// (backend/app/engagement/adaptive.py). The instruction shown in the form is
// exactly what gets injected — researchers can edit it per rule.
export const ADAPTIVE_ACTION_META: Record<
  AdaptiveActionId,
  { label: string; type: "prompt" | "tts_speed"; defaultInstruction?: string }
> = {
  offer_break: {
    label: "Offer a break",
    type: "prompt",
    defaultInstruction:
      "The participant has shown signs of fatigue or disengagement over the " +
      "last few turns. Gently offer a short break or to move to a lighter " +
      "topic. Keep it brief and warm. Do not mention that this was detected " +
      "automatically.",
  },
  soften_next_probe: {
    label: "Soften the next question",
    type: "prompt",
    defaultInstruction:
      "Make your next question gentler and less probing. Lead with warmth and " +
      "give the participant room to answer at their own pace.",
  },
  encourage_elaboration: {
    label: "Encourage elaboration",
    type: "prompt",
    defaultInstruction:
      "The participant's recent answers have been brief. Warmly invite them to " +
      "say more with a single open follow-up question.",
  },
  acknowledge_effort: {
    label: "Acknowledge engagement",
    type: "prompt",
    defaultInstruction:
      "Briefly acknowledge the participant's effort and engagement before " +
      "continuing with the interview.",
  },
  privacy_check: {
    label: "Check in on comfort",
    type: "prompt",
    defaultInstruction:
      "Check in about the participant's comfort and privacy in one short, warm " +
      "sentence before continuing.",
  },
  match_style: {
    label: "Mirror the participant's style",
    type: "prompt",
    defaultInstruction:
      "From now on, subtly mirror the participant's communication style: " +
      "match their level of formality, their sentence length, and their " +
      "energy. If they are brief and casual, be brief and casual; if they " +
      "are detailed and reflective, give them room and depth. Keep the " +
      "mirroring subtle — never imitate their exact words back at them, and " +
      "never mention that you are adapting.",
  },
  slow_down: { label: "Slow speaking pace", type: "tts_speed" },
  reset_pace: { label: "Reset speaking pace", type: "tts_speed" },
};

// Starter rules seeded into the form when adaptive behavior is first enabled.
// They are ordinary, fully editable rules — adjust or remove them like any
// other (the instruction text is pre-filled from the catalog defaults).
export function defaultAdaptiveRules(): AdaptiveRule[] {
  const rule = (
    on: AdaptiveTrigger,
    action: AdaptiveActionId,
    cooldown_seconds: number
  ): AdaptiveRule => ({
    on,
    action,
    custom_instruction: ADAPTIVE_ACTION_META[action].defaultInstruction ?? null,
    cooldown_seconds,
    params: {},
  });
  return [
    rule("sustained_disengagement", "offer_break", 180),
    rule("very_short_answer", "encourage_elaboration", 90),
    rule("high_filler", "soften_next_probe", 120),
  ];
}

export const DEFAULT_ADAPTIVE_POLICY: AdaptivePolicy = {
  mode: "shadow",
  rules: [],
};

export interface AgentListItem {
  id: string;
  study_id: string;
  name: string;
  modality: "voice" | "text";
  avatar: string | null;
  status: "draft" | "active" | "paused";
  pipeline_type: "modular" | "voice_to_voice";
  llm_model: string;
  stt_provider: string;
  stt_model: string | null;
  tts_provider: string;
  tts_model: string | null;
  tts_voice: string | null;
  language: string;
  widget_key: string;
  participant_id_mode: "random" | "predefined" | "input";
  interview_mode: "free_form" | "structured";
  created_at: string;
}

export interface WidgetConfig {
  widget_key: string;
  modality: "voice" | "text";
  avatar: string;
  widget_title: string | null;
  widget_description: string | null;
  widget_primary_color: string;
  widget_listening_message: string | null;
  widget_show_progress: boolean;
  participant_id_mode: "random" | "predefined" | "input";
  interview_mode: "free_form" | "structured";
  question_count: number;
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
  audio_recording_enabled: boolean;
  audio_storage_uri: string | null;
  audio_recording_status: string;
  adaptive_active?: boolean;
  created_at: string;
  updated_at: string;
}

export interface AudioTurn {
  sequence: number;
  role: string;
  filename: string;
  duration_ms?: number | null;
  content_preview?: string | null;
}

export interface SessionAudioManifest {
  session_id: string;
  storage_uri: string | null;
  recording_status: string;
  turns: AudioTurn[];
}

export interface EngagementTurn {
  transcript_sequence: number;
  response_latency_ms: number | null;
  voiced_ms: number | null;
  word_count: number | null;
  char_count: number | null;
  speech_rate_wpm: number | null;
  filler_count: number | null;
  rms_energy: number | null;
  score: number | null;
  label: string | null;
  flags: string[];
}

export interface EngagementEvent {
  transcript_sequence: number | null;
  event_type: string;
  score_at_event: number | null;
}

export interface AdaptiveActionRecord {
  transcript_sequence: number | null;
  trigger: string;
  action: string;
  mode: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface EngagementSummary {
  session_id: string;
  turn_count: number;
  average_score: number | null;
  label: string | null;
  average_latency_ms: number | null;
  average_words: number | null;
  low_engagement_turns: number;
  turns: EngagementTurn[];
  events: EngagementEvent[];
  adaptive_active: boolean;
  adaptive_actions: AdaptiveActionRecord[];
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

  /** Instantiate an Agent in this study from a built-in template. */
  createFromTemplate: (
    studyId: string,
    templateId: string,
    body?: { name?: string },
  ) =>
    request<Agent>(`/studies/${studyId}/agents/from-template/${templateId}`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
};

// ── Templates (public listing, auth-required to instantiate) ────

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  tags: string[];
  modality: "voice" | "text";
  pipeline_type: "modular" | "voice_to_voice";
  llm_model: string;
  interview_mode: "free_form" | "structured";
}

export const templates = {
  list: () => request<AgentTemplate[]>("/templates"),
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

  create: (
    studyId: string,
    agentId: string,
    data: { identifier: string; label?: string | null },
  ) =>
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

  /** Re-mark a predefined participant identifier as available. */
  release: (studyId: string, agentId: string, participantId: string) =>
    request<ParticipantIdentifier>(
      `/studies/${studyId}/agents/${agentId}/participants/${participantId}/release`,
      { method: "POST" }
    ),
};

// ── Knowledge Base ──────────────────────────────────────────────

export interface KnowledgeDocument {
  id: string;
  study_id: string;
  title: string;
  source_type: string;
  content_length: number;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeSearchResult {
  content: string;
  title: string;
  similarity: number;
}

export const knowledge = {
  list: (studyId: string) =>
    request<KnowledgeDocument[]>(`/studies/${studyId}/knowledge`),

  uploadText: (studyId: string, data: { title: string; content: string }) =>
    request<KnowledgeDocument>(`/studies/${studyId}/knowledge/text`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  uploadFile: (studyId: string, file: File, title?: string) => {
    const formData = new FormData();
    formData.append("file", file);
    if (title) formData.append("title", title);
    const headers: Record<string, string> = {};
    const token = getAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return fetch(`${BASE}/studies/${studyId}/knowledge/file`, {
      method: "POST",
      body: formData,
      headers,
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(formatApiError(body.detail, `API error: ${res.status}`));
      }
      return res.json() as Promise<KnowledgeDocument>;
    });
  },

  delete: (studyId: string, documentId: string) =>
    request<void>(`/studies/${studyId}/knowledge/${documentId}`, {
      method: "DELETE",
    }),

  search: (studyId: string, query: string, topK?: number) =>
    request<KnowledgeSearchResult[]>(`/studies/${studyId}/knowledge/search`, {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK || 5 }),
    }),
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

  getAudioManifest: (studyId: string, agentId: string, sessionId: string) =>
    request<SessionAudioManifest>(
      `/studies/${studyId}/agents/${agentId}/sessions/${sessionId}/audio`
    ),

  getEngagement: (studyId: string, agentId: string, sessionId: string) =>
    request<EngagementSummary>(
      `/studies/${studyId}/agents/${agentId}/sessions/${sessionId}/engagement`
    ),

  audioTurnUrl: (
    studyId: string,
    agentId: string,
    sessionId: string,
    filename: string
  ) =>
    `${BASE}/studies/${studyId}/agents/${agentId}/sessions/${sessionId}/audio/${filename}`,

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

  /**
   * Trigger an authenticated CSV download. Uses a Bearer-authed fetch so the
   * browser doesn't strip the Authorization header (which it does for plain
   * <a download> clicks). Falls back to the response Content-Disposition
   * filename when present.
   */
  downloadCsv: (studyId: string, agentId: string, params?: SessionListParams) =>
    downloadAuthed(sessions.exportCsvUrl(studyId, agentId, params), "sessions.csv"),

  downloadJson: (studyId: string, agentId: string, params?: SessionListParams) =>
    downloadAuthed(sessions.exportJsonUrl(studyId, agentId, params), "sessions.json"),

  downloadAudioTurn: (
    studyId: string,
    agentId: string,
    sessionId: string,
    filename: string
  ) =>
    downloadAuthed(
      sessions.audioTurnUrl(studyId, agentId, sessionId, filename),
      filename
    ),
};

/** Fetch a URL with the auth token, then save the blob with a sensible filename. */
export async function downloadAuthed(url: string, fallbackName: string): Promise<void> {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, { headers });
  if (res.status === 401) {
    clearAuthToken();
    if (window.location.pathname !== "/login") window.location.href = "/login";
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    let detail = `Download failed: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail != null) {
        detail = formatApiError(body.detail, detail);
      }
    } catch {
      // not JSON, ignore
    }
    throw new Error(detail);
  }

  // Pull the filename from Content-Disposition when the backend sets it.
  let filename = fallbackName;
  const disp = res.headers.get("Content-Disposition") || "";
  const match = disp.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  if (match) filename = decodeURIComponent(match[1] || match[2] || fallbackName);

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(objectUrl);
}

// ── Settings (API Keys) ─────────────────────────────────────────

export interface ApiKeyStatus {
  field: string;
  env_var: string;
  is_set: boolean;
  source: "env" | "dashboard" | "none";
  masked_value: string;
}

export interface ApiKeysResponse {
  keys: ApiKeyStatus[];
}

export interface FlagStatus {
  field: string;
  env_var: string;
  enabled: boolean;
  source: "env" | "dashboard" | "default";
}

export interface FlagsResponse {
  flags: FlagStatus[];
}

export interface AudioStorageSettingStatus {
  field: string;
  env_var: string;
  is_set: boolean;
  source: "env" | "dashboard" | "none";
  display_value: string;
  sensitive: boolean;
}

export interface AudioStorageResponse {
  settings: AudioStorageSettingStatus[];
}

export const settingsApi = {
  getKeys: () => request<ApiKeysResponse>("/settings/keys"),

  updateKeys: (updates: Record<string, string>) =>
    request<ApiKeysResponse>("/settings/keys", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getFlags: () => request<FlagsResponse>("/settings/flags"),

  updateFlags: (updates: Record<string, boolean>) =>
    request<FlagsResponse>("/settings/flags", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getAudioStorage: () =>
    request<AudioStorageResponse>("/settings/audio-storage"),

  updateAudioStorage: (updates: Record<string, string>) =>
    request<AudioStorageResponse>("/settings/audio-storage", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getAuthConfig: () =>
    request<{ auth_enabled: boolean; username: string }>("/settings/auth"),
};

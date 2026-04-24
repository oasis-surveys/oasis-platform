import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  agents,
  participants,
  settingsApi,
  type Agent,
  type ParticipantIdentifier,
  type ApiKeyStatus,
} from "../lib/api";
import HelpTooltip from "../components/HelpTooltip";
import CopyButton from "../components/CopyButton";
import { useToast } from "../components/Toast";

// ── Model options ─────────────────────────────────────────────

const LLM_MODELS_MODULAR = [
  // OpenAI — latest models (as of March 2026)
  { value: "openai/gpt-5.4", label: "GPT-5.4 (latest flagship)", group: "OpenAI" },
  { value: "openai/gpt-5.2", label: "GPT-5.2", group: "OpenAI" },
  { value: "openai/gpt-5", label: "GPT-5", group: "OpenAI" },
  { value: "openai/gpt-5-mini", label: "GPT-5 Mini (fast)", group: "OpenAI" },
  { value: "openai/gpt-5-nano", label: "GPT-5 Nano (fastest)", group: "OpenAI" },
  { value: "openai/gpt-4.1", label: "GPT-4.1", group: "OpenAI" },
  { value: "openai/gpt-4.1-mini", label: "GPT-4.1 Mini", group: "OpenAI" },
  { value: "openai/gpt-4.1-nano", label: "GPT-4.1 Nano", group: "OpenAI" },
  { value: "openai/gpt-4o", label: "GPT-4o", group: "OpenAI" },
  { value: "openai/gpt-4o-mini", label: "GPT-4o Mini", group: "OpenAI" },
  { value: "openai/o4-mini", label: "o4-mini (reasoning)", group: "OpenAI" },
  { value: "openai/o3", label: "o3 (reasoning)", group: "OpenAI" },
  { value: "openai/o3-mini", label: "o3-mini (reasoning)", group: "OpenAI" },
  // Scaleway — Generative APIs (OpenAI-compatible)
  { value: "scaleway/qwen3-235b-a22b-instruct-2507", label: "Qwen 3 235B A22B Instruct", group: "Scaleway" },
  { value: "scaleway/mistral-small-3.2-24b-instruct-2506", label: "Mistral Small 3.2 24B", group: "Scaleway" },
  { value: "scaleway/voxtral-small-24b-2507", label: "Voxtral Small 24B (audio-capable)", group: "Scaleway" },
  { value: "scaleway/gpt-oss-120b", label: "GPT-OSS 120B", group: "Scaleway" },
  { value: "scaleway/llama-3.3-70b-instruct", label: "Llama 3.3 70B Instruct", group: "Scaleway" },
  { value: "scaleway/gemma-3-27b-it", label: "Gemma 3 27B IT", group: "Scaleway" },
  { value: "scaleway/deepseek-r1-distill-llama-70b", label: "DeepSeek-R1 Distill 70B", group: "Scaleway" },
  { value: "scaleway/devstral-2-123b-instruct-2512", label: "Devstral 2 123B Instruct", group: "Scaleway" },
  { value: "scaleway/pixtral-12b-2409", label: "Pixtral 12B (vision)", group: "Scaleway" },
  { value: "scaleway/llama-3.1-8b-instruct", label: "Llama 3.1 8B Instruct", group: "Scaleway" },
  { value: "scaleway/mistral-nemo-instruct-2407", label: "Mistral Nemo Instruct", group: "Scaleway" },
  // Azure OpenAI (self-hosted)
  { value: "azure/gpt-4o", label: "Azure GPT-4o", group: "Azure" },
  { value: "azure/gpt-4o-mini", label: "Azure GPT-4o Mini", group: "Azure" },
  // GCP Vertex AI (self-hosted)
  { value: "gcp/gemini-2.5-flash", label: "GCP Gemini 2.5 Flash", group: "GCP (Vertex AI)" },
  { value: "gcp/gemini-2.5-pro", label: "GCP Gemini 2.5 Pro", group: "GCP (Vertex AI)" },
  { value: "gcp/gemini-2.0-flash", label: "GCP Gemini 2.0 Flash", group: "GCP (Vertex AI)" },
];

const LLM_MODELS_V2V = [
  // OpenAI Realtime — latest speech-to-speech models
  { value: "openai/gpt-realtime-1.5", label: "GPT Realtime 1.5 (latest)", group: "OpenAI" },
  { value: "openai/gpt-realtime", label: "GPT Realtime", group: "OpenAI" },
  { value: "openai/gpt-realtime-mini", label: "GPT Realtime Mini (fast)", group: "OpenAI" },
  { value: "openai/gpt-4o-realtime-preview", label: "GPT-4o Realtime Preview", group: "OpenAI" },
  { value: "openai/gpt-4o-mini-realtime-preview", label: "GPT-4o Mini Realtime Preview", group: "OpenAI" },
  // Google Gemini — native audio (bidiGenerateContent)
  { value: "google/gemini-2.5-flash-native-audio-latest", label: "Gemini 2.5 Flash Native Audio (latest)", group: "Google" },
  { value: "google/gemini-2.5-flash-native-audio-preview-12-2025", label: "Gemini 2.5 Flash Native Audio (Dec 2025)", group: "Google" },
];

// ── V2V voice options ──────────────────────────────────────────
const OPENAI_REALTIME_VOICES = [
  { value: "coral", label: "Coral (default)" },
  { value: "alloy", label: "Alloy" },
  { value: "ash", label: "Ash" },
  { value: "ballad", label: "Ballad" },
  { value: "echo", label: "Echo" },
  { value: "fable", label: "Fable" },
  { value: "onyx", label: "Onyx" },
  { value: "nova", label: "Nova" },
  { value: "sage", label: "Sage" },
  { value: "shimmer", label: "Shimmer" },
  { value: "verse", label: "Verse" },
];

const GEMINI_LIVE_VOICES = [
  { value: "Charon", label: "Charon (default)" },
  { value: "Kore", label: "Kore" },
  { value: "Puck", label: "Puck" },
  { value: "Aoede", label: "Aoede" },
  { value: "Fenrir", label: "Fenrir" },
  { value: "Leda", label: "Leda" },
  { value: "Orus", label: "Orus" },
  { value: "Zephyr", label: "Zephyr" },
];

const STT_PROVIDERS = [
  { value: "openai", label: "OpenAI Whisper (default)" },
  { value: "deepgram", label: "Deepgram" },
  { value: "scaleway", label: "Scaleway Whisper" },
  { value: "self_hosted", label: "Self-Hosted (OpenAI-compatible)" },
];

const DEEPGRAM_MODELS = [
  { value: "nova-2", label: "Nova 2 (default)" },
  { value: "nova-2-general", label: "Nova 2 General" },
  { value: "nova-2-meeting", label: "Nova 2 Meeting" },
  { value: "nova-2-phonecall", label: "Nova 2 Phone Call" },
  { value: "nova-3", label: "Nova 3" },
  { value: "enhanced", label: "Enhanced" },
  { value: "base", label: "Base" },
];

const OPENAI_STT_MODELS = [
  { value: "whisper-1", label: "Whisper 1 (default)" },
  { value: "gpt-4o-transcribe", label: "GPT-4o Transcribe" },
  { value: "gpt-4o-mini-transcribe", label: "GPT-4o Mini Transcribe" },
];

const SCALEWAY_STT_MODELS = [
  { value: "whisper-large-v3", label: "Whisper Large V3" },
];

const TTS_PROVIDERS = [
  { value: "openai", label: "OpenAI TTS" },
  { value: "elevenlabs", label: "ElevenLabs" },
  { value: "self_hosted", label: "Self-Hosted (OpenAI-compatible)" },
];

const OPENAI_TTS_VOICES = [
  { value: "alloy", label: "Alloy (Neutral)" },
  { value: "echo", label: "Echo (Male)" },
  { value: "fable", label: "Fable (Male)" },
  { value: "onyx", label: "Onyx (Male)" },
  { value: "nova", label: "Nova (Female)" },
  { value: "shimmer", label: "Shimmer (Female)" },
];

const ELEVENLABS_VOICES = [
  { value: "rachel", label: "Rachel (Female)" },
  { value: "alice", label: "Alice (Female)" },
  { value: "lily", label: "Lily (Female)" },
  { value: "emily", label: "Emily (Female)" },
  { value: "bella", label: "Bella (Female)" },
  { value: "elli", label: "Elli (Female)" },
  { value: "josh", label: "Josh (Male)" },
  { value: "adam", label: "Adam (Male)" },
  { value: "arnold", label: "Arnold (Male)" },
  { value: "sam", label: "Sam (Male)" },
  { value: "charlie", label: "Charlie (Male)" },
  { value: "bill", label: "Bill (Male)" },
  { value: "george", label: "George (Male)" },
];

const OPENAI_TTS_MODELS = [
  { value: "gpt-4o-mini-tts", label: "GPT-4o Mini TTS (default)" },
  { value: "tts-1", label: "TTS-1 (fast)" },
  { value: "tts-1-hd", label: "TTS-1 HD (quality)" },
];

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "nl", label: "Dutch" },
  { value: "it", label: "Italian" },
  { value: "zh", label: "Chinese" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "ar", label: "Arabic" },
  { value: "hi", label: "Hindi" },
];

// ── Interview question types ──────────────────────────────────

interface InterviewQuestion {
  text: string;
  probes: string[];
  max_follow_ups: number;
  transition: string;
}

interface InterviewGuide {
  questions: InterviewQuestion[];
  closing_message: string;
}

const EMPTY_QUESTION: InterviewQuestion = {
  text: "",
  probes: [],
  max_follow_ups: 3,
  transition: "",
};

// ── File helpers ──────────────────────────────────────────────

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function generateGuideJSONTemplate(): string {
  const template: InterviewGuide = {
    questions: [
      {
        text: "Can you tell me about your experience with…?",
        probes: [
          "Can you elaborate on that?",
          "How did that make you feel?",
        ],
        max_follow_ups: 3,
        transition: "Thank you. Now I'd like to ask you about…",
      },
      {
        text: "What challenges have you faced in this area?",
        probes: [
          "Can you give me a specific example?",
          "How did you address that?",
        ],
        max_follow_ups: 2,
        transition: "",
      },
    ],
    closing_message: "Thank you for your time. This concludes our interview.",
  };
  return JSON.stringify(template, null, 2);
}

function generateGuideCSVTemplate(): string {
  const header = "question,probes,max_follow_ups,transition";
  const rows = [
    `"Can you tell me about your experience with…?","Can you elaborate on that?|How did that make you feel?",3,"Thank you. Now I'd like to ask you about…"`,
    `"What challenges have you faced in this area?","Can you give me a specific example?|How did you address that?",2,""`,
  ];
  const closingRow = `"__CLOSING_MESSAGE__","Thank you for your time. This concludes our interview.",,`;
  return [header, ...rows, closingRow].join("\n");
}

/** Parse a CSV row respecting quoted fields */
function parseCSVRow(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        result.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
  }
  result.push(current.trim());
  return result;
}

function parseGuideCSV(content: string): InterviewGuide {
  const lines = content
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) throw new Error("CSV must have a header row and at least one question row.");

  const header = parseCSVRow(lines[0]).map((h) => h.toLowerCase().replace(/[^a-z_]/g, ""));
  const qIdx = header.indexOf("question");
  const pIdx = header.indexOf("probes");
  const mIdx = header.indexOf("max_follow_ups");
  const tIdx = header.indexOf("transition");
  if (qIdx === -1) throw new Error("CSV must have a 'question' column.");

  const questions: InterviewQuestion[] = [];
  let closingMessage = "Thank you for your time. This concludes our interview.";

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCSVRow(lines[i]);
    const qText = cols[qIdx] || "";
    if (qText === "__CLOSING_MESSAGE__") {
      closingMessage = cols[pIdx !== -1 ? pIdx : 1] || closingMessage;
      continue;
    }
    if (!qText) continue;
    questions.push({
      text: qText,
      probes: pIdx !== -1 && cols[pIdx] ? cols[pIdx].split("|").map((s) => s.trim()).filter(Boolean) : [],
      max_follow_ups: mIdx !== -1 && cols[mIdx] ? parseInt(cols[mIdx]) || 3 : 3,
      transition: tIdx !== -1 ? cols[tIdx] || "" : "",
    });
  }

  if (questions.length === 0) throw new Error("No valid questions found in CSV.");
  return { questions, closing_message: closingMessage };
}

function parseGuideJSON(content: string): InterviewGuide {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("Invalid JSON format. Please check the file syntax.");
  }

  const obj = parsed as Record<string, unknown>;
  if (!obj || typeof obj !== "object") throw new Error("JSON must be an object.");
  if (!Array.isArray(obj.questions)) throw new Error("JSON must have a 'questions' array.");
  if (obj.questions.length === 0) throw new Error("Questions array must not be empty.");

  const questions: InterviewQuestion[] = obj.questions.map(
    (q: Record<string, unknown>, idx: number) => {
      if (!q || typeof q !== "object") throw new Error(`Question ${idx + 1} is not a valid object.`);
      if (typeof q.text !== "string" || !q.text.trim())
        throw new Error(`Question ${idx + 1} must have a non-empty 'text' field.`);
      return {
        text: q.text,
        probes: Array.isArray(q.probes) ? q.probes.filter((p: unknown) => typeof p === "string") : [],
        max_follow_ups: typeof q.max_follow_ups === "number" ? q.max_follow_ups : 3,
        transition: typeof q.transition === "string" ? q.transition : "",
      };
    }
  );

  return {
    questions,
    closing_message:
      typeof obj.closing_message === "string"
        ? obj.closing_message
        : "Thank you for your time. This concludes our interview.",
  };
}

function buildAgentConfigJSON(form: FormData): string {
  const resolvedModel =
    form.llm_model === "__custom__" ? form.llm_model_custom : form.llm_model;
  const maxDur = form.max_duration_seconds === "__custom__"
    ? (form.max_duration_custom ? parseInt(form.max_duration_custom) : null)
    : (form.max_duration_seconds ? parseInt(form.max_duration_seconds) : null);

  const config: Record<string, unknown> = {
    name: form.name,
    modality: form.modality,
    avatar: form.avatar || "neutral",
    system_prompt: form.system_prompt,
    welcome_message: form.welcome_message || null,
    pipeline_type: form.modality === "text" ? "modular" : form.pipeline_type,
    llm_model: resolvedModel,
    stt_provider: form.stt_provider,
    stt_model: form.stt_model || null,
    tts_provider: form.tts_provider,
    tts_model: form.tts_model || null,
    tts_voice: form.tts_voice || null,
    language: form.language,
    max_duration_seconds: maxDur,
    status: form.status,
    participant_id_mode: form.participant_id_mode,
    widget_title: form.widget_title || null,
    widget_description: form.widget_description || null,
    widget_primary_color: form.widget_primary_color || null,
    widget_listening_message: form.widget_listening_message || null,
    interview_mode: form.interview_mode,
    interview_guide:
      form.interview_mode === "structured" && form.interview_guide.questions.length > 0
        ? form.interview_guide
        : null,
    silence_timeout_seconds: form.silence_timeout_seconds ? parseInt(form.silence_timeout_seconds) : null,
    silence_prompt: form.silence_prompt || null,
    twilio_phone_number: form.twilio_phone_number || null,
  };
  return JSON.stringify(config, null, 2);
}

function importAgentConfigToForm(content: string): Partial<FormData> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch {
    throw new Error("Invalid JSON format.");
  }
  const obj = parsed as Record<string, unknown>;
  if (!obj || typeof obj !== "object") throw new Error("Config must be a JSON object.");

  // Validate required fields
  if (typeof obj.name !== "string" || !obj.name)
    throw new Error("Config must have a 'name' field.");
  if (typeof obj.system_prompt !== "string")
    throw new Error("Config must have a 'system_prompt' field.");

  const v2vModels = LLM_MODELS_V2V.map((m) => m.value);
  const modularModels = LLM_MODELS_MODULAR.map((m) => m.value);
  const allKnown = [...v2vModels, ...modularModels];
  const storedModel = (obj.llm_model as string) || "openai/gpt-5.4";
  const isKnown = allKnown.includes(storedModel);

  const presets = ["300", "600", "900", "1200", "1800", "2700", "3600", "5400", "7200"];
  const durStr = obj.max_duration_seconds != null ? String(obj.max_duration_seconds) : "";
  const isPresetDur = presets.includes(durStr);

  const result: Partial<FormData> = {
    name: obj.name as string,
    modality: (obj.modality as "voice" | "text") || "voice",
    avatar: (obj.avatar as string) || "neutral",
    system_prompt: obj.system_prompt as string,
    welcome_message: (obj.welcome_message as string) || "",
    pipeline_type: (obj.pipeline_type as "modular" | "voice_to_voice") || "modular",
    llm_model: isKnown ? storedModel : "__custom__",
    llm_model_custom: isKnown ? "" : storedModel,
    stt_provider: (obj.stt_provider as string) || "openai",
    stt_model: (obj.stt_model as string) || "gpt-4o-transcribe",
    tts_provider: (obj.tts_provider as string) || "openai",
    tts_model: (obj.tts_model as string) || "gpt-4o-mini-tts",
    tts_voice: (obj.tts_voice as string) || "alloy",
    language: (obj.language as string) || "en",
    max_duration_seconds: durStr && !isPresetDur ? "__custom__" : (durStr || "1800"),
    max_duration_custom: durStr && !isPresetDur ? durStr : "",
    status: (obj.status as "draft" | "active" | "paused") || "draft",
    participant_id_mode: (obj.participant_id_mode as "random" | "predefined" | "input") || "random",
    widget_title: (obj.widget_title as string) || "",
    widget_description: (obj.widget_description as string) || "",
    widget_primary_color: (obj.widget_primary_color as string) || "#111827",
    widget_listening_message: (obj.widget_listening_message as string) || "Agent is listening…",
    interview_mode: (obj.interview_mode as "free_form" | "structured") || "free_form",
    interview_guide: obj.interview_guide
      ? (obj.interview_guide as InterviewGuide)
      : { questions: [], closing_message: "Thank you for your time. This concludes our interview." },
    silence_timeout_seconds: obj.silence_timeout_seconds != null ? String(obj.silence_timeout_seconds) : "",
    silence_prompt: (obj.silence_prompt as string) || "Take your time. Let me know when you're ready to continue.",
    twilio_phone_number: (obj.twilio_phone_number as string) || "",
  };
  return result;
}

// ── Form data ─────────────────────────────────────────────────

interface FormData {
  name: string;
  modality: "voice" | "text";
  avatar: string;
  system_prompt: string;
  welcome_message: string;
  pipeline_type: "modular" | "voice_to_voice";
  llm_model: string;
  llm_model_custom: string;
  stt_provider: string;
  stt_model: string;
  tts_provider: string;
  tts_model: string;
  tts_voice: string;
  language: string;
  max_duration_seconds: string;
  max_duration_custom: string;
  status: "draft" | "active" | "paused";
  participant_id_mode: "random" | "predefined" | "input";
  widget_title: string;
  widget_description: string;
  widget_primary_color: string;
  widget_listening_message: string;
  interview_mode: "free_form" | "structured";
  interview_guide: InterviewGuide;
  silence_timeout_seconds: string;
  silence_prompt: string;
  twilio_phone_number: string;
}

const DEFAULT_FORM: FormData = {
  name: "",
  modality: "voice",
  avatar: "neutral",
  system_prompt: `You are a qualitative research interviewer conducting a semi-structured interview. Your goal is to explore the participant's experiences, perspectives, and opinions in depth.

Guidelines:
- Ask only ONE question at a time. Wait for the participant to respond fully before moving on.
- Use open-ended questions (e.g. "Can you tell me more about…", "How did that make you feel?").
- Listen actively: acknowledge responses before transitioning ("That's an interesting point…", "Thank you for sharing that.").
- Probe naturally when answers are vague or surface-level ("Could you give me a specific example?", "What do you mean by…?").
- Stay neutral — do not express personal opinions, agree/disagree, or lead the participant toward a particular answer.
- If the participant goes off-topic, gently guide them back without being dismissive.
- Keep your language warm, professional, and conversational. Avoid jargon.
- Respect silences — a brief pause can encourage the participant to elaborate.
- When all topics have been covered, thank the participant and close the interview gracefully.

Important: Adapt your style to the communication channel. For voice interviews, keep responses concise and natural-sounding — avoid bullet points, numbered lists, or formatting that doesn't translate to speech. For text-based interviews, you may use light formatting but still keep messages short and conversational to maintain engagement.`,
  welcome_message: "Hello, thank you for participating in this study.",
  pipeline_type: "modular",
  llm_model: "openai/gpt-4o",
  llm_model_custom: "",
  stt_provider: "openai",
  stt_model: "gpt-4o-transcribe",
  tts_provider: "openai",
  tts_model: "gpt-4o-mini-tts",
  tts_voice: "alloy",
  language: "en",
  max_duration_seconds: "1800",
  max_duration_custom: "",
  status: "draft",
  participant_id_mode: "random",
  widget_title: "",
  widget_description: "",
  widget_primary_color: "#0D7377",
  widget_listening_message: "Agent is listening…",
  interview_mode: "free_form",
  interview_guide: {
    questions: [],
    closing_message: "Thank you for your time. This concludes our interview.",
  },
  silence_timeout_seconds: "",
  silence_prompt: "Take your time. Let me know when you're ready to continue.",
  twilio_phone_number: "",
};

// ── Grouped select helper ──────────────────────────────────────
function GroupedSelect({
  value,
  onChange,
  options,
  className,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  options: { value: string; label: string; group: string }[];
  className?: string;
}) {
  const groups = [...new Set(options.map((o) => o.group))];
  return (
    <select value={value} onChange={onChange} className={className}>
      {groups.map((g) => (
        <optgroup key={g} label={g}>
          {options.filter((o) => o.group === g).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

export default function AgentFormPage() {
  const { studyId, agentId } = useParams<{
    studyId: string;
    agentId: string;
  }>();
  const navigate = useNavigate();
  const isNew = agentId === "new";

  const [form, setForm] = useState<FormData>(DEFAULT_FORM);
  const [existing, setExisting] = useState<Agent | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, showToast] = useToast();
  const [loading, setLoading] = useState(!isNew);

  // API key status (for missing key warnings)
  const [apiKeys, setApiKeys] = useState<ApiKeyStatus[]>([]);
  const isKeySet = useCallback(
    (field: string) => apiKeys.find((k) => k.field === field)?.is_set ?? true,
    [apiKeys]
  );

  // Participant identifiers (predefined mode)
  const [pidList, setPidList] = useState<ParticipantIdentifier[]>([]);
  const [newPid, setNewPid] = useState("");
  const [bulkPids, setBulkPids] = useState("");

  // File upload refs
  const guideFileRef = useRef<HTMLInputElement>(null);
  const configFileRef = useRef<HTMLInputElement>(null);

  // ── Interview guide file upload ──
  const handleGuideUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result as string;
        let guide: InterviewGuide;
        if (file.name.endsWith(".csv")) {
          guide = parseGuideCSV(text);
        } else {
          guide = parseGuideJSON(text);
        }
        setForm((f) => ({
          ...f,
          interview_mode: "structured",
          interview_guide: guide,
        }));
        showToast(`Loaded ${guide.questions.length} question(s) from ${file.name}`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to parse file");
      }
    };
    reader.readAsText(file);
  };

  // ── Agent config export ──
  const handleExportConfig = () => {
    const json = buildAgentConfigJSON(form);
    const safeName = (form.name || "agent").replace(/[^a-zA-Z0-9_-]/g, "_");
    downloadFile(json, `${safeName}_config.json`, "application/json");
    showToast("Agent config downloaded");
  };

  // ── Agent config import ──
  const handleImportConfig = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result as string;
        const imported = importAgentConfigToForm(text);
        setForm((f) => ({ ...f, ...imported }));
        showToast("Agent config imported successfully");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to import config");
      }
    };
    reader.readAsText(file);
  };

  // Text agents always use chat models, never V2V
  const llmModels =
    form.modality === "text"
      ? LLM_MODELS_MODULAR
      : form.pipeline_type === "voice_to_voice"
        ? LLM_MODELS_V2V
        : LLM_MODELS_MODULAR;
  const isCustomModel = form.llm_model === "__custom__";

  // STT model options based on provider
  const sttModelOptions =
    form.stt_provider === "deepgram"
      ? DEEPGRAM_MODELS
      : form.stt_provider === "scaleway"
        ? SCALEWAY_STT_MODELS
        : form.stt_provider === "self_hosted"
          ? []
          : OPENAI_STT_MODELS;

  // V2V voice options based on selected model
  const isGoogleV2V = form.llm_model.startsWith("google/");
  const v2vVoiceOptions = isGoogleV2V ? GEMINI_LIVE_VOICES : OPENAI_REALTIME_VOICES;

  // TTS voice options based on provider
  const ttsVoiceOptions =
    form.tts_provider === "openai"
      ? OPENAI_TTS_VOICES
      : form.tts_provider === "self_hosted"
        ? OPENAI_TTS_VOICES
        : ELEVENLABS_VOICES;

  // Fetch API key status on mount for missing-key warnings
  useEffect(() => {
    settingsApi.getKeys().then((res) => setApiKeys(res.keys)).catch(() => {});
  }, []);

  // Determine which API keys are required for current config
  // (computed here; isModularPipeline is inline since the full isModular is defined later)
  const resolvedModel = form.llm_model === "__custom__" ? form.llm_model_custom : form.llm_model;
  const isModularPipeline = form.modality === "text" || form.pipeline_type === "modular";
  const missingKeys: { label: string; field: string; envVar: string }[] = [];

  if (apiKeys.length > 0) {
    // LLM provider
    if (resolvedModel.startsWith("openai/") || (!resolvedModel.includes("/") && !resolvedModel.startsWith("__"))) {
      if (!isKeySet("openai_api_key")) missingKeys.push({ label: "OpenAI API Key", field: "openai_api_key", envVar: "OPENAI_API_KEY" });
    } else if (resolvedModel.startsWith("google/")) {
      if (!isKeySet("google_api_key")) missingKeys.push({ label: "Google API Key", field: "google_api_key", envVar: "GOOGLE_API_KEY" });
    } else if (resolvedModel.startsWith("scaleway/")) {
      if (!isKeySet("scaleway_secret_key")) missingKeys.push({ label: "Scaleway Secret Key", field: "scaleway_secret_key", envVar: "SCALEWAY_SECRET_KEY" });
    } else if (resolvedModel.startsWith("azure/")) {
      if (!isKeySet("azure_openai_api_key")) missingKeys.push({ label: "Azure OpenAI API Key", field: "azure_openai_api_key", envVar: "AZURE_OPENAI_API_KEY" });
    } else if (resolvedModel.startsWith("gcp/")) {
      if (!isKeySet("gcp_api_key")) missingKeys.push({ label: "GCP API Key", field: "gcp_api_key", envVar: "GCP_API_KEY" });
    }

    // STT provider (voice only, modular only)
    if (form.modality === "voice" && isModularPipeline) {
      if (form.stt_provider === "deepgram" && !isKeySet("deepgram_api_key")) {
        missingKeys.push({ label: "Deepgram API Key", field: "deepgram_api_key", envVar: "DEEPGRAM_API_KEY" });
      } else if (form.stt_provider === "openai" && !isKeySet("openai_api_key")) {
        if (!missingKeys.some((k) => k.field === "openai_api_key")) {
          missingKeys.push({ label: "OpenAI API Key", field: "openai_api_key", envVar: "OPENAI_API_KEY" });
        }
      } else if (form.stt_provider === "scaleway" && !isKeySet("scaleway_secret_key")) {
        if (!missingKeys.some((k) => k.field === "scaleway_secret_key")) {
          missingKeys.push({ label: "Scaleway Secret Key", field: "scaleway_secret_key", envVar: "SCALEWAY_SECRET_KEY" });
        }
      } else if (form.stt_provider === "self_hosted" && !isKeySet("self_hosted_stt_url")) {
        missingKeys.push({ label: "Self-Hosted STT URL", field: "self_hosted_stt_url", envVar: "SELF_HOSTED_STT_URL" });
      }
    }

    // TTS provider (voice only, modular only)
    if (form.modality === "voice" && isModularPipeline) {
      if (form.tts_provider === "elevenlabs" && !isKeySet("elevenlabs_api_key")) {
        missingKeys.push({ label: "ElevenLabs API Key", field: "elevenlabs_api_key", envVar: "ELEVENLABS_API_KEY" });
      } else if (form.tts_provider === "openai" && !isKeySet("openai_api_key")) {
        if (!missingKeys.some((k) => k.field === "openai_api_key")) {
          missingKeys.push({ label: "OpenAI API Key", field: "openai_api_key", envVar: "OPENAI_API_KEY" });
        }
      } else if (form.tts_provider === "self_hosted" && !isKeySet("self_hosted_tts_url")) {
        missingKeys.push({ label: "Self-Hosted TTS URL", field: "self_hosted_tts_url", envVar: "SELF_HOSTED_TTS_URL" });
      }
    }
  }

  useEffect(() => {
    if (isNew || !studyId || !agentId) return;
    agents
      .get(studyId, agentId)
      .then((a) => {
        setExisting(a);
        const v2vModels = LLM_MODELS_V2V.map((m) => m.value);
        const modularModels = LLM_MODELS_MODULAR.map((m) => m.value);
        const allKnown = [...v2vModels, ...modularModels];
        const storedModel = a.llm_model;
        const isKnown = allKnown.includes(storedModel);

        setForm({
          name: a.name,
          modality: a.modality || "voice",
          avatar: a.avatar || "neutral",
          system_prompt: a.system_prompt,
          welcome_message: a.welcome_message || "",
          pipeline_type: a.pipeline_type,
          llm_model: isKnown ? storedModel : "__custom__",
          llm_model_custom: isKnown ? "" : storedModel,
          stt_provider: a.stt_provider,
          stt_model: a.stt_model || "gpt-4o-transcribe",
          tts_provider: a.tts_provider,
          tts_model: a.tts_model || "gpt-4o-mini-tts",
          tts_voice: a.tts_voice || "alloy",
          language: a.language,
          max_duration_seconds: (() => {
            const val = a.max_duration_seconds?.toString() || "";
            const presets = ["300", "600", "900", "1200", "1800", "2700", "3600", "5400", "7200"];
            return val && !presets.includes(val) ? "__custom__" : val;
          })(),
          max_duration_custom: (() => {
            const val = a.max_duration_seconds?.toString() || "";
            const presets = ["300", "600", "900", "1200", "1800", "2700", "3600", "5400", "7200"];
            return val && !presets.includes(val) ? val : "";
          })(),
          status: a.status,
          participant_id_mode: a.participant_id_mode || "random",
          widget_title: a.widget_title || "",
          widget_description: a.widget_description || "",
          widget_primary_color: a.widget_primary_color || "#111827",
          widget_listening_message: a.widget_listening_message || "Agent is listening…",
          interview_mode: a.interview_mode || "free_form",
          interview_guide: a.interview_guide || {
            questions: [],
            closing_message: "Thank you for your time. This concludes our interview.",
          },
          silence_timeout_seconds: a.silence_timeout_seconds ? String(a.silence_timeout_seconds) : "",
          silence_prompt: a.silence_prompt || "Take your time. Let me know when you're ready to continue.",
          twilio_phone_number: a.twilio_phone_number || "",
        });
        participants.list(studyId, agentId).then(setPidList).catch(console.error);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [studyId, agentId, isNew]);

  const set =
    (field: keyof FormData) =>
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
      >
    ) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!studyId) return;
    setSaving(true);
    setError(null);

    const resolvedModel =
      form.llm_model === "__custom__" ? form.llm_model_custom : form.llm_model;

    const payload = {
      name: form.name,
      modality: form.modality,
      avatar: form.avatar || "neutral",
      system_prompt: form.system_prompt,
      welcome_message: form.welcome_message || null,
      pipeline_type: form.modality === "text" ? "modular" as const : form.pipeline_type,
      llm_model: resolvedModel,
      stt_provider: form.stt_provider,
      stt_model: form.stt_model || null,
      tts_provider: form.tts_provider,
      tts_model: form.tts_model || null,
      tts_voice: form.tts_voice || null,
      language: form.language,
      max_duration_seconds: (() => {
        const raw = form.max_duration_seconds === "__custom__"
          ? form.max_duration_custom
          : form.max_duration_seconds;
        return raw ? parseInt(raw) : null;
      })(),
      status: form.status,
      participant_id_mode: form.participant_id_mode,
      widget_title: form.widget_title || null,
      widget_description: form.widget_description || null,
      widget_primary_color: form.widget_primary_color || null,
      widget_listening_message: form.widget_listening_message || null,
      interview_mode: form.interview_mode,
      interview_guide:
        form.interview_mode === "structured" && form.interview_guide.questions.length > 0
          ? form.interview_guide
          : null,
      silence_timeout_seconds: form.silence_timeout_seconds ? parseInt(form.silence_timeout_seconds, 10) : null,
      silence_prompt: form.silence_prompt || null,
      twilio_phone_number: form.twilio_phone_number || null,
    };

    try {
      if (isNew) {
        const created = await agents.create(studyId, payload);
        navigate(`/studies/${studyId}/agents/${created.id}`);
        showToast("Agent created!");
      } else if (agentId) {
        const updated = await agents.update(studyId, agentId, payload);
        setExisting(updated);
        showToast("Changes saved");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!studyId || !agentId || !confirm("Delete this agent?")) return;
    await agents.delete(studyId, agentId);
    navigate(`/studies/${studyId}`);
  };

  // ── Participant identifier management ──
  const handleAddPid = async () => {
    if (!studyId || !agentId || !newPid.trim()) return;
    try {
      const created = await participants.create(studyId, agentId, {
        identifier: newPid.trim(),
      });
      setPidList((prev) => [...prev, created]);
      setNewPid("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add identifier");
    }
  };

  const handleBulkAddPids = async () => {
    if (!studyId || !agentId || !bulkPids.trim()) return;
    const ids = bulkPids
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length === 0) return;
    try {
      const created = await participants.bulkCreate(studyId, agentId, ids);
      setPidList((prev) => [...prev, ...created]);
      setBulkPids("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to bulk add");
    }
  };

  const handleDeletePid = async (pid: ParticipantIdentifier) => {
    if (!studyId || !agentId) return;
    await participants.delete(studyId, agentId, pid.id);
    setPidList((prev) => prev.filter((p) => p.id !== pid.id));
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <div className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-gray-700 animate-spin" />
        Loading…
      </div>
    );
  }

  const isModular = form.modality === "text" || form.pipeline_type === "modular";
  const isAzureLLM = form.llm_model.startsWith("azure/");
  const isScalewayLLM = form.llm_model.startsWith("scaleway/");
  const isGcpLLM = form.llm_model.startsWith("gcp/");

  const widgetUrl = existing ? `${window.location.origin}/interview/${existing.widget_key}` : "";
  const embedCode = existing
    ? `<iframe src="${widgetUrl}" width="100%" height="700" style="border:none;border-radius:16px;"${existing.modality === "voice" ? ' allow="microphone"' : ""} title="${existing.name} Interview"></iframe>`
    : "";

  return (
    <div className="max-w-3xl">
      {toast}

      {/* Breadcrumb */}
      <nav className="mb-6 text-sm text-gray-400 flex items-center gap-2">
        <Link to="/" className="hover:text-gray-600 transition-colors">Studies</Link>
        <ChevronRight />
        <Link to={`/studies/${studyId}`} className="hover:text-gray-600 transition-colors">Study</Link>
        <ChevronRight />
        <span className="text-gray-700 font-medium">
          {isNew ? "New Agent" : existing?.name || "Agent"}
        </span>
      </nav>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* ── Identity & Prompt ── */}
        <div className="card p-6">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              {isNew ? "Create Agent" : "Edit Agent"}
              <HelpTooltip text="An agent is an AI interviewer with its own system prompt, model configuration, and participant-facing widget." />
            </h2>
            <div className="flex items-center gap-2">
              {/* Import config */}
              <input
                ref={configFileRef}
                type="file"
                accept=".json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleImportConfig(file);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                onClick={() => configFileRef.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
                title="Import agent configuration from a JSON file"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
                Import Config
              </button>
              {/* Export config */}
              <button
                type="button"
                onClick={handleExportConfig}
                className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
                title="Export agent configuration as a JSON file"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                Export Config
              </button>
            </div>
          </div>

          {error && (
            <p className="mb-4 text-sm text-red-600 bg-red-50 rounded-xl px-4 py-2.5 animate-slide-up">
              {error}
            </p>
          )}

          {/* Activation warning */}
          {existing && form.status !== "active" && (
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 animate-fade-in">
              <svg className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              <div>
                <p className="text-sm font-medium text-amber-800">Agent is not active</p>
                <p className="text-xs text-amber-600 mt-0.5">
                  This agent is currently set to <strong>{form.status}</strong>. Participants will not be able to start interviews until the status is changed to <strong>Active</strong>.
                </p>
              </div>
            </div>
          )}

          {/* Widget key & sharing */}
          {existing && (
            <div className="mb-5 rounded-xl bg-gray-50 p-4 border border-gray-100">
              <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Share with participants
              </label>
              <div className="flex items-center gap-2 flex-wrap">
                <code className="text-xs font-mono text-gray-700 bg-white rounded-lg border border-gray-200 px-3 py-1.5 select-all">
                  {existing.widget_key}
                </code>
                <CopyButton
                  text={widgetUrl}
                  onCopied={(msg) => {
                    showToast(msg);
                    if (form.status !== "active") {
                      setTimeout(() => showToast("⚠️ Agent is not active. Participants cannot connect yet."), 350);
                    }
                  }}
                  toastMessage="Interview link copied!"
                  size="md"
                />
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(embedCode);
                    showToast("Embed code copied!");
                    if (form.status !== "active") {
                      setTimeout(() => showToast("⚠️ Agent is not active. Participants cannot connect yet."), 350);
                    }
                  }}
                  className="btn-secondary !py-1.5 !px-3 !text-xs"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                  </svg>
                  Embed
                </button>
                <HelpTooltip text="Copy the embed code to embed this interview widget in Qualtrics, SurveyMonkey, or any survey tool via an HTML iframe." />
              </div>
            </div>
          )}

          <div className="space-y-4">
            {/* ── Modality Selector (Voice vs Text) ── */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
                Interview Type
                <HelpTooltip text="Choose whether this agent conducts voice-based interviews (with audio) or text-based chat interviews (no microphone needed)." />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, modality: "voice" }))}
                  className={`relative rounded-xl border-2 px-4 py-4 text-left transition-all ${
                    form.modality === "voice"
                      ? "border-gray-900 bg-gray-50 shadow-sm"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center w-10 h-10 rounded-xl ${
                      form.modality === "voice" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-500"
                    } transition-colors`}>
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
                        <line x1="12" y1="19" x2="12" y2="23" />
                        <line x1="8" y1="23" x2="16" y2="23" />
                      </svg>
                    </div>
                    <div>
                      <div className="font-semibold text-sm text-gray-900">Voice Interview</div>
                      <div className="text-xs text-gray-500 mt-0.5">Audio-based with STT, LLM, and TTS</div>
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setForm((f) => {
                    const v2vModels = LLM_MODELS_V2V.map((m) => m.value);
                    const needsModelReset = v2vModels.includes(f.llm_model);
                    return {
                      ...f,
                      modality: "text",
                      pipeline_type: "modular",
                      ...(needsModelReset ? { llm_model: "openai/gpt-4.1" } : {}),
                    };
                  })}
                  className={`relative rounded-xl border-2 px-4 py-4 text-left transition-all ${
                    form.modality === "text"
                      ? "border-gray-900 bg-gray-50 shadow-sm"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`flex items-center justify-center w-10 h-10 rounded-xl ${
                      form.modality === "text" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-500"
                    } transition-colors`}>
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <div>
                      <div className="font-semibold text-sm text-gray-900">Text Chat</div>
                      <div className="text-xs text-gray-500 mt-0.5">Chat-based, no microphone needed</div>
                    </div>
                  </div>
                </button>
              </div>
            </div>

            {/* ── Avatar Selector (for text chat) ── */}
            {form.modality === "text" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
                  Agent Avatar
                  <HelpTooltip text="Choose an avatar that will represent the AI agent in the chat interface. This helps participants feel more connected." />
                </label>
                <div className="flex gap-3 flex-wrap">
                  {[
                    { id: "none", label: "None", emoji: null },
                    { id: "robot", label: "Robot", emoji: "🤖" },
                    { id: "neutral", label: "Neutral", emoji: "🧑‍💼" },
                    { id: "female", label: "Female", emoji: "👩‍💼" },
                    { id: "male", label: "Male", emoji: "👨‍💼" },
                  ].map((av) => (
                    <button
                      key={av.id}
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, avatar: av.id }))}
                      className={`flex flex-col items-center gap-2 rounded-xl border-2 px-5 py-4 transition-all ${
                        form.avatar === av.id
                          ? "border-gray-900 bg-gray-50 shadow-sm"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      {av.emoji ? (
                        <span className="text-3xl">{av.emoji}</span>
                      ) : (
                        <span className="text-2xl text-gray-400">⊘</span>
                      )}
                      <span className="text-xs font-medium text-gray-700">{av.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  Name
                  <HelpTooltip text="A descriptive name for this agent. Only visible to you in the admin dashboard." />
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={set("name")}
                  required
                  className="input-styled"
                  placeholder="e.g. Interview Bot Alpha"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  Status
                  <HelpTooltip text="Only 'Active' agents can receive interview connections. 'Draft' and 'Paused' agents are not accessible to participants." />
                </label>
                <select value={form.status} onChange={set("status")} className="select-styled">
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="paused">Paused</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                System Prompt
                <HelpTooltip text="Define the agent's behaviour, interview style, the questions it should ask, and any research-specific instructions. This is the main prompt that guides the AI." />
              </label>
              <textarea
                value={form.system_prompt}
                onChange={set("system_prompt")}
                rows={12}
                className="input-styled font-mono text-xs"
                placeholder="Define the agent's role, interview style, and instructions…"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                Welcome Message
                <HelpTooltip text="The first message the agent speaks when a participant connects. Leave empty for no greeting." />
              </label>
              <input
                type="text"
                value={form.welcome_message}
                onChange={set("welcome_message")}
                className="input-styled"
                placeholder="Hello, thank you for participating..."
              />
            </div>
          </div>
        </div>

        {/* ── Interview Mode ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            Interview Mode
            <HelpTooltip text="Free-form lets the AI guide the conversation naturally using your system prompt. Structured mode follows a pre-defined question guide with follow-up probes — ideal for semi-structured interviews." />
          </h3>

          <div className="mb-4">
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, interview_mode: "free_form" }))}
                className={`flex-1 rounded-xl border-2 px-4 py-3 text-left transition-all ${
                  form.interview_mode === "free_form"
                    ? "border-gray-900 bg-gray-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="font-medium text-sm text-gray-900">Free-form</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Open-ended conversation guided by the system prompt
                </div>
              </button>
              <button
                type="button"
                onClick={() => {
                  setForm((f) => ({
                    ...f,
                    interview_mode: "structured",
                    interview_guide:
                      f.interview_guide.questions.length === 0
                        ? { ...f.interview_guide, questions: [{ ...EMPTY_QUESTION }] }
                        : f.interview_guide,
                  }));
                }}
                className={`flex-1 rounded-xl border-2 px-4 py-3 text-left transition-all ${
                  form.interview_mode === "structured"
                    ? "border-gray-900 bg-gray-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="font-medium text-sm text-gray-900">Structured</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  Pre-defined questions with follow-up probes
                </div>
              </button>
            </div>
          </div>

          {form.interview_mode === "structured" && (
            <div className="space-y-4 animate-slide-up">
              <p className="text-xs text-gray-500">
                Define the questions your agent will ask in order.  For each question, add example
                probes that the agent can use to get deeper answers. The agent will adapt its probing
                based on what the participant actually says.
              </p>

              {/* ── Guide upload/download bar ── */}
              <div className="flex items-center justify-between rounded-xl bg-gray-50 border border-gray-100 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-500">Import guide:</span>
                  <input
                    ref={guideFileRef}
                    type="file"
                    accept=".json,.csv"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleGuideUpload(file);
                      e.target.value = "";
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => guideFileRef.current?.click()}
                    className="inline-flex items-center gap-1 rounded-lg bg-white border border-gray-200 px-2.5 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
                  >
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                    </svg>
                    Upload JSON / CSV
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-500">Templates:</span>
                  <button
                    type="button"
                    onClick={() => downloadFile(generateGuideJSONTemplate(), "interview_guide_template.json", "application/json")}
                    className="inline-flex items-center gap-1 rounded-lg bg-white border border-gray-200 px-2.5 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
                  >
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                    JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => downloadFile(generateGuideCSVTemplate(), "interview_guide_template.csv", "text/csv")}
                    className="inline-flex items-center gap-1 rounded-lg bg-white border border-gray-200 px-2.5 py-1 text-[11px] font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all"
                  >
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                    CSV
                  </button>
                  {/* Download current guide */}
                  {form.interview_guide.questions.length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        downloadFile(
                          JSON.stringify(form.interview_guide, null, 2),
                          `interview_guide.json`,
                          "application/json"
                        );
                        showToast("Interview guide downloaded");
                      }}
                      className="inline-flex items-center gap-1 rounded-lg bg-gray-900 text-white px-2.5 py-1 text-[11px] font-medium hover:bg-gray-800 transition-all"
                    >
                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                      </svg>
                      Export Current
                    </button>
                  )}
                </div>
              </div>

              {/* Question list */}
              {form.interview_guide.questions.map((q, qi) => (
                <div
                  key={qi}
                  className="rounded-xl border border-gray-200 p-4 space-y-3 relative group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      Question {qi + 1}
                    </span>
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      {qi > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            setForm((f) => {
                              const qs = [...f.interview_guide.questions];
                              [qs[qi - 1], qs[qi]] = [qs[qi], qs[qi - 1]];
                              return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                            });
                          }}
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all"
                          title="Move up"
                        >
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                          </svg>
                        </button>
                      )}
                      {qi < form.interview_guide.questions.length - 1 && (
                        <button
                          type="button"
                          onClick={() => {
                            setForm((f) => {
                              const qs = [...f.interview_guide.questions];
                              [qs[qi], qs[qi + 1]] = [qs[qi + 1], qs[qi]];
                              return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                            });
                          }}
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all"
                          title="Move down"
                        >
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                      )}
                      {form.interview_guide.questions.length > 1 && (
                        <button
                          type="button"
                          onClick={() => {
                            setForm((f) => ({
                              ...f,
                              interview_guide: {
                                ...f.interview_guide,
                                questions: f.interview_guide.questions.filter((_, i) => i !== qi),
                              },
                            }));
                          }}
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
                          title="Remove question"
                        >
                          <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Main question */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Question
                    </label>
                    <input
                      type="text"
                      value={q.text}
                      onChange={(e) => {
                        setForm((f) => {
                          const qs = [...f.interview_guide.questions];
                          qs[qi] = { ...qs[qi], text: e.target.value };
                          return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                        });
                      }}
                      className="input-styled"
                      placeholder="e.g. Can you tell me about your experience with…?"
                    />
                  </div>

                  {/* Probes */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                      Example Probes
                      <HelpTooltip text="Example follow-up questions the agent can use to explore this topic deeper. The agent will adapt these based on participant responses." />
                    </label>
                    <div className="space-y-1.5">
                      {q.probes.map((probe, pi) => (
                        <div key={pi} className="flex items-center gap-2">
                          <input
                            type="text"
                            value={probe}
                            onChange={(e) => {
                              setForm((f) => {
                                const qs = [...f.interview_guide.questions];
                                const probes = [...qs[qi].probes];
                                probes[pi] = e.target.value;
                                qs[qi] = { ...qs[qi], probes };
                                return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                              });
                            }}
                            className="input-styled flex-1 text-sm"
                            placeholder="e.g. Can you elaborate on that?"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              setForm((f) => {
                                const qs = [...f.interview_guide.questions];
                                qs[qi] = { ...qs[qi], probes: qs[qi].probes.filter((_, i) => i !== pi) };
                                return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                              });
                            }}
                            className="h-8 w-8 rounded-lg flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-all shrink-0"
                          >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={() => {
                          setForm((f) => {
                            const qs = [...f.interview_guide.questions];
                            qs[qi] = { ...qs[qi], probes: [...qs[qi].probes, ""] };
                            return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                          });
                        }}
                        className="text-xs text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1 py-1"
                      >
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                        </svg>
                        Add probe
                      </button>
                    </div>
                  </div>

                  {/* Max follow-ups */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                        Max Follow-ups
                        <HelpTooltip text="Maximum follow-up exchanges before the agent transitions to the next question. The agent may move on sooner if the topic is sufficiently explored." />
                      </label>
                      <input
                        type="number"
                        min={0}
                        max={10}
                        value={q.max_follow_ups}
                        onChange={(e) => {
                          setForm((f) => {
                            const qs = [...f.interview_guide.questions];
                            qs[qi] = { ...qs[qi], max_follow_ups: parseInt(e.target.value) || 3 };
                            return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                          });
                        }}
                        className="input-styled w-24"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                        Transition
                        <HelpTooltip text="Optional text the agent says when moving to the next question. Leave empty for a natural transition." />
                      </label>
                      <input
                        type="text"
                        value={q.transition}
                        onChange={(e) => {
                          setForm((f) => {
                            const qs = [...f.interview_guide.questions];
                            qs[qi] = { ...qs[qi], transition: e.target.value };
                            return { ...f, interview_guide: { ...f.interview_guide, questions: qs } };
                          });
                        }}
                        className="input-styled text-sm"
                        placeholder="e.g. Now I'd like to ask you about…"
                      />
                    </div>
                  </div>
                </div>
              ))}

              {/* Add question button */}
              <button
                type="button"
                onClick={() => {
                  setForm((f) => ({
                    ...f,
                    interview_guide: {
                      ...f.interview_guide,
                      questions: [...f.interview_guide.questions, { ...EMPTY_QUESTION }],
                    },
                  }));
                }}
                className="w-full rounded-xl border-2 border-dashed border-gray-200 hover:border-gray-400 px-4 py-3 text-sm text-gray-500 hover:text-gray-700 transition-all flex items-center justify-center gap-2"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Add Question
              </button>

              {/* Closing message */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                  Closing Message
                  <HelpTooltip text="The message the agent speaks after the last question is complete." />
                </label>
                <input
                  type="text"
                  value={form.interview_guide.closing_message}
                  onChange={(e) => {
                    setForm((f) => ({
                      ...f,
                      interview_guide: { ...f.interview_guide, closing_message: e.target.value },
                    }));
                  }}
                  className="input-styled"
                  placeholder="Thank you for your time…"
                />
              </div>

              <InfoBanner color="blue">
                <strong>How it works:</strong> The agent will ask each question in order, probe
                for deeper answers using your example probes, then naturally transition to the
                next question. The system prompt still applies — use it to set the tone, persona,
                and any additional context.
              </InfoBanner>
            </div>
          )}
        </div>

        {/* ── Pipeline & Model Config ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            {form.modality === "text" ? "LLM Configuration" : "Pipeline Configuration"}
            <HelpTooltip text={form.modality === "text"
              ? "Select the language model that will power the text chat."
              : "Choose how audio is processed. Modular chains STT → LLM → TTS services. Voice-to-Voice sends audio directly to multimodal models like OpenAI Realtime or Gemini Live."
            } />
          </h3>

          <div className="space-y-4">
            <div className={`grid ${form.modality === "text" ? "grid-cols-1" : "grid-cols-2"} gap-4`}>
              {form.modality === "voice" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Pipeline Type
                </label>
                <select
                  value={form.pipeline_type}
                  onChange={(e) => {
                    const pt = e.target.value as "modular" | "voice_to_voice";
                    setForm((f) => ({
                      ...f,
                      pipeline_type: pt,
                      llm_model:
                        pt === "voice_to_voice"
                          ? "openai/gpt-realtime-1.5"
                          : "openai/gpt-5.4",
                      tts_voice:
                        pt === "voice_to_voice" ? "coral" : f.tts_voice,
                    }));
                  }}
                  className="select-styled"
                >
                  <option value="modular">Modular (STT → LLM → TTS)</option>
                  <option value="voice_to_voice">Voice-to-Voice (Multimodal)</option>
                </select>
                {!isModular && (
                  <p className="text-xs text-amber-600 mt-1.5">
                    Routes audio directly to a multimodal endpoint. STT & TTS settings are not used.
                  </p>
                )}
              </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  LLM Model
                  <HelpTooltip text="Select the language model. Use 'Custom' to enter any LiteLLM-compatible model identifier." />
                </label>
                <GroupedSelect
                  value={form.llm_model}
                  onChange={set("llm_model")}
                  options={[
                    ...llmModels,
                    { value: "__custom__", label: "Custom (LiteLLM format)", group: "Custom" },
                  ]}
                  className="select-styled"
                />
              </div>
            </div>

            {/* Custom model identifier */}
            {isCustomModel && (
              <div className="animate-slide-up">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Custom Model Identifier
                </label>
                <input
                  type="text"
                  value={form.llm_model_custom}
                  onChange={set("llm_model_custom")}
                  className="input-styled font-mono"
                  placeholder="e.g. openai/gpt-4.1, anthropic/claude-3.5-sonnet, mistral/mistral-large-latest"
                />
                <p className="text-xs text-gray-400 mt-1.5">
                  Enter any model identifier in{" "}
                  <a href="https://docs.litellm.ai/docs/providers" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-600">LiteLLM format</a>.
                  Use <code className="bg-gray-100 px-1 rounded text-xs">provider/model-name</code> syntax.
                </p>
              </div>
            )}

            {/* V2V voice selection */}
            {form.modality === "voice" && !isModular && form.llm_model !== "__custom__" && (
              <div className="animate-slide-up">
                <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                  Voice
                  <HelpTooltip text="The voice used by the V2V model for audio responses. Different providers have different voice options." />
                </label>
                <select
                  value={form.tts_voice}
                  onChange={(e) => setForm((f) => ({ ...f, tts_voice: e.target.value }))}
                  className="select-styled"
                >
                  {v2vVoiceOptions.map((v) => (
                    <option key={v.value} value={v.value}>{v.label}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Provider hints */}
            {form.llm_model.startsWith("google/") && (
              <InfoBanner color="emerald">
                <strong>Google Gemini:</strong> Requires <code>GOOGLE_API_KEY</code> (from{" "}
                <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="underline">AI Studio</a>
                ) in your <code>.env</code> file.
              </InfoBanner>
            )}
            {isAzureLLM && (
              <InfoBanner color="blue">
                <strong>Azure OpenAI:</strong> Requires <code>AZURE_OPENAI_API_KEY</code>, <code>AZURE_OPENAI_ENDPOINT</code>, and <code>AZURE_OPENAI_API_VERSION</code> in your <code>.env</code> file.
              </InfoBanner>
            )}
            {isScalewayLLM && (
              <InfoBanner color="purple">
                <strong>Scaleway:</strong> Requires <code>SCALEWAY_SECRET_KEY</code> in your <code>.env</code> file. Uses Scaleway's OpenAI-compatible Generative APIs endpoint.
              </InfoBanner>
            )}
            {isGcpLLM && (
              <InfoBanner color="cyan">
                <strong>GCP Vertex AI:</strong> Requires <code>GCP_PROJECT_ID</code>, <code>GCP_LOCATION</code>, and <code>GCP_API_KEY</code> in your <code>.env</code> file.
              </InfoBanner>
            )}
            {isModular && form.stt_provider === "scaleway" && (
              <InfoBanner color="purple">
                <strong>Scaleway STT:</strong> Uses the Whisper Large V3 model via Scaleway's OpenAI-compatible API. Requires <code>SCALEWAY_SECRET_KEY</code>.
              </InfoBanner>
            )}
            {isModular && form.stt_provider === "self_hosted" && (
              <InfoBanner color="sky">
                <strong>Self-Hosted STT:</strong> Point this at any OpenAI-compatible speech-to-text server (e.g. Speaches/faster-whisper, LocalAI). Configure <code>SELF_HOSTED_STT_URL</code> in <Link to="/settings" className="underline font-medium">Settings</Link> or your <code>.env</code> file.
              </InfoBanner>
            )}
            {isModular && form.tts_provider === "self_hosted" && (
              <InfoBanner color="sky">
                <strong>Self-Hosted TTS:</strong> Point this at any OpenAI-compatible text-to-speech server (e.g. Kokoro, Piper, LocalAI). Configure <code>SELF_HOSTED_TTS_URL</code> in <Link to="/settings" className="underline font-medium">Settings</Link> or your <code>.env</code> file.
              </InfoBanner>
            )}

            {/* STT / TTS — only visible for voice modular pipeline */}
            {form.modality === "voice" && isModular && (
              <>
                {/* STT row */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                      Speech-to-Text
                      <HelpTooltip text="The STT provider converts participant audio into text for the LLM. Deepgram offers real-time streaming; Whisper models work for batch processing. Self-Hosted uses any OpenAI-compatible STT server." />
                    </label>
                    <select
                      value={form.stt_provider}
                      onChange={(e) => {
                        const p = e.target.value;
                        setForm((f) => ({
                          ...f,
                          stt_provider: p,
                          stt_model:
                            p === "deepgram"
                              ? "nova-2"
                              : p === "scaleway"
                                ? "whisper-large-v3"
                                : p === "self_hosted"
                                  ? "whisper-1"
                                  : "gpt-4o-transcribe",
                        }));
                      }}
                      className="select-styled"
                    >
                      {STT_PROVIDERS.map((p) => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                  {form.stt_provider !== "self_hosted" ? (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        STT Model
                      </label>
                      <select
                        value={form.stt_model}
                        onChange={set("stt_model")}
                        className="select-styled"
                      >
                        {sttModelOptions.map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        STT Model
                      </label>
                      <input
                        type="text"
                        value={form.stt_model}
                        onChange={set("stt_model")}
                        placeholder="whisper-1"
                        className="input-styled"
                      />
                    </div>
                  )}
                </div>

                {/* TTS row */}
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                      Text-to-Speech
                      <HelpTooltip text="The TTS provider converts the LLM's text response back into speech for the participant. Self-Hosted uses any OpenAI-compatible TTS server." />
                    </label>
                    <select
                      value={form.tts_provider}
                      onChange={(e) => {
                        const p = e.target.value;
                        setForm((f) => ({
                          ...f,
                          tts_provider: p,
                          tts_voice: p === "elevenlabs" ? "rachel" : "alloy",
                          tts_model: p === "openai" ? "gpt-4o-mini-tts" : p === "self_hosted" ? "tts-1" : "",
                        }));
                      }}
                      className="select-styled"
                    >
                      {TTS_PROVIDERS.map((p) => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))}
                    </select>
                  </div>
                  {form.tts_provider === "openai" && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        TTS Model
                      </label>
                      <select
                        value={form.tts_model}
                        onChange={set("tts_model")}
                        className="select-styled"
                      >
                        {OPENAI_TTS_MODELS.map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  {form.tts_provider === "self_hosted" && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1.5">
                        TTS Model
                      </label>
                      <input
                        type="text"
                        value={form.tts_model}
                        onChange={set("tts_model")}
                        placeholder="tts-1"
                        className="input-styled"
                      />
                    </div>
                  )}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1.5">
                      Voice
                    </label>
                    {form.tts_provider === "self_hosted" ? (
                      <input
                        type="text"
                        value={form.tts_voice}
                        onChange={set("tts_voice")}
                        placeholder="alloy"
                        className="input-styled"
                      />
                    ) : (
                      <select
                        value={form.tts_voice}
                        onChange={set("tts_voice")}
                        className="select-styled"
                      >
                        {ttsVoiceOptions.map((v) => (
                          <option key={v.value} value={v.value}>{v.label}</option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {form.tts_provider === "elevenlabs" && (
                  <InfoBanner color="amber">
                    <strong>ElevenLabs note:</strong> The free tier does not allow library voices via the API. You need a paid plan, or use a voice ID from your own ElevenLabs account.
                  </InfoBanner>
                )}
              </>
            )}
          </div>

          {/* ── Missing API key warnings ── */}
          {missingKeys.length > 0 && (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 animate-slide-up">
              <div className="flex items-start gap-3">
                <svg className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <h4 className="text-sm font-semibold text-amber-800 mb-1">Missing API Key{missingKeys.length > 1 ? "s" : ""}</h4>
                  <p className="text-xs text-amber-700 mb-2">
                    The current configuration requires API keys that are not yet configured. The agent will not work until these are set.
                  </p>
                  <ul className="space-y-1">
                    {missingKeys.map((k) => (
                      <li key={k.field} className="text-xs text-amber-700 flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                        <strong>{k.label}</strong> — set <code className="bg-amber-100 px-1 rounded text-[11px]">{k.envVar}</code> in your <code className="bg-amber-100 px-1 rounded text-[11px]">.env</code> file or via{" "}
                        <Link to="/settings" className="underline font-medium hover:text-amber-900">Settings</Link>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Interview Settings ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            Interview Settings
            <HelpTooltip text="Configure language and maximum session duration. Sessions exceeding the max duration will be automatically terminated." />
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Language</label>
              <select value={form.language} onChange={set("language")} className="select-styled">
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Max Duration
              </label>
              <select
                value={form.max_duration_seconds}
                onChange={set("max_duration_seconds")}
                className="select-styled"
              >
                <option value="300">5 minutes</option>
                <option value="600">10 minutes</option>
                <option value="900">15 minutes</option>
                <option value="1200">20 minutes</option>
                <option value="1800">30 minutes</option>
                <option value="2700">45 minutes</option>
                <option value="3600">60 minutes</option>
                <option value="5400">90 minutes</option>
                <option value="7200">120 minutes</option>
                <option value="__custom__">Custom</option>
              </select>
            </div>
          </div>
          {form.max_duration_seconds === "__custom__" && (
            <div className="animate-slide-up">
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Custom Duration (seconds)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min="60"
                  max="7200"
                  step="1"
                  value={form.max_duration_custom}
                  onChange={set("max_duration_custom")}
                  className="input-styled w-40 font-mono"
                  placeholder="e.g. 450"
                />
                <span className="text-xs text-gray-400">
                  {form.max_duration_custom
                    ? (() => {
                        const s = parseInt(form.max_duration_custom);
                        if (isNaN(s)) return "";
                        const m = Math.floor(s / 60);
                        const r = s % 60;
                        return `= ${m}m ${r}s`;
                      })()
                    : "Min 60s · Max 7200s (2 hours)"}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* ── Silence Handling ── */}
        {form.modality === "voice" && form.pipeline_type === "modular" && (
          <div className="card p-6">
            <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
              Silence Handling
              <HelpTooltip text="When the participant stops speaking for a set duration, the agent can automatically send a follow-up prompt to re-engage. Leave timeout empty to disable." />
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Silence Timeout (seconds)
                </label>
                <input
                  type="number"
                  value={form.silence_timeout_seconds}
                  onChange={set("silence_timeout_seconds")}
                  className="input-styled"
                  placeholder="e.g. 10 (leave empty to disable)"
                  min={5}
                  max={120}
                />
                <p className="mt-1 text-xs text-gray-400">
                  Seconds of silence before sending the follow-up prompt. Leave empty to disable.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Silence Prompt
                </label>
                <input
                  type="text"
                  value={form.silence_prompt}
                  onChange={set("silence_prompt")}
                  className="input-styled"
                  placeholder="Take your time..."
                />
                <p className="mt-1 text-xs text-gray-400">
                  The message spoken by the agent when extended silence is detected.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ── Participant Identification ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            Participant Identification
            <HelpTooltip text="Choose how participants are identified. 'Random' auto-generates IDs. 'Predefined' creates unique links per participant. 'User Input' asks participants to enter their ID." />
          </h3>

          <div className="mb-4">
            <select
              value={form.participant_id_mode}
              onChange={set("participant_id_mode")}
              className="select-styled"
            >
              <option value="random">
                Random — Auto-generate ID when participant starts
              </option>
              <option value="predefined">
                Predefined — Create unique links for each participant
              </option>
              <option value="input">
                User Input — Participant enters their ID in the widget
              </option>
            </select>
          </div>

          {form.participant_id_mode === "random" && (
            <p className="text-xs text-gray-400">
              A unique participant ID will be automatically generated for each interview session.
            </p>
          )}

          {form.participant_id_mode === "input" && (
            <p className="text-xs text-gray-400">
              Participants will be prompted to enter their identifier before starting the interview.
            </p>
          )}

          {form.participant_id_mode === "predefined" && !isNew && (
            <div className="mt-4 space-y-4 animate-slide-up">
              <p className="text-xs text-gray-500">
                Create participant identifiers below. Each gets a unique link:{" "}
                <code className="bg-gray-100 px-1.5 py-0.5 rounded text-[11px]">
                  /interview/{existing?.widget_key}?pid=IDENTIFIER
                </code>
              </p>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={newPid}
                  onChange={(e) => setNewPid(e.target.value)}
                  className="input-styled flex-1"
                  placeholder="Participant ID (e.g. P001)"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddPid();
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={handleAddPid}
                  className="btn-primary !py-2"
                >
                  Add
                </button>
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer text-gray-500 hover:text-gray-700 transition-colors">
                  Bulk add (one per line)
                </summary>
                <div className="mt-2 flex gap-2">
                  <textarea
                    value={bulkPids}
                    onChange={(e) => setBulkPids(e.target.value)}
                    rows={4}
                    className="input-styled flex-1 font-mono"
                    placeholder={"P001\nP002\nP003"}
                  />
                  <button
                    type="button"
                    onClick={handleBulkAddPids}
                    className="btn-primary self-end"
                  >
                    Add All
                  </button>
                </div>
              </details>

              {pidList.length > 0 && (
                <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 max-h-60 overflow-y-auto">
                  {pidList.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center justify-between px-3.5 py-2.5 text-sm hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <code className="font-mono text-gray-800 text-xs">{p.identifier}</code>
                        {p.used ? (
                          <span className="rounded-full bg-blue-50 text-blue-700 px-2 py-0.5 text-[10px] font-semibold">
                            Used
                          </span>
                        ) : (
                          <span className="rounded-full bg-gray-100 text-gray-500 px-2 py-0.5 text-[10px] font-semibold">
                            Available
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <CopyButton
                          text={`${window.location.origin}/interview/${existing?.widget_key}?pid=${p.identifier}`}
                          onCopied={(msg) => {
                            showToast(msg);
                            if (form.status !== "active") {
                              setTimeout(() => showToast("⚠️ Agent is not active. Participants cannot connect yet."), 350);
                            }
                          }}
                          toastMessage="Participant link copied!"
                        />
                        {!p.used && (
                          <button
                            type="button"
                            onClick={() => handleDeletePid(p)}
                            className="h-7 w-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
                          >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {pidList.length === 0 && (
                <p className="text-xs text-gray-300 text-center py-6 border border-dashed border-gray-200 rounded-xl">
                  No participant identifiers yet.
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Widget Customisation ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            Widget Appearance
            <HelpTooltip text="Customise how the interview widget looks and behaves when participants visit the link. Changes are applied instantly." />
          </h3>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Widget Title
                </label>
                <input
                  type="text"
                  value={form.widget_title}
                  onChange={set("widget_title")}
                  className="input-styled"
                  placeholder="Voice Interview"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Primary Colour
                </label>
                <div className="flex gap-2">
                  <input
                    type="color"
                    value={form.widget_primary_color}
                    onChange={set("widget_primary_color")}
                    className="h-[42px] w-[42px] rounded-xl border border-gray-200 cursor-pointer p-0.5"
                  />
                  <input
                    type="text"
                    value={form.widget_primary_color}
                    onChange={set("widget_primary_color")}
                    className="input-styled flex-1 font-mono"
                    placeholder="#111827"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Widget Description
              </label>
              <textarea
                value={form.widget_description}
                onChange={set("widget_description")}
                rows={2}
                className="input-styled"
                placeholder="Click the button below to begin your interview."
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                Listening Message
                <HelpTooltip text="Text shown to participants while the agent is listening to them speak. This appears below the orb animation." />
              </label>
              <input
                type="text"
                value={form.widget_listening_message}
                onChange={set("widget_listening_message")}
                className="input-styled"
                placeholder="Agent is listening…"
              />
            </div>

            <div className="flex items-center gap-3 rounded-xl bg-gray-50 p-3 border border-gray-100">
              <div
                className="h-8 w-8 rounded-full shadow-sm border border-white/50"
                style={{
                  background: `radial-gradient(circle at 35% 30%, ${form.widget_primary_color}dd, ${form.widget_primary_color})`,
                }}
              />
              <span className="text-xs text-gray-500">Preview of your primary colour</span>
            </div>
          </div>
        </div>

        {/* ── Telephony (Twilio) ── */}
        <div className="card p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-5 flex items-center gap-2">
            Telephony (Twilio)
            <HelpTooltip text="Connect a Twilio phone number so participants can call in for interviews via regular phone. Requires TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in your .env file." />
            <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider bg-gray-100 rounded-full px-2 py-0.5">Optional</span>
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1">
                Twilio Phone Number
                <HelpTooltip text="The Twilio phone number assigned to this agent (e.g. +1234567890). Participants will call this number to start an interview." />
              </label>
              <input
                type="tel"
                value={form.twilio_phone_number}
                onChange={set("twilio_phone_number")}
                className="input-styled font-mono"
                placeholder="+1234567890"
              />
            </div>

            {/* Webhook URL info (only shown for existing agents) */}
            {existing && (
              <div className="rounded-xl bg-gray-50 p-4 border border-gray-100 space-y-3">
                <label className="block text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                  Twilio Webhook Configuration
                </label>
                <p className="text-xs text-gray-500">
                  Configure your Twilio phone number's <strong>Voice webhook</strong> (HTTP POST) to point to:
                </p>
                <div className="flex items-center gap-2">
                  <code className="text-xs font-mono text-gray-700 bg-white rounded-lg border border-gray-200 px-3 py-1.5 select-all flex-1 truncate">
                    {`${window.location.origin}/api/twilio/voice/${existing.id}`}
                  </code>
                  <CopyButton
                    text={`${window.location.origin}/api/twilio/voice/${existing.id}`}
                    onCopied={showToast}
                    toastMessage="Webhook URL copied!"
                    size="md"
                  />
                </div>
                <InfoBanner color="amber">
                  <strong>Setup steps:</strong>{" "}
                  1. Buy a phone number in your{" "}
                  <a href="https://console.twilio.com/us1/develop/phone-numbers/manage/incoming" target="_blank" rel="noopener noreferrer" className="underline">Twilio Console</a>.{" "}
                  2. Set the Voice webhook URL above.{" "}
                  3. Add <code>TWILIO_ACCOUNT_SID</code> and <code>TWILIO_AUTH_TOKEN</code> to your <code>.env</code> file.{" "}
                  4. For local development, use{" "}
                  <a href="https://ngrok.com" target="_blank" rel="noopener noreferrer" className="underline">ngrok</a>{" "}
                  to expose your server.
                </InfoBanner>
              </div>
            )}
          </div>
        </div>

        {/* ── Actions ── */}
        <div className="flex items-center justify-between pb-8">
          <div>
            {!isNew && (
              <button type="button" onClick={handleDelete} className="btn-danger">
                Delete Agent
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Link to={`/studies/${studyId}`} className="btn-secondary">
              Cancel
            </Link>
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? (
                <>
                  <div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Saving…
                </>
              ) : isNew ? (
                "Create Agent"
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

// ── Helper Components ────────────────────────────────────────

function ChevronRight() {
  return (
    <svg className="h-3.5 w-3.5 text-gray-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function InfoBanner({ color, children }: { color: string; children: React.ReactNode }) {
  const colorMap: Record<string, string> = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    purple: "bg-purple-50 border-purple-200 text-purple-700",
    cyan: "bg-cyan-50 border-cyan-200 text-cyan-700",
    amber: "bg-amber-50 border-amber-200 text-amber-700",
  };
  return (
    <div className={`rounded-xl border px-4 py-3 text-xs ${colorMap[color] || colorMap.blue} animate-fade-in`}>
      {children}
    </div>
  );
}

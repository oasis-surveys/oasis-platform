/**
 * OASIS — Settings page.
 *
 * Allows admins to view/update API keys at runtime without restarting.
 * Dashboard overrides take priority over .env values.
 */

import { useState, useEffect, useCallback } from "react";
import {
  settingsApi,
  type ApiKeyStatus,
  type AudioStorageSettingStatus,
  type FlagStatus,
} from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import HelpTooltip from "../components/HelpTooltip";
import { useToast } from "../components/Toast";
import SettingsCollapsibleSection from "../components/SettingsCollapsibleSection";

// Labels and descriptions for each API key field
const KEY_INFO: Record<string, { label: string; description: string; category: string }> = {
  openai_api_key: {
    label: "OpenAI API Key",
    description: "Required for GPT models, Realtime voice-to-voice, TTS, and embeddings (RAG).",
    category: "AI Providers",
  },
  deepgram_api_key: {
    label: "Deepgram API Key",
    description: "Required for Deepgram STT (speech-to-text).",
    category: "AI Providers",
  },
  elevenlabs_api_key: {
    label: "ElevenLabs API Key",
    description: "Required for ElevenLabs TTS (text-to-speech).",
    category: "AI Providers",
  },
  cartesia_api_key: {
    label: "Cartesia API Key",
    description: "Required for Cartesia TTS.",
    category: "AI Providers",
  },
  google_api_key: {
    label: "Google AI API Key",
    description: "Required for Gemini text models (google/...) and Gemini Live voice-to-voice.",
    category: "AI Providers",
  },
  anthropic_api_key: {
    label: "Anthropic API Key",
    description: "Required for Claude models (anthropic/claude-...).",
    category: "AI Providers",
  },
  openai_compatible_llm_url: {
    label: "OpenAI-Compatible LLM URL",
    description: "Base URL for any custom OpenAI-compatible LLM endpoint (LiteLLM proxy, vLLM, Ollama). Used by 'custom/<model>' selections.",
    category: "Self-Hosted",
  },
  openai_compatible_llm_api_key: {
    label: "OpenAI-Compatible LLM API Key",
    description: "Bearer token for the custom LLM endpoint (optional — many local servers ignore this).",
    category: "Self-Hosted",
  },
  scaleway_secret_key: {
    label: "Scaleway Secret Key",
    description: "Required for Scaleway LLM, STT (Whisper), and Voxtral models.",
    category: "AI Providers",
  },
  scaleway_project_id: {
    label: "Scaleway Project ID",
    description: "Required for Scaleway Generative APIs (sent as X-Project-ID).",
    category: "AI Providers",
  },
  azure_openai_api_key: {
    label: "Azure OpenAI API Key",
    description: "Required for self-hosted Azure OpenAI models.",
    category: "Self-Hosted",
  },
  azure_openai_endpoint: {
    label: "Azure OpenAI Endpoint",
    description: "The base URL for your Azure OpenAI deployment.",
    category: "Self-Hosted",
  },
  azure_openai_api_version: {
    label: "Azure OpenAI API Version",
    description: "API version string used by the Azure OpenAI client (e.g. 2024-08-01-preview).",
    category: "Self-Hosted",
  },
  gcp_project_id: {
    label: "GCP Project ID",
    description: "Required for GCP Vertex AI models.",
    category: "Self-Hosted",
  },
  gcp_location: {
    label: "GCP Location",
    description: "Vertex AI region (e.g. us-central1, europe-west4).",
    category: "Self-Hosted",
  },
  gcp_api_key: {
    label: "GCP API Key",
    description: "Alternative to Application Default Credentials for GCP.",
    category: "Self-Hosted",
  },
  self_hosted_stt_url: {
    label: "Self-Hosted STT URL",
    description: "Base URL for an OpenAI-compatible STT server (e.g. Speaches, faster-whisper).",
    category: "Self-Hosted",
  },
  self_hosted_stt_api_key: {
    label: "Self-Hosted STT API Key",
    description: "API key for the self-hosted STT server (optional — many local servers ignore this).",
    category: "Self-Hosted",
  },
  self_hosted_stt_model: {
    label: "Self-Hosted STT Model",
    description: "Model name to pass to the STT server (default: whisper-1).",
    category: "Self-Hosted",
  },
  self_hosted_tts_url: {
    label: "Self-Hosted TTS URL",
    description: "Base URL for an OpenAI-compatible TTS server (e.g. Kokoro, Piper).",
    category: "Self-Hosted",
  },
  self_hosted_tts_api_key: {
    label: "Self-Hosted TTS API Key",
    description: "API key for the self-hosted TTS server (optional — many local servers ignore this).",
    category: "Self-Hosted",
  },
  self_hosted_tts_model: {
    label: "Self-Hosted TTS Model",
    description: "Model name to pass to the TTS server (default: tts-1).",
    category: "Self-Hosted",
  },
  embedding_api_url: {
    label: "Embedding API URL",
    description: "Base URL for an OpenAI-compatible embedding server. Leave empty to use OpenAI.",
    category: "Self-Hosted",
  },
  embedding_api_key: {
    label: "Embedding API Key",
    description: "API key for the embedding server. Falls back to OpenAI API key if empty.",
    category: "Self-Hosted",
  },
  embedding_model: {
    label: "Embedding Model",
    description: "Model name for embeddings (default: text-embedding-3-small). Must output 1536 dimensions to match the DB schema.",
    category: "Self-Hosted",
  },
  twilio_account_sid: {
    label: "Twilio Account SID",
    description: "Required for telephony (phone call) interviews.",
    category: "Telephony",
  },
  twilio_auth_token: {
    label: "Twilio Auth Token",
    description: "Required for telephony (phone call) interviews.",
    category: "Telephony",
  },
  twilio_phone_number: {
    label: "Twilio Phone Number",
    description: "The provisioned Twilio phone number for inbound calls.",
    category: "Telephony",
  },
};

const AUDIO_STORAGE_INFO: Record<
  string,
  { label: string; description: string; inputType?: "password" | "text" }
> = {
  audio_storage_backend: {
    label: "Storage backend",
    description: "Where interview session WAV files are written (local disk or S3-compatible object storage).",
  },
  audio_storage_local_path: {
    label: "Local storage path",
    description: "Directory on the server (or Docker volume mount) for WAV files when backend is local.",
    inputType: "text",
  },
  audio_s3_bucket: {
    label: "S3 bucket",
    description: "Bucket name for interview audio when backend is S3.",
    inputType: "text",
  },
  audio_s3_prefix: {
    label: "S3 key prefix",
    description: "Folder prefix inside the bucket (default: oasis-recordings).",
    inputType: "text",
  },
  audio_s3_region: {
    label: "S3 region",
    description: "AWS region (e.g. us-east-1) or region for your S3-compatible provider.",
    inputType: "text",
  },
  audio_s3_endpoint_url: {
    label: "S3 endpoint URL",
    description: "Optional custom endpoint for MinIO, Scaleway, etc. Leave empty for AWS.",
    inputType: "text",
  },
  audio_s3_access_key_id: {
    label: "S3 access key ID",
    description: "Access key with write permissions to the bucket.",
    inputType: "password",
  },
  audio_s3_secret_access_key: {
    label: "S3 secret access key",
    description: "Secret key paired with the access key ID.",
    inputType: "password",
  },
};

const CATEGORIES = ["AI Providers", "Self-Hosted", "Telephony"];

function audioSettingValue(
  settings: AudioStorageSettingStatus[],
  field: string,
  fallback: string
): string {
  const row = settings.find((s) => s.field === field);
  if (!row?.is_set) return fallback;
  if (row.sensitive) return row.display_value;
  return row.display_value || fallback;
}

export default function SettingsPage() {
  const { authEnabled, username } = useAuth();
  const [toastNode, showToast] = useToast();
  const [keys, setKeys] = useState<ApiKeyStatus[]>([]);
  const [flags, setFlags] = useState<FlagStatus[]>([]);
  const [audioStorage, setAudioStorage] = useState<AudioStorageSettingStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingFields, setEditingFields] = useState<Record<string, string>>({});
  const [editingAudioFields, setEditingAudioFields] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [flagSaving, setFlagSaving] = useState<string | null>(null);

  const loadKeys = useCallback(async () => {
    setLoadError(null);
    try {
      const [k, f, a] = await Promise.all([
        settingsApi.getKeys(),
        settingsApi.getFlags(),
        settingsApi.getAudioStorage(),
      ]);
      setKeys(k.keys);
      setFlags(f.flags);
      setAudioStorage(a.settings);
    } catch (err) {
      setLoadError(
        err instanceof Error ? err.message : "Failed to load settings. Check your connection and try again."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleFlagToggle = async (field: string, value: boolean) => {
    setFlagSaving(field);
    try {
      const res = await settingsApi.updateFlags({ [field]: value });
      setFlags(res.flags);
      showToast(value ? "Setting enabled" : "Setting disabled", "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setFlagSaving(null);
    }
  };

  const openaiUseEu = flags.find((f) => f.field === "openai_use_eu");

  const handleEdit = (field: string) => {
    setEditingFields((prev) => ({ ...prev, [field]: "" }));
  };

  const handleCancelEdit = (field: string) => {
    setEditingFields((prev) => {
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleClearOverride = async (field: string) => {
    setSaving(true);
    try {
      const res = await settingsApi.updateKeys({ [field]: "" });
      setKeys(res.keys);
      showToast("Override cleared — using .env value", "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async (field: string) => {
    const value = editingFields[field];
    if (!value) return;

    setSaving(true);
    try {
      const res = await settingsApi.updateKeys({ [field]: value });
      setKeys(res.keys);
      setEditingFields((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
      showToast("API key updated successfully", "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setSaving(false);
    }
  };

  const handleAudioBackendChange = async (value: "local" | "s3") => {
    setSaving(true);
    try {
      const res = await settingsApi.updateAudioStorage({
        audio_storage_backend: value,
      });
      setAudioStorage(res.settings);
      showToast(`Audio storage: ${value}`, "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setSaving(false);
    }
  };

  const handleAudioEdit = (field: string) => {
    setEditingAudioFields((prev) => ({ ...prev, [field]: "" }));
  };

  const handleAudioCancelEdit = (field: string) => {
    setEditingAudioFields((prev) => {
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleAudioClearOverride = async (field: string) => {
    setSaving(true);
    try {
      const res = await settingsApi.updateAudioStorage({ [field]: "" });
      setAudioStorage(res.settings);
      showToast("Override cleared — using .env value", "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setSaving(false);
    }
  };

  const handleAudioSave = async (field: string) => {
    const value = editingAudioFields[field];
    if (value === undefined || value === "") return;

    setSaving(true);
    try {
      const res = await settingsApi.updateAudioStorage({ [field]: value });
      setAudioStorage(res.settings);
      setEditingAudioFields((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
      showToast("Audio storage setting updated", "success");
    } catch (err: any) {
      showToast(`Error: ${err.message}`, "warning");
    } finally {
      setSaving(false);
    }
  };

  const audioBackend = audioSettingValue(audioStorage, "audio_storage_backend", "local");
  const isS3Backend = audioBackend === "s3";

  const renderAudioStorageRow = (setting: AudioStorageSettingStatus) => {
    const info = AUDIO_STORAGE_INFO[setting.field];
    if (!info || setting.field === "audio_storage_backend") return null;

    if (isS3Backend && setting.field === "audio_storage_local_path") return null;
    if (!isS3Backend && setting.field.startsWith("audio_s3_")) return null;

    const isEditing = setting.field in editingAudioFields;
    const inputType = info.inputType ?? (setting.sensitive ? "password" : "text");

    return (
      <div key={setting.field} className="px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-sm font-medium text-gray-900">{info.label}</span>
              <code className="text-[10px] text-gray-400 bg-gray-50 rounded px-1.5 py-0.5">
                {setting.env_var}
              </code>
              {setting.is_set && (
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    setting.source === "dashboard"
                      ? "bg-blue-50 text-blue-700"
                      : "bg-green-50 text-green-700"
                  }`}
                >
                  {setting.source === "dashboard" ? "Dashboard" : ".env"}
                </span>
              )}
              {!setting.is_set && (
                <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                  Not set
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400">{info.description}</p>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {setting.is_set && !isEditing && (
              <span className="text-xs text-gray-400 font-mono max-w-[14rem] truncate">
                {setting.display_value}
              </span>
            )}

            {isEditing ? (
              <div className="flex items-center gap-2">
                <input
                  type={inputType}
                  value={editingAudioFields[setting.field]}
                  onChange={(e) =>
                    setEditingAudioFields((prev) => ({
                      ...prev,
                      [setting.field]: e.target.value,
                    }))
                  }
                  placeholder="Enter new value…"
                  className="w-64 rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-1.5 text-xs text-gray-900 focus:border-gray-900 focus:ring-1 focus:ring-gray-900 outline-none transition-all"
                  autoFocus
                />
                <button
                  onClick={() => handleAudioSave(setting.field)}
                  disabled={saving || !editingAudioFields[setting.field]}
                  className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50 transition-all"
                >
                  Save
                </button>
                <button
                  onClick={() => handleAudioCancelEdit(setting.field)}
                  className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-all"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleAudioEdit(setting.field)}
                  className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-all"
                >
                  {setting.is_set ? "Update" : "Set"}
                </button>
                {setting.source === "dashboard" && (
                  <button
                    onClick={() => handleAudioClearOverride(setting.field)}
                    disabled={saving}
                    className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 hover:border-red-200 transition-all"
                    title="Clear dashboard override and use .env value"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-gray-900" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {toastNode}
      {loadError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center justify-between gap-4">
          <span>{loadError}</span>
          <button type="button" onClick={() => loadKeys()} className="btn-secondary !py-1 !px-2 !text-xs shrink-0">
            Retry
          </button>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage API keys and platform configuration. Dashboard overrides take priority over{" "}
          <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">.env</code> values.
        </p>
      </div>

      {/* Auth Info */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
          Authentication
          <HelpTooltip text="Set AUTH_ENABLED=true and AUTH_PASSWORD in your .env to require login. Default is off." />
        </h2>
        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${authEnabled ? "bg-green-500" : "bg-gray-300"}`} />
            <span className="text-gray-600">
              Authentication: <strong>{authEnabled ? "Enabled" : "Disabled"}</strong>
            </span>
          </div>
          {username && (
            <div className="text-gray-500">
              Logged in as: <strong>{username}</strong>
            </div>
          )}
        </div>
      </div>

      {/* OpenAI data residency toggle */}
      {openaiUseEu && (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-1.5">
            OpenAI Data Residency
            <HelpTooltip text="Routes every OpenAI call (chat, realtime, STT, TTS, embeddings) through eu.api.openai.com instead of api.openai.com so customer content stays in the EEA region." />
          </h2>

          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-gray-900">
                  Use EU API endpoint (eu.api.openai.com)
                </span>
                <code className="text-[10px] text-gray-400 bg-gray-50 rounded px-1.5 py-0.5">
                  OPENAI_USE_EU
                </code>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    openaiUseEu.source === "dashboard"
                      ? "bg-blue-50 text-blue-700"
                      : openaiUseEu.source === "env"
                      ? "bg-green-50 text-green-700"
                      : "bg-gray-100 text-gray-500"
                  }`}
                >
                  {openaiUseEu.source === "dashboard"
                    ? "Dashboard"
                    : openaiUseEu.source === "env"
                    ? ".env"
                    : "Default"}
                </span>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                Keep customer content (prompts, audio, transcripts) inside the
                EEA region. Affects all OpenAI calls: chat, Realtime
                voice-to-voice, Whisper STT, TTS, and embeddings (RAG).
              </p>
              <p className="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-md px-3 py-2 leading-relaxed">
                <strong>Confirm with your institution first.</strong> The
                OpenAI project your API key belongs to needs data-residency
                enabled and a Modified Abuse Monitoring or Zero Data Retention
                amendment in place.{" "}
                <a
                  href="https://developers.openai.com/api/docs/guides/your-data"
                  target="_blank"
                  rel="noreferrer"
                  className="underline hover:text-amber-900"
                >
                  Read the OpenAI guide
                </a>
                .
              </p>
            </div>

            <div className="flex-shrink-0 pt-1">
              <button
                type="button"
                role="switch"
                aria-checked={openaiUseEu.enabled}
                disabled={flagSaving === "openai_use_eu"}
                onClick={() =>
                  handleFlagToggle("openai_use_eu", !openaiUseEu.enabled)
                }
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                  openaiUseEu.enabled ? "bg-gray-900" : "bg-gray-300"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                    openaiUseEu.enabled ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Interview audio storage */}
      <SettingsCollapsibleSection title="Interview audio storage">
        <div className="px-5 py-4 border-b border-gray-50">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-medium text-gray-900">Storage backend</span>
                <code className="text-[10px] text-gray-400 bg-gray-50 rounded px-1.5 py-0.5">
                  AUDIO_STORAGE_BACKEND
                </code>
              </div>
              <p className="text-xs text-gray-400">
                {AUDIO_STORAGE_INFO.audio_storage_backend.description}
              </p>
              <p className="mt-2 text-xs text-gray-500">
                Per-agent <strong>Store interview audio</strong> must still be enabled on each voice agent.
              </p>
            </div>
            <select
              value={audioBackend}
              disabled={saving}
              onChange={(e) =>
                handleAudioBackendChange(e.target.value as "local" | "s3")
              }
              className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-900 focus:border-gray-900 focus:ring-1 focus:ring-gray-900 outline-none"
            >
              <option value="local">Local disk</option>
              <option value="s3">S3 / compatible</option>
            </select>
          </div>
        </div>
        <div className="divide-y divide-gray-50">
          {audioStorage.map((s) => renderAudioStorageRow(s))}
        </div>
      </SettingsCollapsibleSection>

      {/* API Keys by Category */}
      {CATEGORIES.map((category, idx) => {
        const categoryKeys = keys.filter(
          (k) => KEY_INFO[k.field]?.category === category
        );
        if (categoryKeys.length === 0) return null;

        return (
          <SettingsCollapsibleSection
            key={category}
            title={category}
            defaultOpen={idx === 0}
            dataTour={idx === 0 ? "settings-keys" : undefined}
          >
            <div className="divide-y divide-gray-50">
              {categoryKeys.map((key) => {
                const info = KEY_INFO[key.field];
                const isEditing = key.field in editingFields;

                return (
                  <div key={key.field} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-gray-900">
                            {info?.label || key.field}
                          </span>
                          <code className="text-[10px] text-gray-400 bg-gray-50 rounded px-1.5 py-0.5">
                            {key.env_var}
                          </code>
                          {key.is_set && (
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                                key.source === "dashboard"
                                  ? "bg-blue-50 text-blue-700"
                                  : "bg-green-50 text-green-700"
                              }`}
                            >
                              {key.source === "dashboard" ? "Dashboard" : ".env"}
                            </span>
                          )}
                          {!key.is_set && (
                            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
                              Not set
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-400">{info?.description}</p>
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {key.is_set && !isEditing && (
                          <span className="text-xs text-gray-400 font-mono">
                            {key.masked_value}
                          </span>
                        )}

                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="password"
                              value={editingFields[key.field]}
                              onChange={(e) =>
                                setEditingFields((prev) => ({
                                  ...prev,
                                  [key.field]: e.target.value,
                                }))
                              }
                              placeholder="Enter new value…"
                              className="w-64 rounded-lg border border-gray-200 bg-gray-50/50 px-3 py-1.5 text-xs text-gray-900 focus:border-gray-900 focus:ring-1 focus:ring-gray-900 outline-none transition-all"
                              autoFocus
                            />
                            <button
                              onClick={() => handleSave(key.field)}
                              disabled={saving || !editingFields[key.field]}
                              className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50 transition-all"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => handleCancelEdit(key.field)}
                              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-all"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => handleEdit(key.field)}
                              className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-all"
                            >
                              {key.is_set ? "Update" : "Set"}
                            </button>
                            {key.source === "dashboard" && (
                              <button
                                onClick={() => handleClearOverride(key.field)}
                                disabled={saving}
                                className="rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 hover:border-red-200 transition-all"
                                title="Clear dashboard override and use .env value"
                              >
                                Clear
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </SettingsCollapsibleSection>
        );
      })}

      {/* Info */}
      <div className="rounded-xl bg-gray-50 border border-gray-200 p-5 text-sm text-gray-500">
        <p className="font-medium text-gray-700 mb-2">How it works</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>
            API keys and audio storage settings set here are stored in Redis and take priority over{" "}
            <code>.env</code> values.
          </li>
          <li>Changes take effect immediately — no restart required.</li>
          <li>Click "Clear" to remove a dashboard override and fall back to the <code>.env</code> value.</li>
          <li>
            Values are encrypted in transit but stored as plain text in Redis.
            For production, use <code>.env</code> files or a secrets manager.
          </li>
        </ul>
      </div>
    </div>
  );
}

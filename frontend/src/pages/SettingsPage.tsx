/**
 * OASIS — Settings page.
 *
 * Allows admins to view/update API keys at runtime without restarting.
 * Dashboard overrides take priority over .env values.
 */

import { useState, useEffect, useCallback } from "react";
import { settingsApi, type ApiKeyStatus } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import HelpTooltip from "../components/HelpTooltip";
import { useToast } from "../components/Toast";

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
    description: "Required for Gemini Live voice-to-voice models.",
    category: "AI Providers",
  },
  scaleway_secret_key: {
    label: "Scaleway Secret Key",
    description: "Required for Scaleway LLM, STT (Whisper), and Voxtral models.",
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
  gcp_project_id: {
    label: "GCP Project ID",
    description: "Required for GCP Vertex AI models.",
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

const CATEGORIES = ["AI Providers", "Self-Hosted", "Telephony"];

export default function SettingsPage() {
  const { authEnabled, username } = useAuth();
  const [toastNode, showToast] = useToast();
  const [keys, setKeys] = useState<ApiKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingFields, setEditingFields] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const loadKeys = useCallback(async () => {
    try {
      const res = await settingsApi.getKeys();
      setKeys(res.keys);
    } catch (err) {
      console.error("Failed to load API keys:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

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

      {/* API Keys by Category */}
      {CATEGORIES.map((category) => {
        const categoryKeys = keys.filter(
          (k) => KEY_INFO[k.field]?.category === category
        );
        if (categoryKeys.length === 0) return null;

        return (
          <div key={category} className="card">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-900">{category}</h2>
            </div>
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
          </div>
        );
      })}

      {/* Info */}
      <div className="rounded-xl bg-gray-50 border border-gray-200 p-5 text-sm text-gray-500">
        <p className="font-medium text-gray-700 mb-2">How it works</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>
            API keys set here are stored in Redis and take priority over <code>.env</code> values.
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

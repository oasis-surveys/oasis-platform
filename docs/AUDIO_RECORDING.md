# Voice interview audio recording

OASIS can save raw audio from **web voice** interviews (modular STT/LLM/TTS and voice-to-voice). It does not record Twilio phone calls or text chat.

Recording is **off by default**. You turn on storage for the server, then enable **Store interview audio** on each voice agent that should save files.

---

## Turning it on

1. **Server storage** (Settings → Interview audio storage, or `.env` on the host):

   ```env
   AUDIO_STORAGE_BACKEND=local
   AUDIO_STORAGE_LOCAL_PATH=/data/oasis-recordings
   ```

   Dashboard values in Redis override `.env` (same pattern as API keys). Changes apply without a restart.

2. **Per agent**: open the agent → Interview Settings → **Store interview audio** → Save.

3. Run a new web voice interview. Files are written when the session ends (disconnect, timeout, or admin terminate).

If storage is not configured, the agent toggle has no effect and `audio_recording_status` on the session will be `failed`.

---

## What gets written

Each recorded session produces **two mono WAV files** plus a manifest:

| File | Contents |
|------|----------|
| `session_user.wav` | Participant microphone for the call. Capture pauses while the agent is speaking so speaker playback is not mixed in. |
| `session_agent.wav` | All agent audio for the call (TTS or realtime model output). |
| `manifest.json` | Metadata: paths, sample rates, durations, errors. |

- Format: 16-bit PCM in a standard WAV container.
- Sample rate follows the pipeline (often 16 kHz for the participant, 24 kHz for the agent in voice-to-voice).
- The **transcript in PostgreSQL stays turn-based** (sequence numbers per line). Audio is **not** split by transcript turn.

`recording_status` on the session row is set when the interview ends: `complete`, `partial` (some files or manifest errors), or `failed`.

---

## Path layout

Objects share one prefix tree on disk or in the bucket:

```text
{AUDIO_S3_PREFIX}/   # omitted for local; see below
  studies/{study_id}/
    agents/{agent_id}/
      participants/{participant_id}/
        sessions/{session_id}/
          manifest.json
          session_user.wav
          session_agent.wav
```

`participant_id` is sanitized for path safety (unsafe characters become `_`). Anonymous participants use `anonymous`.

**Local:** files live under `AUDIO_STORAGE_LOCAL_PATH`. In Docker Compose the default mount is `./data/recordings` on the host → `/data/oasis-recordings` in the backend container.

**S3:** the full object key is `{AUDIO_S3_PREFIX}/{path above}`. Example with prefix `oasis-recordings`:

```text
s3://my-bucket/oasis-recordings/studies/859f9e97-.../agents/7dcdace1-.../participants/P001/sessions/c8420f20-.../session_user.wav
```

The session row stores a `storage_uri` such as `local:///data/oasis-recordings/studies/...` or `s3://my-bucket/oasis-recordings/studies/...` for reference.

---

## manifest.json

Written last. Example:

```json
{
  "session_id": "c8420f20-8b26-40e2-8ab7-195b19c79b93",
  "pipeline_type": "modular",
  "recording_mode": "session",
  "recorded_at": "2026-05-21T16:50:57.276258+00:00",
  "turns": [
    {
      "sequence": 1,
      "role": "user",
      "filename": "session_user.wav",
      "storage_key": "studies/.../session_user.wav",
      "sample_rate": 16000,
      "duration_ms": 8864,
      "content_preview": "Session recording"
    },
    {
      "sequence": 2,
      "role": "agent",
      "filename": "session_agent.wav",
      "storage_key": "studies/.../session_agent.wav",
      "sample_rate": 24000,
      "duration_ms": 25950,
      "content_preview": "Session recording"
    }
  ],
  "errors": []
}
```

The `turns` array lists the two session files (not per-transcript-turn clips). Non-empty `errors` means something failed during write; check backend logs.

---

## S3 and AWS

Set **Storage backend** to **S3 / compatible** in the dashboard, or in `.env`:

```env
AUDIO_STORAGE_BACKEND=s3
AUDIO_S3_BUCKET=your-bucket-name
AUDIO_S3_PREFIX=oasis-recordings
AUDIO_S3_REGION=eu-west-1
AUDIO_S3_ACCESS_KEY_ID=...
AUDIO_S3_SECRET_ACCESS_KEY=...
# Optional: MinIO, Wasabi, etc.
# AUDIO_S3_ENDPOINT_URL=https://...
```

The backend uses the AWS SDK (`boto3`) with SigV4. Leave `AUDIO_S3_ENDPOINT_URL` empty for AWS S3.

### Bucket setup

- Use a **dedicated bucket** (or a dedicated prefix) for interview audio, separate from public assets.
- **Block all public access** on the bucket. OASIS does not set public ACLs; downloads go through the authenticated API, not anonymous S3 URLs.
- Enable **default encryption** (SSE-S3 or SSE-KMS). If you use KMS, the IAM principal needs `kms:Decrypt` / `kms:GenerateDataKey` on that key.
- Restrict **bucket policy** to the deployment account/VPC if you can (e.g. `aws:SourceVpce` for an S3 gateway endpoint).
- Add a **lifecycle rule** if retention should expire objects after N days (not handled inside OASIS).

### IAM policy (least privilege)

Scope to the prefix OASIS uses. Replace bucket name and prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "OasisAudioWriteRead",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name",
        "arn:aws:s3:::your-bucket-name/oasis-recordings/*"
      ],
      "Condition": {
        "StringLike": {
          "s3:prefix": ["oasis-recordings/*"]
        }
      }
    }
  ]
}
```

On EC2 or ECS you can attach this policy to an **instance/task role** and leave `AUDIO_S3_ACCESS_KEY_ID` / `AUDIO_S3_SECRET_ACCESS_KEY` empty only if you extend the app to use the default credential chain (today OASIS expects explicit keys in `.env` or the dashboard). For production, prefer **long-lived keys in `.env` or a secrets manager** on the host, not pasted into the dashboard on a shared machine.

### Credentials and the dashboard

S3 keys set under Settings are stored in **Redis as plain text**, like other API keys. That is fine for a local demo; on a shared server use `.env` or IAM roles and avoid putting secrets in Redis.

Do not commit `.env` or grant `s3:*` on `*`. Rotate keys if the dashboard was used on an untrusted machine.

### Other S3-compatible stores

Same variables; set `AUDIO_S3_ENDPOINT_URL` to the vendor endpoint and use that vendor's region and signing setup.

---

## API (authenticated)

Same auth as the rest of the admin API (session cookie when `AUTH_ENABLED=true`).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}/audio` | JSON manifest |
| `GET` | `/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}/audio/{filename}` | Download `session_user.wav` or `session_agent.wav` |

The session detail page in the dashboard calls these endpoints when `audio_recording_enabled` is true.

---

## Consent and retention

Raw audio is identifiable data in most jurisdictions. Use it only with consent wording that covers voice recording, a defined retention period, and access controls on the bucket or disk. The transcript alone may be enough for some studies; audio is optional per agent for that reason.

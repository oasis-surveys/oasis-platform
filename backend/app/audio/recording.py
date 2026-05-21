"""
Pipecat processors and session manager for voice interview audio recording.

Each session produces two files: session_user.wav and session_agent.wav.
"""

from __future__ import annotations

import io
import json
import wave
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from loguru import logger

from pipecat.frames.frames import (
    AudioRawFrame,
    BotStartedSpeakingFrame,
    Frame,
    OutputAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.audio.storage import AudioStorageBackend, build_session_prefix

DEFAULT_SAMPLE_RATE = 16000


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class AudioRecordingManager:
    """
    Accumulates participant and agent PCM for the full session.

    Participant mic is recorded except while the agent is speaking (avoids
    speaker bleed). Files are written once when the session ends.
    """

    def __init__(
        self,
        storage: AudioStorageBackend,
        *,
        session_prefix: str,
        session_id: UUID,
        pipeline_type: str,
    ):
        self._storage = storage
        self._prefix = session_prefix
        self._session_id = str(session_id)
        self._pipeline_type = pipeline_type
        self._user_pcm = bytearray()
        self._agent_pcm = bytearray()
        self._user_sample_rate = DEFAULT_SAMPLE_RATE
        self._agent_sample_rate = DEFAULT_SAMPLE_RATE
        self._files: list[dict] = []
        self._errors: list[str] = []
        self._finalized = False
        self._user_capturing = True

    @property
    def storage_uri(self) -> str:
        return self._storage.uri_for_prefix(self._prefix)

    def _append_pcm(self, buffer: bytearray, frame: AudioRawFrame):
        if frame.audio:
            buffer.extend(frame.audio)
        rate = getattr(frame, "sample_rate", None) or DEFAULT_SAMPLE_RATE
        return rate

    def resume_user_capture(self):
        """Resume appending participant mic (does not clear accumulated audio)."""
        self._user_capturing = True

    def stop_user_capture(self):
        """Pause mic capture while the agent is speaking."""
        self._user_capturing = False

    def on_agent_speech_start(self):
        self.stop_user_capture()

    def append_user_frame(self, frame: AudioRawFrame):
        if not self._user_capturing:
            return
        rate = self._append_pcm(self._user_pcm, frame)
        if rate:
            self._user_sample_rate = rate

    def append_agent_frame(self, frame: OutputAudioRawFrame):
        rate = self._append_pcm(self._agent_pcm, frame)
        if rate:
            self._agent_sample_rate = rate

    async def on_agent_tts_started(self):
        self.on_agent_speech_start()

    async def on_agent_tts_stopped(self):
        """Agent finished a segment — resume participant mic capture."""
        self.resume_user_capture()

    async def _write_session_wav(self, role: str) -> None:
        if role == "user":
            pcm = bytes(self._user_pcm)
            sample_rate = self._user_sample_rate
        else:
            pcm = bytes(self._agent_pcm)
            sample_rate = self._agent_sample_rate

        if not pcm:
            return

        filename = f"session_{role}.wav"
        key = f"{self._prefix}/{filename}"
        try:
            wav_bytes = _pcm_to_wav(pcm, sample_rate)
            await self._storage.write_bytes(key, wav_bytes)
            self._files.append(
                {
                    "sequence": 1 if role == "user" else 2,
                    "role": role,
                    "filename": filename,
                    "storage_key": key,
                    "sample_rate": sample_rate,
                    "duration_ms": int(len(pcm) / 2 / sample_rate * 1000),
                    "content_preview": "Session recording",
                }
            )
        except Exception as exc:
            msg = f"Failed to write {filename}: {exc}"
            logger.error(msg)
            self._errors.append(msg)

    async def finalize_session(self) -> str:
        """
        Write session WAVs and manifest.json.
        Returns: complete | partial | failed
        """
        if self._finalized:
            return "complete" if not self._errors else "partial"
        self._finalized = True

        await self._write_session_wav("user")
        await self._write_session_wav("agent")

        manifest = {
            "session_id": self._session_id,
            "pipeline_type": self._pipeline_type,
            "recording_mode": "session",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "turns": self._files,
            "errors": self._errors,
        }
        try:
            await self._storage.write_json(
                f"{self._prefix}/manifest.json",
                json.dumps(manifest, indent=2).encode("utf-8"),
            )
        except Exception as exc:
            logger.error(f"Failed to write audio manifest: {exc}")
            self._errors.append(str(exc))

        if self._errors and self._files:
            return "partial"
        if self._errors:
            return "failed"
        if self._files:
            return "complete"
        return "failed"


class UserAudioTap(FrameProcessor):
    """Capture inbound microphone PCM (place after transport.input())."""

    def __init__(self, manager: Optional[AudioRecordingManager], **kwargs):
        super().__init__(**kwargs)
        self._manager = manager

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self._manager and isinstance(frame, AudioRawFrame) and not isinstance(
            frame, OutputAudioRawFrame
        ):
            self._manager.append_user_frame(frame)
        await self.push_frame(frame, direction)


class SpeakingEventTap(FrameProcessor):
    """Resume participant capture on speech-start events from VAD / Realtime."""

    def __init__(self, manager: Optional[AudioRecordingManager], **kwargs):
        super().__init__(**kwargs)
        self._manager = manager

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self._manager:
            if isinstance(frame, UserStartedSpeakingFrame):
                self._manager.resume_user_capture()
            elif isinstance(frame, (BotStartedSpeakingFrame, TTSStartedFrame)):
                self._manager.on_agent_speech_start()
        await self.push_frame(frame, direction)


class AgentAudioTap(FrameProcessor):
    """Capture outbound agent PCM (place immediately after TTS or V2V LLM)."""

    def __init__(self, manager: Optional[AudioRecordingManager], **kwargs):
        super().__init__(**kwargs)
        self._manager = manager

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self._manager:
            if isinstance(frame, OutputAudioRawFrame):
                self._manager.append_agent_frame(frame)
            elif isinstance(frame, TTSStartedFrame):
                await self._manager.on_agent_tts_started()
            elif isinstance(frame, TTSStoppedFrame):
                await self._manager.on_agent_tts_stopped()
        await self.push_frame(frame, direction)

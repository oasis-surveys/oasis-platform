"""Tests for voice interview audio recording helpers."""

import io
import wave

import pytest

from app.audio.recording import _pcm_to_wav, AudioRecordingManager
from app.audio.storage import LocalAudioStorage, sanitize_path_segment, build_session_prefix
from uuid import uuid4


def test_sanitize_path_segment():
    assert sanitize_path_segment("P-001") == "P-001"
    assert sanitize_path_segment("  ") == "anonymous"
    assert "/" not in sanitize_path_segment("a/b\\c")


def test_build_session_prefix():
    sid = uuid4()
    prefix = build_session_prefix(
        study_id=uuid4(),
        agent_id=uuid4(),
        participant_id="P001",
        session_id=sid,
    )
    assert f"sessions/{sid}" in prefix
    assert "participants/P001" in prefix


def test_pcm_to_wav_roundtrip():
    pcm = b"\x00\x01" * 800
    wav_bytes = _pcm_to_wav(pcm, 16000)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert len(wf.readframes(wf.getnframes())) == len(pcm)


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline_type", ["modular", "voice_to_voice"])
async def test_session_recording_writes_files(tmp_path, pipeline_type):
    storage = LocalAudioStorage(str(tmp_path))
    session_id = uuid4()
    prefix = build_session_prefix(
        study_id=uuid4(),
        agent_id=uuid4(),
        participant_id="subj1",
        session_id=session_id,
    )
    mgr = AudioRecordingManager(
        storage,
        session_prefix=prefix,
        session_id=session_id,
        pipeline_type=pipeline_type,
    )
    mgr._user_pcm.extend(b"\x00\x00" * 100)
    mgr._agent_pcm.extend(b"\x01\x00" * 100)

    status = await mgr.finalize_session()
    assert status == "complete"
    assert (tmp_path / prefix / "session_user.wav").exists()
    assert (tmp_path / prefix / "session_agent.wav").exists()
    manifest = (tmp_path / prefix / "manifest.json").read_text()
    assert '"recording_mode": "session"' in manifest
    assert len(mgr._files) == 2


@pytest.mark.asyncio
async def test_user_capture_paused_during_agent_speech():
    from pipecat.frames.frames import InputAudioRawFrame

    storage = LocalAudioStorage("/tmp/unused")
    mgr = AudioRecordingManager(
        storage,
        session_prefix="test/prefix",
        session_id=uuid4(),
        pipeline_type="modular",
    )
    chunk = InputAudioRawFrame(audio=b"\x00\x00" * 100, sample_rate=16000, num_channels=1)
    mgr.append_user_frame(chunk)
    mgr.on_agent_speech_start()
    blocked = InputAudioRawFrame(audio=b"\xff\xff" * 50, sample_rate=16000, num_channels=1)
    mgr.append_user_frame(blocked)
    assert len(mgr._user_pcm) == 200
    mgr.resume_user_capture()
    active = InputAudioRawFrame(audio=b"\x01\x00" * 50, sample_rate=16000, num_channels=1)
    mgr.append_user_frame(active)
    assert len(mgr._user_pcm) == 300


@pytest.mark.asyncio
async def test_agent_tts_stopped_resumes_user_capture():
    storage = LocalAudioStorage("/tmp/unused")
    mgr = AudioRecordingManager(
        storage,
        session_prefix="test/prefix",
        session_id=uuid4(),
        pipeline_type="modular",
    )
    mgr.on_agent_speech_start()
    assert mgr._user_capturing is False
    await mgr.on_agent_tts_stopped()
    assert mgr._user_capturing is True

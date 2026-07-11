"""Live checks for configured providers."""

from __future__ import annotations

import asyncio
import re
import struct
import time
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger

from app.config import settings
from app.providers.availability import get_effective_provider_setting
from app.providers.catalog import (
    DEFAULTS,
    get_catalog_entry,
    get_configured_catalog,
    resolve_llm_api_kind,
)

_MIN_COMPLETION_TOKENS = 32

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I),
    re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9._-]+", re.I),
    re.compile(r"([?&]key=)[^&\s]+", re.I),
)


def _sanitize_error(msg: str | None) -> str | None:
    if not msg:
        return None
    out = str(msg)
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    if len(out) > 300:
        out = out[:297] + "..."
    return out


def _mini_wav_bytes(*, duration_ms: int = 200, sample_rate: int = 16000) -> bytes:
    """Tiny mono 16-bit PCM WAV (near-silence) for STT probes."""
    n_samples = int(sample_rate * duration_ms / 1000)
    data = b"\x00\x01" * n_samples
    byte_rate = sample_rate * 2
    block_align = 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        len(data),
    )
    return header + data


@dataclass
class SmokeProbeResult:
    category: str
    provider: str
    model: str
    endpoint: str
    ok: bool
    latency_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["error"] = _sanitize_error(d.get("error"))
        return d


async def _get_key(field: str) -> str:
    return await get_effective_provider_setting(field)


async def _openai_api_base() -> str | None:
    from app.api.settings import get_effective_flag

    return (
        "https://eu.api.openai.com/v1"
        if await get_effective_flag("openai_use_eu")
        else None
    )


async def _openai_realtime_url() -> str:
    from app.api.settings import get_effective_flag

    return (
        "wss://eu.api.openai.com/v1/realtime"
        if await get_effective_flag("openai_use_eu")
        else "wss://api.openai.com/v1/realtime"
    )


def _openai_compatible_endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


async def _probe_llm(model: str) -> SmokeProbeResult:
    entry = get_catalog_entry(model)
    provider = entry.provider if entry else model.split("/", 1)[0]
    api_kind = resolve_llm_api_kind(model) or "chat_completions"
    started = time.perf_counter()
    endpoint = api_kind

    try:
        if api_kind == "responses":
            from app.api.text_chat import _call_openai_responses

            api_key = await _get_key("openai_api_key")
            base = await _openai_api_base()
            endpoint = f"{base or 'https://api.openai.com/v1'}/responses"
            await _call_openai_responses(
                [{"role": "user", "content": "Reply with exactly: ok"}],
                model,
                api_key,
                base,
            )
        elif model.startswith("scaleway/"):
            import litellm

            scw_key = await _get_key("scaleway_secret_key")
            endpoint = "https://api.scaleway.ai/v1/chat/completions"
            await litellm.acompletion(
                model=f"openai/{model.split('/', 1)[1]}",
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                api_key=scw_key,
                api_base="https://api.scaleway.ai/v1",
                max_tokens=_MIN_COMPLETION_TOKENS,
            )
        elif model.startswith("anthropic/"):
            import litellm

            endpoint = "https://api.anthropic.com/v1/messages"
            await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                api_key=await _get_key("anthropic_api_key"),
                max_tokens=_MIN_COMPLETION_TOKENS,
            )
        elif model.startswith("google/"):
            import litellm

            google_model = model.split("/", 1)[1]
            endpoint = "generativelanguage.googleapis.com"
            await litellm.acompletion(
                model=f"gemini/{google_model}",
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                api_key=await _get_key("google_api_key"),
                max_tokens=_MIN_COMPLETION_TOKENS,
            )
        elif model.startswith("custom/"):
            import litellm

            custom_model = model.split("/", 1)[1]
            base_url = await _get_key("openai_compatible_llm_url")
            endpoint = base_url or "custom"
            await litellm.acompletion(
                model=f"openai/{custom_model}",
                messages=[{"role": "user", "content": "Reply with exactly: ok"}],
                api_base=base_url,
                api_key=await _get_key("openai_compatible_llm_api_key") or "not-needed",
                max_tokens=_MIN_COMPLETION_TOKENS,
            )
        else:
            import litellm

            openai_model = model.removeprefix("openai/")
            kwargs: dict = {
                "model": openai_model,
                "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                "api_key": await _get_key("openai_api_key"),
                "max_completion_tokens": _MIN_COMPLETION_TOKENS
                if openai_model.startswith(("gpt-5", "o1", "o3", "o4"))
                else None,
                "max_tokens": _MIN_COMPLETION_TOKENS
                if not openai_model.startswith(("gpt-5", "o1", "o3", "o4"))
                else None,
            }
            base = await _openai_api_base()
            endpoint = f"{base or 'https://api.openai.com/v1'}/chat/completions"
            if base:
                kwargs["api_base"] = base
            await litellm.acompletion(**{k: v for k, v in kwargs.items() if v is not None})

        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("llm", provider, model, endpoint, True, latency)
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult(
            "llm", provider, model, endpoint, False, latency, str(exc)
        )


async def _probe_stt(provider: str, model: str) -> SmokeProbeResult:
    started = time.perf_counter()
    wav = _mini_wav_bytes()
    endpoint = ""

    try:
        if provider == "openai" and model == "gpt-realtime-whisper":
            import websockets

            api_key = await _get_key("openai_api_key")
            url = await _openai_realtime_url()
            endpoint = url
            headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}
            async with websockets.connect(
                f"{url}?model={model}",
                additional_headers=headers,
                open_timeout=15,
                close_timeout=5,
            ) as ws:
                await asyncio.wait_for(ws.recv(), timeout=10)
        elif provider == "openai":
            import httpx

            api_key = await _get_key("openai_api_key")
            base = await _openai_api_base() or "https://api.openai.com/v1"
            endpoint = f"{base}/audio/transcriptions"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("probe.wav", wav, "audio/wav")},
                    data={"model": model, "language": "en"},
                )
                resp.raise_for_status()
        elif provider == "deepgram":
            import httpx

            api_key = await _get_key("deepgram_api_key")
            endpoint = "https://api.deepgram.com/v1/listen"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{endpoint}?model={model}&language=en",
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "audio/wav",
                    },
                    content=wav,
                )
                resp.raise_for_status()
        elif provider == "scaleway":
            import httpx

            api_key = await _get_key("scaleway_secret_key")
            endpoint = f"{settings.scaleway_api_url}/audio/transcriptions"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("probe.wav", wav, "audio/wav")},
                    data={"model": model or "whisper-large-v3"},
                )
                resp.raise_for_status()
        elif provider == "self_hosted":
            import httpx

            base_url = await _get_key("self_hosted_stt_url")
            api_key = await _get_key("self_hosted_stt_api_key") or "not-needed"
            endpoint = _openai_compatible_endpoint(
                base_url,
                "audio/transcriptions",
            )
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("probe.wav", wav, "audio/wav")},
                    data={"model": model, "language": "en"},
                )
                resp.raise_for_status()
        else:
            raise ValueError(f"Unsupported STT provider: {provider}")

        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("stt", provider, model, endpoint, True, latency)
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("stt", provider, model, endpoint or provider, False, latency, str(exc))


async def _probe_tts(provider: str, model: str | None, voice: str) -> SmokeProbeResult:
    started = time.perf_counter()
    endpoint = ""

    try:
        if provider == "openai":
            import httpx

            api_key = await _get_key("openai_api_key")
            base = await _openai_api_base() or "https://api.openai.com/v1"
            endpoint = f"{base}/audio/speech"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model or DEFAULTS["tts_model"],
                        "input": "ok",
                        "voice": voice,
                    },
                )
                resp.raise_for_status()
        elif provider == "elevenlabs":
            import httpx

            from app.pipeline.runner import _resolve_elevenlabs_voice

            api_key = await _get_key("elevenlabs_api_key")
            voice_id = _resolve_elevenlabs_voice(voice)
            endpoint = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                    json={"text": "ok", "model_id": "eleven_multilingual_v2"},
                )
                resp.raise_for_status()
        elif provider == "cartesia":
            import httpx

            api_key = await _get_key("cartesia_api_key")
            endpoint = "https://api.cartesia.ai/tts/bytes"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={
                        "X-API-Key": api_key,
                        "Cartesia-Version": "2024-06-10",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model_id": "sonic-2",
                        "transcript": "ok",
                        "voice": {"mode": "id", "id": voice},
                        "output_format": {"container": "wav", "encoding": "pcm_f32le", "sample_rate": 44100},
                    },
                )
                resp.raise_for_status()
        elif provider == "self_hosted":
            import httpx

            base_url = await _get_key("self_hosted_tts_url")
            api_key = await _get_key("self_hosted_tts_api_key") or "not-needed"
            endpoint = _openai_compatible_endpoint(base_url, "audio/speech")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model or DEFAULTS["self_hosted_tts_model"],
                        "input": "ok",
                        "voice": voice,
                    },
                )
                resp.raise_for_status()
        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("tts", provider, model or voice, endpoint, True, latency)
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("tts", provider, model or voice, endpoint or provider, False, latency, str(exc))


async def _probe_v2v(model: str) -> SmokeProbeResult:
    entry = get_catalog_entry(model)
    provider = entry.provider if entry else model.split("/", 1)[0]
    api_kind = resolve_llm_api_kind(model) or "realtime"
    started = time.perf_counter()
    endpoint = ""

    try:
        if api_kind == "realtime":
            import websockets

            api_key = await _get_key("openai_api_key")
            model_id = model.split("/", 1)[1]
            url = await _openai_realtime_url()
            endpoint = url
            headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}
            async with websockets.connect(
                f"{url}?model={model_id}",
                additional_headers=headers,
                open_timeout=15,
                close_timeout=5,
            ) as ws:
                await asyncio.wait_for(ws.recv(), timeout=10)
        elif api_kind == "gemini_live":
            import websockets

            api_key = await _get_key("google_api_key")
            model_id = model.split("/", 1)[1]
            endpoint = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
            url = f"{endpoint}?key={api_key}"
            async with websockets.connect(url, open_timeout=15, close_timeout=5) as ws:
                await ws.send(
                    '{"setup":{"model":"models/'
                    + model_id
                    + '","generationConfig":{"responseModalities":["AUDIO"]}}}'
                )
                await asyncio.wait_for(ws.recv(), timeout=10)
        else:
            raise ValueError(f"Unsupported V2V api_kind: {api_kind}")

        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("v2v", provider, model, endpoint, True, latency)
    except Exception as exc:
        latency = (time.perf_counter() - started) * 1000
        return SmokeProbeResult("v2v", provider, model, endpoint or api_kind, False, latency, str(exc))


def _tts_probe_config(provider: dict, catalog: dict) -> tuple[str | None, str]:
    voice = DEFAULTS["tts_voice"]
    provider_name = provider["value"]
    provider_voices = catalog["voices"].get(provider_name, [])
    if provider_voices:
        voice = provider_voices[0]["value"]
    model = provider["models"][0]["value"] if provider["models"] else None
    return model, voice


async def run_configured_smoke_tests(*, live: bool = True) -> dict[str, Any]:
    """Probe every model in the configured catalog."""
    catalog = await get_configured_catalog()
    probes: list[SmokeProbeResult] = []

    if not live:
        for m in catalog["llm_modular"]:
            probes.append(SmokeProbeResult("llm", m["provider"], m["value"], m["api_kind"], True, 0))
        for m in catalog["llm_v2v"]:
            probes.append(SmokeProbeResult("v2v", m["provider"], m["value"], m["api_kind"], True, 0))
        for sp in catalog["stt_providers"]:
            for sm in sp["models"]:
                probes.append(SmokeProbeResult("stt", sp["value"], sm["value"], sp["value"], True, 0))
        for tp in catalog["tts_providers"]:
            model, voice = _tts_probe_config(tp, catalog)
            probes.append(SmokeProbeResult("tts", tp["value"], model or voice, tp["value"], True, 0))
        return {
            "live": False,
            "total": len(probes),
            "passed": len(probes),
            "failed": 0,
            "results": [p.to_dict() for p in probes],
        }

    semaphore = asyncio.Semaphore(5)

    async def run_probe(probe):
        async with semaphore:
            return await probe

    tasks = []

    for m in catalog["llm_modular"]:
        tasks.append(run_probe(_probe_llm(m["value"])))
    for m in catalog["llm_v2v"]:
        tasks.append(run_probe(_probe_v2v(m["value"])))
    for sp in catalog["stt_providers"]:
        for sm in sp["models"]:
            tasks.append(run_probe(_probe_stt(sp["value"], sm["value"])))
    for tp in catalog["tts_providers"]:
        model, voice = _tts_probe_config(tp, catalog)
        tasks.append(run_probe(_probe_tts(tp["value"], model, voice)))

    logger.info(f"Provider smoke: running {len(tasks)} live probes")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for raw in results:
        if isinstance(raw, SmokeProbeResult):
            probes.append(raw)
        elif isinstance(raw, Exception):
            probes.append(
                SmokeProbeResult("unknown", "unknown", "unknown", "", False, None, str(raw))
            )

    passed = sum(1 for p in probes if p.ok)
    return {
        "live": True,
        "total": len(probes),
        "passed": passed,
        "failed": len(probes) - passed,
        "results": [p.to_dict() for p in probes],
    }

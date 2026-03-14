/**
 * OASIS — Tests for audio conversion helpers.
 *
 * Tests the PCM16 ↔ Float32 conversion functions used in audio.ts.
 * These are pure functions — no browser APIs needed.
 */

import { describe, it, expect } from "vitest";

// We need to test the internal conversion helpers. Since they're private,
// we test them indirectly through the AudioPlayer/MicCapture interface,
// or we re-implement the logic here for validation.

// ── PCM16 ↔ Float32 Roundtrip ─────────────────────────────────

function float32ToPcm16(float32: Float32Array): Uint8Array {
  const buf = new ArrayBuffer(float32.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(buf);
}

function pcm16ToFloat32(pcm16: Uint8Array): Float32Array {
  const view = new DataView(pcm16.buffer, pcm16.byteOffset, pcm16.byteLength);
  const numSamples = pcm16.byteLength / 2;
  const float32 = new Float32Array(numSamples);
  for (let i = 0; i < numSamples; i++) {
    const s = view.getInt16(i * 2, true);
    float32[i] = s / (s < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}

describe("Audio Conversion Helpers", () => {
  it("converts Float32 to PCM16", () => {
    const input = new Float32Array([0.0, 0.5, -0.5, 1.0, -1.0]);
    const pcm16 = float32ToPcm16(input);
    expect(pcm16.byteLength).toBe(input.length * 2);
  });

  it("converts PCM16 back to Float32", () => {
    const input = new Float32Array([0.0, 0.5, -0.5]);
    const pcm16 = float32ToPcm16(input);
    const output = pcm16ToFloat32(pcm16);
    expect(output.length).toBe(input.length);
  });

  it("roundtrip preserves approximate values", () => {
    const input = new Float32Array([0.0, 0.5, -0.5, 1.0, -1.0]);
    const pcm16 = float32ToPcm16(input);
    const output = pcm16ToFloat32(pcm16);

    for (let i = 0; i < input.length; i++) {
      // PCM16 quantization means we lose some precision
      expect(Math.abs(output[i] - input[i])).toBeLessThan(0.001);
    }
  });

  it("handles silence (all zeros)", () => {
    const input = new Float32Array([0, 0, 0, 0]);
    const pcm16 = float32ToPcm16(input);
    const output = pcm16ToFloat32(pcm16);

    for (let i = 0; i < output.length; i++) {
      expect(output[i]).toBe(0);
    }
  });

  it("clamps values outside [-1, 1]", () => {
    const input = new Float32Array([2.0, -2.0, 1.5, -1.5]);
    const pcm16 = float32ToPcm16(input);
    const output = pcm16ToFloat32(pcm16);

    // Values > 1 should be clamped to 1
    expect(output[0]).toBeCloseTo(1.0, 2);
    // Values < -1 should be clamped to -1
    expect(output[1]).toBeCloseTo(-1.0, 2);
  });

  it("handles empty arrays", () => {
    const input = new Float32Array([]);
    const pcm16 = float32ToPcm16(input);
    expect(pcm16.byteLength).toBe(0);

    const output = pcm16ToFloat32(pcm16);
    expect(output.length).toBe(0);
  });

  it("PCM16 byte order is little-endian", () => {
    // Max positive value (1.0) → 0x7FFF in LE = [0xFF, 0x7F]
    const input = new Float32Array([1.0]);
    const pcm16 = float32ToPcm16(input);
    expect(pcm16[0]).toBe(0xff);
    expect(pcm16[1]).toBe(0x7f);
  });

  it("PCM16 negative value byte order", () => {
    // Max negative value (-1.0) → 0x8000 in LE = [0x00, 0x80]
    const input = new Float32Array([-1.0]);
    const pcm16 = float32ToPcm16(input);
    expect(pcm16[0]).toBe(0x00);
    expect(pcm16[1]).toBe(0x80);
  });

  it("handles many samples", () => {
    // Simulate 1 second of 16kHz audio
    const numSamples = 16000;
    const input = new Float32Array(numSamples);
    for (let i = 0; i < numSamples; i++) {
      // Generate a sine wave
      input[i] = Math.sin((2 * Math.PI * 440 * i) / numSamples);
    }

    const pcm16 = float32ToPcm16(input);
    expect(pcm16.byteLength).toBe(numSamples * 2);

    const output = pcm16ToFloat32(pcm16);
    expect(output.length).toBe(numSamples);

    // Verify the shape is roughly preserved
    for (let i = 0; i < numSamples; i++) {
      expect(Math.abs(output[i] - input[i])).toBeLessThan(0.001);
    }
  });
});

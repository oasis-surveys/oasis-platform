/**
 * OASIS — Lightweight protobuf encoder/decoder for Pipecat frames.
 *
 * Mirrors the pipecat `frames.proto` schema used by ProtobufFrameSerializer.
 * Uses protobufjs to stay compatible with the server's binary format.
 */

import protobuf from "protobufjs";

// ── Proto schema (matches pipecat/frames/protobufs/frames.proto) ──

const protoJSON = {
  nested: {
    pipecat: {
      nested: {
        TextFrame: {
          fields: {
            id: { type: "uint64", id: 1 },
            name: { type: "string", id: 2 },
            text: { type: "string", id: 3 },
          },
        },
        AudioRawFrame: {
          fields: {
            id: { type: "uint64", id: 1 },
            name: { type: "string", id: 2 },
            audio: { type: "bytes", id: 3 },
            sample_rate: { type: "uint32", id: 4 },
            num_channels: { type: "uint32", id: 5 },
            pts: { type: "uint64", id: 6 },
          },
        },
        TranscriptionFrame: {
          fields: {
            id: { type: "uint64", id: 1 },
            name: { type: "string", id: 2 },
            text: { type: "string", id: 3 },
            user_id: { type: "string", id: 4 },
            timestamp: { type: "string", id: 5 },
          },
        },
        MessageFrame: {
          fields: {
            data: { type: "string", id: 1 },
          },
        },
        Frame: {
          oneofs: {
            frame: {
              oneof: ["text", "audio", "transcription", "message"],
            },
          },
          fields: {
            text: { type: "TextFrame", id: 1 },
            audio: { type: "AudioRawFrame", id: 2 },
            transcription: { type: "TranscriptionFrame", id: 3 },
            message: { type: "MessageFrame", id: 4 },
          },
        },
      },
    },
  },
};

const root = protobuf.Root.fromJSON(protoJSON);
const Frame = root.lookupType("pipecat.Frame");

// ── Encode helpers ──────────────────────────────────────────────

/**
 * Encode a raw PCM16 audio chunk into a pipecat Frame (protobuf bytes).
 */
export function encodeAudioFrame(
  pcm16: Uint8Array,
  sampleRate: number = 16000,
  numChannels: number = 1
): Uint8Array {
  const msg = Frame.create({
    audio: {
      audio: pcm16,
      sample_rate: sampleRate,
      num_channels: numChannels,
    },
  });
  return Frame.encode(msg).finish();
}

// ── Decode helpers ──────────────────────────────────────────────

export type DecodedFrame =
  | { type: "audio"; audio: Uint8Array; sampleRate: number; numChannels: number }
  | { type: "text"; text: string }
  | { type: "transcription"; text: string; userId: string; timestamp: string }
  | { type: "message"; data: string }
  | { type: "unknown" };

/**
 * Decode a pipecat Frame from protobuf bytes.
 */
export function decodeFrame(data: Uint8Array): DecodedFrame {
  const frame = Frame.decode(data) as any;

  if (frame.audio) {
    return {
      type: "audio",
      audio: frame.audio.audio instanceof Uint8Array
        ? frame.audio.audio
        : new Uint8Array(frame.audio.audio),
      sampleRate: frame.audio.sample_rate || 16000,
      numChannels: frame.audio.num_channels || 1,
    };
  }

  if (frame.text) {
    return { type: "text", text: frame.text.text || "" };
  }

  if (frame.transcription) {
    return {
      type: "transcription",
      text: frame.transcription.text || "",
      userId: frame.transcription.user_id || "",
      timestamp: frame.transcription.timestamp || "",
    };
  }

  if (frame.message) {
    return { type: "message", data: frame.message.data || "" };
  }

  return { type: "unknown" };
}

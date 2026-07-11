import { describe, expect, it } from "vitest";

import { withUnavailableSaved } from "./AgentFormPage";

describe("withUnavailableSaved", () => {
  const options = [
    { value: "openai/gpt-5.6-luna", label: "GPT-5.6 Luna", group: "OpenAI" },
  ];

  it("keeps a saved unavailable model visible", () => {
    const result = withUnavailableSaved(options, "google/gemini-2.5-flash");

    expect(result[0]).toEqual({
      value: "google/gemini-2.5-flash",
      label: "google/gemini-2.5-flash (unavailable)",
      group: "Unavailable",
    });
  });

  it("does not duplicate an available model", () => {
    expect(withUnavailableSaved(options, "openai/gpt-5.6-luna")).toEqual(options);
  });
});

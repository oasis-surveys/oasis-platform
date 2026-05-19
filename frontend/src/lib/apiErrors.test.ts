import { describe, it, expect } from "vitest";
import {
  formatApiError,
  isValidWidgetHexColor,
  localDateEndIso,
  localDateStartIso,
} from "./apiErrors";

describe("formatApiError", () => {
  it("returns string detail as-is", () => {
    expect(formatApiError("Not found")).toBe("Not found");
  });

  it("joins validation error arrays", () => {
    expect(
      formatApiError([{ msg: "field required" }, { msg: "too short" }])
    ).toBe("field required; too short");
  });

  it("uses fallback when detail is missing", () => {
    expect(formatApiError(undefined, "fallback")).toBe("fallback");
  });
});

describe("isValidWidgetHexColor", () => {
  it("accepts 6-digit hex", () => {
    expect(isValidWidgetHexColor("#0D7377")).toBe(true);
  });

  it("rejects invalid values", () => {
    expect(isValidWidgetHexColor("red")).toBe(false);
    expect(isValidWidgetHexColor("#GGG")).toBe(false);
  });
});

describe("localDateIso", () => {
  it("uses local start and end of calendar day", () => {
    const start = localDateStartIso("2026-05-19");
    const end = localDateEndIso("2026-05-19");
    expect(new Date(start).getHours()).toBe(0);
    expect(new Date(end).getHours()).toBe(23);
  });
});

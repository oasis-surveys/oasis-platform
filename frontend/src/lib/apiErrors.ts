/**
 * Normalize FastAPI error `detail` payloads for display in the UI.
 */
export function formatApiError(
  detail: unknown,
  fallback = "Request failed"
): string {
  if (detail == null) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const msg = (item as { msg?: string }).msg;
          return typeof msg === "string" ? msg : "";
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length > 0) return parts.join("; ");
  }
  if (typeof detail === "object" && detail !== null && "msg" in detail) {
    const msg = (detail as { msg?: string }).msg;
    if (typeof msg === "string") return msg;
  }
  return fallback;
}

/** Local calendar date (YYYY-MM-DD) → start of that day in local timezone (ISO). */
export function localDateStartIso(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d, 0, 0, 0, 0).toISOString();
}

/** Local calendar date (YYYY-MM-DD) → end of that day in local timezone (ISO). */
export function localDateEndIso(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d, 23, 59, 59, 999).toISOString();
}

const HEX_COLOR_RE = /^#([0-9A-Fa-f]{6})$/;

export function isValidWidgetHexColor(hex: string): boolean {
  return HEX_COLOR_RE.test(hex.trim());
}

/** Parse #RRGGBB or return fallback (default OASIS teal). */
export function parseWidgetHexColor(hex: string, fallback = "#0D7377"): string {
  const trimmed = hex.trim();
  return isValidWidgetHexColor(trimmed) ? trimmed : fallback;
}

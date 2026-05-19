import { parseWidgetHexColor } from "./apiErrors";

/** Convert hex colour (#RRGGBB) to rgba with given alpha. */
export function hexToRgba(hex: string, alpha: number): string {
  const h = parseWidgetHexColor(hex).replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Extract RGB components as comma-separated string for CSS variables. */
export function hexToRgb(hex: string): string {
  const h = parseWidgetHexColor(hex).replace("#", "");
  return `${parseInt(h.substring(0, 2), 16)}, ${parseInt(h.substring(2, 4), 16)}, ${parseInt(h.substring(4, 6), 16)}`;
}

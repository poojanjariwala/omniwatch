/** Runtime configuration from public/app-config.js (loaded before the bundle). */
declare global {
  interface Window {
    OW_CONFIG?: { API_BASE?: string };
  }
}

export function apiBase(): string {
  const base = window.OW_CONFIG?.API_BASE;
  return base && base !== "/" ? base.replace(/\/+$/, "") : "";
}

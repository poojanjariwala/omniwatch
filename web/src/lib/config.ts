/** Runtime configuration from public/app-config.js (loaded before the bundle). */
declare global {
  interface Window {
    OW_CONFIG?: { API_BASE?: string; DEMO_MODE?: boolean };
  }
}

export function apiBase(): string {
  const base = window.OW_CONFIG?.API_BASE;
  return base && base !== "/" ? base.replace(/\/+$/, "") : "";
}

/** Demo mode: serve all API calls from the in-browser demo backend.
 *  "auto" enables it on deployed static hosts (github.io etc.) but not on
 *  localhost, where the vite proxy talks to the real API during development. */
export function isDemoMode(): boolean {
  const cfg = window.OW_CONFIG?.DEMO_MODE;
  if (cfg === false) return false;
  if (cfg === true) return true;
  if (localStorage.getItem("ow_demo_mode") === "1") return true;
  const host = window.location.hostname;
  const isStaticHost = host !== "localhost" && host !== "127.0.0.1" && host !== "";
  return (cfg === "auto" || cfg == null) && isStaticHost;
}

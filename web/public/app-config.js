// OmniWatch runtime configuration.
// Edit this file on a deployed static host to repoint the API without rebuilding.
// NOTE: if you change API_BASE, you must add the origin to backend CORS
// (CORS_ORIGINS env var on the API server), or requests will be blocked.
window.OW_CONFIG = {
  API_BASE: "", // empty = same origin (default for Docker/nginx and vite dev proxy)
  // "auto" = demo backend on static hosts (e.g. GitHub Pages), real API on localhost.
  // true forces demo everywhere; false disables the demo backend entirely.
  DEMO_MODE: "auto",
};

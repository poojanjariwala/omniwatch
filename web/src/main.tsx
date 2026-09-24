import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import App from "./App";
// Outfit — the single flat-design type family (self-hosted, keeps CSP 'self').
import "@fontsource/outfit/400.css";
import "@fontsource/outfit/500.css";
import "@fontsource/outfit/600.css";
import "@fontsource/outfit/700.css";
import "@fontsource/outfit/800.css";
import "./styles/design.css";
// Leaflet CSS is imported inside the lazy-loaded OpMap chunk so the map
// bundle (JS + CSS) is only fetched on pages that actually render a map.

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);

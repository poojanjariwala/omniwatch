// Local verification server: serves web/dist under /omniwatch/ exactly like
// GitHub Pages project sites do. Usage: node scripts/serve-pages-preview.mjs [port]
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { join, extname } from "node:path";

const ROOT = new URL("../web/dist", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const PORT = Number(process.argv[2] ?? 8788);
const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".svg": "image/svg+xml", ".woff": "font/woff", ".woff2": "font/woff2",
  ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
};

createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (!url.pathname.startsWith("/omniwatch/")) {
    res.writeHead(302, { Location: "/omniwatch/" }).end();
    return;
  }
  let rel = url.pathname.slice("/omniwatch/".length) || "index.html";
  if (rel.includes("..")) { res.writeHead(400).end(); return; }
  try {
    const buf = await readFile(join(ROOT, rel));
    res.writeHead(200, { "Content-Type": MIME[extname(rel)] ?? "application/octet-stream" });
    res.end(buf);
  } catch {
    // SPA fallback (HashRouter usually keeps URLs clean, but be safe)
    try {
      const buf = await readFile(join(ROOT, "index.html"));
      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(buf);
    } catch { res.writeHead(404).end("not found"); }
  }
}).listen(PORT, () => console.log(`pages preview on http://localhost:${PORT}/omniwatch/`));

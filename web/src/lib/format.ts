export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

export function sevTone(sev: string): string {
  if (sev === "critical") return "red";
  if (sev === "warning") return "amber";
  return "blue";
}

export function riskTone(risk: string | number | undefined): string {
  if (risk === "red" || (typeof risk === "number" && risk >= 0.7)) return "red";
  if (risk === "amber" || (typeof risk === "number" && risk >= 0.4)) return "amber";
  return "green";
}

export function statusTone(status: string): string {
  const ok = new Set(["completed", "closed", "consumed", "verified", "passed",
    "green", "issued", "active", "approved", "submitted", "true_positive", "pass"]);
  if (ok.has(status)) return "green";
  const warn = new Set(["in_review", "verifying", "review", "warning", "amber",
    "registered", "in_progress", "activated", "pending", "inconclusive", "unknown"]);
  if (warn.has(status)) return "amber";
  return "red";
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function shortHash(h: string | null | undefined, n = 12): string {
  if (!h) return "—";
  return h.length > n ? `${h.slice(0, n)}…` : h;
}

export function truncate(s: string | undefined | null, n = 90): string {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

/**
 * Client-side demo backend — serves every /api endpoint from in-memory,
 * seeded state so the SPA runs as a full interactive demo with no server.
 * Mutations (dispatch, scans, uploads, case actions) mutate the same state,
 * so the demo behaves like the real product for judges/demo viewers.
 *
 * Enabled via window.OW_CONFIG.DEMO_MODE (see public/app-config.js) or the
 * "ow_demo_mode" localStorage flag set by the login page's quick logins.
 */
import { DEMO_PERSONAS } from "./demo";

/* ------------------------------------------------------------------ utils */

const HEX = "0123456789abcdef";
function hex(n: number): string {
  let s = "";
  for (let i = 0; i < n; i++) s += HEX[Math.floor(Math.random() * 16)];
  return s;
}
function sha(): string {
  return hex(64);
}
function iso(minAgo: number): string {
  return new Date(Date.now() - minAgo * 60_000).toISOString();
}
function isoAhead(minAhead: number): string {
  return new Date(Date.now() + minAhead * 60_000).toISOString();
}
function approxDistanceM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6_371_000, rad = Math.PI / 180;
  const x = (lng2 - lng1) * rad * Math.cos(((lat1 + lat2) / 2) * rad);
  const y = (lat2 - lat1) * rad;
  return Math.round(Math.sqrt(x * x + y * y) * R);
}
function checklistFor(cat: string): Array<{ id: string; item: string }> {
  return cat === "skill"
    ? [{ id: "c1", item: "Attendance register matches trainees present" }, { id: "c2", item: "Trainer qualifications displayed" }, { id: "c3", item: "Equipment inventory intact" }]
    : [{ id: "c1", item: "Stock register matches physical inventory" }, { id: "c2", item: "QR handout scanning in active use" }, { id: "c3", item: "Beneficiary queue matches reported count" }, { id: "c4", item: "Storage conditions acceptable" }];
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload ?? null), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/* ------------------------------------------------------------------- seed */

interface DemoUser {
  id: number; email: string; password: string; full_name: string; role: string;
  org_id?: number | null; state_code?: string | null;
}
interface DemoState {
  seq: Record<string, number>;
  users: DemoUser[];
  orgs: Array<{ id: number; name: string }>;
  projects: any[];
  cameras: any[];
  cctvEvents: any[];
  alerts: any[];
  inspections: any[];
  evidence: any[];
  cases: any[];
  distributions: any[];
  codes: Array<any & { distribution_id: number }>;
  scanLogs: any[];
  outdoorEvents: any[];
  audit: any[];
}
function nextId(s: DemoState, k: string): number {
  s.seq[k] = (s.seq[k] ?? 100) + 1;
  return s.seq[k];
}
function auditLog(s: DemoState, actor: DemoUser | null, action: string, objectType: string, objectId: number | null, detail: Record<string, unknown> = {}) {
  s.audit.unshift({
    id: nextId(s, "audit"), ts: iso(0), actor_id: actor?.id ?? null,
    actor_name: actor?.full_name ?? "system", actor_role: actor?.role ?? "system",
    action, object_type: objectType, object_id: objectId, detail,
  });
}

function seed(): DemoState {
  const s: DemoState = {
    seq: {}, users: [], orgs: [], projects: [], cameras: [], cctvEvents: [],
    alerts: [], inspections: [], evidence: [], cases: [], distributions: [],
    codes: [], scanLogs: [], outdoorEvents: [], audit: [],
  };

  s.orgs = [
    { id: 1, name: "Dept. of Social Justice (Demo)" },
    { id: 2, name: "PMU Field Ops (Demo)" },
    { id: 3, name: "NGO Aasha Foundation" },
    { id: 4, name: "NGO Kiran Society" },
  ];

  s.users = [
    { id: 1, email: "admin@omniwatch.demo.in", password: "Admin@Demo123", full_name: "Arjun Mehta", role: "dosje", org_id: 1, state_code: "DL" },
    { id: 2, email: "state@omniwatch.demo.in", password: "State@Demo123", full_name: "Priya Nair", role: "state", org_id: 1, state_code: "DL" },
    { id: 3, email: "rakesh@pmu.demo.in", password: "Pmu@Demo123", full_name: "Rakesh Kumar", role: "pmu", org_id: 2 },
    { id: 4, email: "meena@pmu.demo.in", password: "Pmu@Demo123", full_name: "Meena Sharma", role: "pmu", org_id: 2 },
    { id: 5, email: "ngo@demo.org", password: "Ngo@Demo123", full_name: "Aasha Foundation Desk", role: "ngo", org_id: 3 },
    { id: 6, email: "ngo2@demo.org", password: "Ngo2@Demo123", full_name: "Kiran Society Desk", role: "ngo", org_id: 4 },
    { id: 7, email: "ben@demo.in", password: "Ben@Demo123", full_name: "Sunita Devi", role: "beneficiary" },
  ];

  const P = (code: string, name: string, orgId: number, lat: number, lng: number, risk: string, score: number, reported: number, cat: string, alertsOpen: number, cams: number) => ({
    id: nextId(s, "project"), code, name, scheme: "NSAP / SIDM (demo)", category: cat,
    address: `Ward ${10 + (nextId(s, "ward") % 40)}, North District, Delhi`, lat, lng,
    status: "active", reported_beneficiaries: reported, risk_status: risk, risk_score: score,
    org_name: s.orgs.find((o) => o.id === orgId)?.name, org_id: orgId,
    camera_count: cams, open_alerts: alertsOpen, geofence_radius_m: 50,
    risk_last_update: iso(30 + Math.floor(Math.random() * 300)), risk_reason: { drivers: ["cctv occupancy deviation", "beneficiary grievance rate"] },
  });
  s.projects = [
    P("REG-101", "Ashok Vihar Distribution Centre", 3, 28.7145, 77.1712, "red", 0.82, 1420, "distribution", 2, 2),
    P("REG-102", "Rohini Sector-7 Skill Centre", 3, 28.7025, 77.1187, "amber", 0.55, 640, "skill", 1, 1),
    P("REG-103", "Civil Lines Old-Age Home", 1, 28.6802, 77.2219, "green", 0.18, 210, "centre", 0, 2),
    P("REG-104", "Narela Community Kitchen", 4, 28.8227, 77.0918, "amber", 0.47, 980, "distribution", 1, 1),
    P("REG-105", "Dwarka Mobility Aid Camp", 4, 28.5921, 77.0460, "green", 0.21, 330, "outdoor", 0, 0),
    P("REG-106", "Karol Bagh Aid Depot", 3, 28.6512, 77.1907, "red", 0.74, 1180, "distribution", 2, 1),
  ];
  const proj = (code: string) => s.projects.find((p) => p.code === code)!;

  s.cameras = [
    { id: 1, project_id: proj("REG-101").id, project_name: proj("REG-101").name, name: "Main hall — entry", source_type: "simulator", enabled: true, ingest_every_seconds: 30, last_ingest_at: iso(4), last_frame_count: 23, last_error: null },
    { id: 2, project_id: proj("REG-101").id, project_name: proj("REG-101").name, name: "Counter — desk tripwire", source_type: "simulator", enabled: true, ingest_every_seconds: 45, last_ingest_at: iso(9), last_frame_count: 11, last_error: null },
    { id: 3, project_id: proj("REG-106").id, project_name: proj("REG-106").name, name: "Depot entrance", source_type: "file", enabled: true, ingest_every_seconds: 60, last_ingest_at: iso(26), last_frame_count: 8, last_error: null },
    { id: 4, project_id: proj("REG-104").id, project_name: proj("REG-104").name, name: "Kitchen queue", source_type: "simulator", enabled: false, ingest_every_seconds: 30, last_ingest_at: null, last_frame_count: null, last_error: "stream unreachable (demo)" },
  ];
  for (let i = 40; i > 0; i--) {
    s.cctvEvents.push({
      id: nextId(s, "ccev"), camera_id: 1 + (i % 3), ts: iso(i * 12),
      occupancy: 6 + Math.floor(Math.random() * 10) + (i < 8 ? 14 : 0),
      items_handed: 3 + Math.floor(Math.random() * 6), processed_by: "simulator",
    });
  }

  const mkAlert = (n: number, kind: string, sev: string, status: string, pCode: string, minAgo: number, title: string, summary: string, risk: number) => ({
    id: nextId(s, "alert"), code: `ALR-${1000 + n}`, kind, severity: sev, status, title, summary,
    project_id: proj(pCode).id, project_name: proj(pCode).name, occurred_at: iso(minAgo),
    signals: [
      { type: "cctv_occupancy", observed: 34, baseline: 12.5, ratio: 2.7, window_minutes: 30 },
      { type: "items_handed", count: 6, expected_min: 25, desk: "counter-1" },
      { type: "beneficiary_grievance", count: 3, channel: "helpline" },
    ],
    risk_signal: risk, recommended_action: "Dispatch a blind on-site inspection to verify occupancy and register accuracy.",
    feedback: null, case_id: null, ai_generated: true,
    location: { lat: proj(pCode).lat, lng: proj(pCode).lng },
  });
  s.alerts = [
    mkAlert(1, "distribution_anomaly", "critical", "open", "REG-101", 18, "Sustained occupancy spike with near-zero handouts",
      "CCTV shows ~34 people inside for 30+ minutes while the desk counter recorded only 6 items handed over. Pattern consistent with diverted stock held for non-beneficiaries.", 0.86),
    mkAlert(2, "register_mismatch", "warning", "in_review", "REG-106", 55, "Reported beneficiaries exceed observed footfall",
      "Register reports 210 beneficiaries served today; door counter and QR scans support at most 90.", 0.61),
    mkAlert(3, "after_hours_activity", "warning", "verifying", "REG-104", 180, "Depot entry outside operating hours",
      "Motion detected 02:10–02:40 with shutter partially open; no delivery was scheduled.", 0.52),
    mkAlert(4, "qr_replay_attempt", "critical", "open", "REG-101", 240, "Reused QR code scanned 4 times",
      "The same item code was presented at two terminals within minutes — replay blocked and logged.", 0.79),
    mkAlert(5, "geofence_violation", "warning", "action_taken", "REG-102", 400, "Outdoor camp registered 900 m from approved pin",
      "Live broadcast placed the stall outside the approved geofence; spot check dispatched and evidence collected.", 0.44),
    mkAlert(6, "cctv_outage", "info", "open", "REG-104", 620, "Camera offline for 9 hours",
      "Kitchen queue camera stopped reporting; possible deliberate obstruction during distribution window.", 0.35),
  ];

  const mkInsp = (o: Partial<any> & { pCode: string; status: string; kind: string; inspector: DemoUser; minAgo: number }) => {
    const p = proj(o.pCode);
    return {
      id: nextId(s, "insp"), code: `INS-${2000 + s.seq.insp}`, status: o.status, blind: true,
      assignment_kind: o.kind, assigned_inspector_id: o.inspector.id, inspector_name: o.inspector.full_name,
      project_id: p.id, project: { code: p.code, name: p.name, scheme: p.scheme, category: p.category, address: p.address, org_name: p.org_name, lat: p.lat, lng: p.lng, geofence_radius_m: p.geofence_radius_m, risk_status: p.risk_status },
      created_at: iso(o.minAgo), assigned_at: iso(o.minAgo), activated_at: null, arrival_at: null, submitted_at: null,
      reason: o.reason ?? null, checklist_template: checklistFor(p.category),
      evidence: [], route_timeline: [], route_warnings: [], commitment_hash: sha(),
      verification_passed: null, notes: null,
    };
  };
  s.inspections = [
    mkInsp({ pCode: "REG-101", status: "assigned", kind: "risk_priority", inspector: s.users[2], minAgo: 22, reason: "Alert ALR-1001 pattern match (sealed)" }),
    mkInsp({ pCode: "REG-104", status: "assigned", kind: "spot_check", inspector: s.users[3], minAgo: 95, reason: "Random monthly draw" }),
    mkInsp({ pCode: "REG-102", status: "in_progress", kind: "random_surge", inspector: s.users[2], minAgo: 300 }),
    mkInsp({ pCode: "REG-106", status: "submitted", kind: "risk_priority", inspector: s.users[3], minAgo: 1500 }),
    mkInsp({ pCode: "REG-103", status: "completed", kind: "scheduled", inspector: s.users[2], minAgo: 2900 }),
  ];
  const submitted = s.inspections[3];
  submitted.activated_at = iso(1400); submitted.arrival_at = iso(1385); submitted.submitted_at = iso(1290);
  submitted.verification_passed = true; submitted.blind = false;
  submitted.evidence = [makeEvidenceRow(s, submitted.id, true, 12, "demo_simulated"), makeEvidenceRow(s, submitted.id, true, 11, "live_camera")];
  submitted.route_timeline = [
    { ts: iso(1400), within_geofence: false, distance_m: 41000 }, { ts: iso(1385), within_geofence: true, distance_m: 8 },
  ];
  const completed = s.inspections[4];
  completed.activated_at = iso(2880); completed.arrival_at = iso(2860); completed.submitted_at = iso(2800);
  completed.blind = false; completed.evidence = [makeEvidenceRow(s, completed.id, true, 12, "demo_simulated")];

  for (let i = 0; i < 2; i++) {
    const c = {
      id: nextId(s, "case"), code: `CAS-${300 + i}`, title: ["Stock diversion pattern — Ashok Vihar", "Register inflation — Karol Bagh"][i],
      status: i === 0 ? "open" : "closed", project_id: proj(i === 0 ? "REG-101" : "REG-106").id,
      project_name: proj(i === 0 ? "REG-101" : "REG-106").name, opened_at: iso(2000 - i * 400),
      alert_count: 2 - i, evidence_count: 2, inspection_count: 1,
      closure_action: i === 0 ? null : "clear", closure_note: i === 0 ? null : "Verified on-site; records reconciled.",
      timeline: [
        { kind: "alert", at: iso(2050 - i * 400), text: "Alert raised by anomaly engine (advisory)" },
        { kind: "review", at: iso(2030 - i * 400), text: "Reviewed by DoSJE official — moved to verification" },
        { kind: "inspection", at: iso(1900 - i * 400), text: "Blind inspection completed with geofence-verified evidence" },
        ...(i === 1 ? [{ kind: "closure", at: iso(400), text: "Case closed after re-authenticated decision" }] : []),
      ],
    };
    s.cases.push(c);
    s.alerts[i].case_id = c.id;
  }

  const mkDist = (title: string, pCode: string, consumed: number, total: number, orgId: number) => {
    const d = {
      id: nextId(s, "dist"), code: `DST-${500 + s.seq.dist}`, title, distribution_date: new Date().toISOString().slice(0, 10),
      status: "active", consumed, total_items: total, project_id: proj(pCode).id,
      project_name: proj(pCode).name, org_name: s.orgs.find((o) => o.id === orgId)?.name, org_id: orgId,
    };
    s.distributions.push(d);
    for (let i = 1; i <= total; i++) {
      const isConsumed = i <= consumed;
      s.codes.push({
        id: nextId(s, "code"), distribution_id: d.id, serial: i,
        code: `OW-${d.code}-${String(i).padStart(3, "0")}-${hex(6)}`,
        status: isConsumed ? "consumed" : "issued",
        recipient_token: isConsumed ? `BEN-${String(100 + i).padStart(3, "0")}` : null,
        consumed_at: isConsumed ? iso(60 + i * 7) : null,
      });
    }
    return d;
  };
  const d1 = mkDist("October ration kit — phase 2", "REG-101", 9, 24, 3);
  const d2 = mkDist("Winter blanket drive", "REG-104", 4, 30, 4);
  for (let i = 0; i < 6; i++) {
    const ok = i !== 4;
    s.scanLogs.push({
      id: nextId(s, "scanlog"), ok, reason: ok ? "handed_over" : "already_consumed",
      code: ok ? `OW-${d1.code}-00${i + 1}-xxxx` : `OW-${d1.code}-003-xxxx`,
      created_at: iso(100 - i * 15), actor_name: "Aasha Foundation Desk",
      distribution_id: d1.id,
    });
  }

  s.outdoorEvents = [
    { id: 1, code: "EVT-401", title: "Mela distribution stall — Dwarka", scheduled_at: isoAhead(2880), registered_at: iso(3000), status: "approved", lat: 28.5921, lng: 77.046, org_name: "NGO Kiran Society", project_id: proj("REG-105").id, live_lat: null, live_lng: null, last_broadcast_at: null },
    { id: 2, code: "EVT-402", title: "Awareness camp — Rohini", scheduled_at: isoAhead(120), registered_at: iso(2900), status: "registered", lat: 28.7041, lng: 77.1025, org_name: "NGO Aasha Foundation", project_id: null, live_lat: null, live_lng: null, last_broadcast_at: null },
    { id: 3, code: "EVT-403", title: "Mobile aid van — Civil Lines", scheduled_at: iso(60), registered_at: iso(4000), status: "completed", lat: 28.6802, lng: 77.2219, org_name: "NGO Aasha Foundation", project_id: proj("REG-103").id, live_lat: 28.6804, live_lng: 77.2222, last_broadcast_at: iso(90) },
  ];

  const auditActions: Array<[string, string, number | null, number | null]> = [
    ["auth.login", "user", 1, 1], ["auth.login", "user", 3, 3], ["alert.status_change", "alert", 2, 1],
    ["inspection.dispatch", "inspection", s.inspections[0].id, 1], ["evidence.access", "evidence", 1, 1],
    ["evidence.upload", "evidence", 2, 3], ["case.opened", "case", 1, 1], ["qr.scan", "qr_code", 3, 5],
    ["qr.scan_blocked", "qr_code", 4, 5], ["cctv.ingest", "camera", 1, 1], ["auth.login_failed", "user", null, null],
    ["report.generated", "case", 1, 1], ["event.registered", "outdoor_event", 2, 5], ["alert.dispatch", "alert", 1, 1],
    ["case.closed", "case", 2, 2],
  ];
  auditActions.forEach(([action, ot, oid, actorId], i) => {
    const actor = s.users.find((u) => u.id === actorId);
    s.audit.push({
      id: nextId(s, "audit"), ts: iso(10 + i * 37), actor_id: actorId,
      actor_name: actor?.full_name ?? "system",
      actor_role: actor?.role ?? "system",
      action, object_type: ot, object_id: oid, detail: { demo: true },
    });
  });

  return s;
}

function makeEvidenceRow(s: DemoState, inspectionId: number, geoOk: boolean, minAgo: number, source: string) {
  const prev = s.evidence[s.evidence.length - 1];
  const row = {
    id: nextId(s, "evidence"), inspection_id: inspectionId, case_id: null,
    kind: "photo", mime: "image/jpeg", source, captured_at: iso(minAgo),
    lat: 28.71 + Math.random() * 0.01, lng: 77.15 + Math.random() * 0.01,
    geofence_ok: geoOk, distance_m: geoOk ? Math.floor(Math.random() * 40) : 800 + Math.floor(Math.random() * 500),
    sha256: sha(), chain_prev_hash: prev ? prev.chain_hash : hex(64), chain_hash: sha(),
    metadata: { device: "demo-web", label: "DEMO SIMULATED SITE PHOTO" },
  };
  s.evidence.push(row);
  return row;
}

/* ------------------------------------------------------------- blob makers */

function demoEvidenceImage(label: string): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = 640; canvas.height = 420;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 640, 420);
  g.addColorStop(0, "#1e293b"); g.addColorStop(1, "#334155");
  ctx.fillStyle = g; ctx.fillRect(0, 0, 640, 420);
  ctx.fillStyle = "#94a3b8";
  for (let i = 0; i < 40; i++) ctx.fillRect(Math.random() * 640, Math.random() * 420, 3, 3);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 24px sans-serif";
  ctx.fillText("DEMO EVIDENCE ARTIFACT", 40, 90);
  ctx.font = "15px sans-serif";
  ctx.fillText(label, 40, 125);
  ctx.fillText(`captured ${new Date().toLocaleString()}`, 40, 395);
  return new Promise((res) => canvas.toBlob((b) => res(b ?? new Blob()), "image/jpeg", 0.9));
}

/** Minimal valid single-page PDF (ASCII only). */
function buildPdf(title: string, lines: string[]): Blob {
  const esc = (t: string) => t.replace(/[\\()]/g, (c) => `\\${c}`);
  let content = `BT /F1 16 Tf 50 780 Td (${esc(title)}) Tj ET\n`;
  lines.forEach((l, i) => {
    content += `BT /F1 10 Tf 50 ${756 - i * 14} Td (${esc(l.slice(0, 95))}) Tj ET\n`;
  });
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${content.length} >>\nstream\n${content}endstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((o, i) => { offsets.push(pdf.length); pdf += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => { pdf += `${String(o).padStart(10, "0")} 00000 n \n`; });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return new Blob([pdf], { type: "application/pdf" });
}

/* --------------------------------------------------------------- the router */

let state: DemoState = seed();
let currentUser: DemoUser | null = null;

function userFromToken(_token: string | null): DemoUser | null {
  if (currentUser) return currentUser;
  // Restore the session after a page refresh (demo tokens are decorative;
  // the SPA stores the profile in sessionStorage via setSession()).
  try {
    const raw = sessionStorage.getItem("ow_user");
    if (raw) {
      const email = (JSON.parse(raw) as { email?: string }).email;
      currentUser = state.users.find((u) => u.email === email) ?? null;
    }
  } catch { /* ignore */ }
  return currentUser;
}

function publicUser(u: DemoUser) {
  return { id: u.id, email: u.email, full_name: u.full_name, role: u.role, org_id: u.org_id ?? null, state_code: u.state_code ?? null };
}

function recomputeProjectRisk(p: any) {
  p.open_alerts = state.alerts.filter((a) => a.project_id === p.id && !["closed", "action_taken"].includes(a.status)).length;
}
function recomputeCaseCounts(c: any) {
  const alerts = state.alerts.filter((a) => a.case_id === c.id);
  const inspIds = new Set(alerts.map((a) => a.dispatched_inspection_id).filter(Boolean));
  const ev = state.evidence.filter((e) => inspIds.has(e.inspection_id));
  c.alert_count = alerts.length;
  c.inspection_count = inspIds.size;
  c.evidence_count = ev.length;
}

export async function demoRequest(path: string, opts: {
  method?: string; json?: any; form?: FormData; headers?: Headers;
} = {}): Promise<Response> {
  const method = (opts.method ?? "GET").toUpperCase();
  const [rawPath, rawQuery] = path.split("?");
  const q = new URLSearchParams(rawQuery ?? "");
  const seg = rawPath.replace(/^\/api\//, "").split("/").filter(Boolean);
  const s = state;
  await new Promise((r) => setTimeout(r, 120 + Math.random() * 180)); // realistic latency

  /* ------------------------------------------------------------- auth */
  if (seg[0] === "auth" && seg[1] === "login" && method === "POST") {
    const u = s.users.find((x) => x.email === opts.json?.email && x.password === opts.json?.password);
    if (!u) {
      auditLog(s, null, "auth.login_failed", "user", null, { email: opts.json?.email });
      return jsonResponse({ detail: "Invalid email or password (demo)" }, 401);
    }
    currentUser = u;
    auditLog(s, u, "auth.login", "user", u.id);
    return jsonResponse({
      access_token: `demo.${hex(24)}`, refresh_token: `demo.${hex(24)}`, user: publicUser(u),
    });
  }
  if (seg[0] === "auth" && seg[1] === "refresh" && method === "POST") {
    if (!currentUser) return jsonResponse({ detail: "invalid refresh token" }, 401);
    return jsonResponse({ access_token: `demo.${hex(24)}`, refresh_token: `demo.${hex(24)}` });
  }
  if (seg[0] === "auth" && seg[1] === "confirm-password" && method === "POST") {
    if (currentUser && opts.json?.password === currentUser.password) {
      auditLog(s, currentUser, "auth.reauth", "user", currentUser.id);
      return jsonResponse({ action_token: `demo.act.${hex(16)}` });
    }
    return jsonResponse({ detail: "Password re-authentication failed (demo)" }, 401);
  }
  if (seg[0] === "auth" && seg[1] === "logout" && method === "POST") {
    currentUser = null;
    return new Response(null, { status: 204 });
  }

  const user = userFromToken(opts.headers?.get("Authorization") ?? null);

  /* -------------------------------------------------------- dashboard */
  if (seg[0] === "dashboard" && seg[1] === "overview") {
    const open = s.alerts.filter((a) => !["closed", "action_taken"].includes(a.status));
    return jsonResponse({
      summary: {
        projects: {
          total: s.projects.length,
          red: s.projects.filter((p) => p.risk_status === "red").length,
          amber: s.projects.filter((p) => p.risk_status === "amber").length,
        },
        alerts: { open: open.length, critical: open.filter((a) => a.severity === "critical").length },
        inspections: { open: s.inspections.filter((i) => !["completed", "cancelled"].includes(i.status)).length },
        cameras: s.cameras.filter((c) => c.enabled).length,
        active_events: s.outdoorEvents.filter((e) => e.status === "approved").length,
      },
      alerts: open,
      inspections: s.inspections.filter((i) => i.status !== "cancelled"),
      inspector_status: s.users.filter((u) => u.role === "pmu").map((u) => ({
        id: u.id, full_name: u.full_name,
        open_inspections: s.inspections.filter((i) => i.assigned_inspector_id === u.id && !["completed", "cancelled"].includes(i.status)).length,
        last_position_at: iso(5 + u.id * 3),
      })),
    });
  }
  if (seg[0] === "dashboard" && seg[1] === "map") {
    return jsonResponse({
      projects: s.projects.map((p) => ({ id: p.id, code: p.code, name: p.name, lat: p.lat, lng: p.lng, risk_status: p.risk_status, risk_score: p.risk_score, org_name: p.org_name, category: p.category })),
      inspectors: s.users.filter((u) => u.role === "pmu").map((u, i) => ({
        id: u.id, full_name: u.full_name,
        lat: 28.69 + i * 0.02 + (s.inspections.some((x) => x.assigned_inspector_id === u.id && x.status === "in_progress") ? 0.005 : 0),
        lng: 77.13 + i * 0.03,
      })),
      outdoor_events: s.outdoorEvents.filter((e) => e.status !== "completed").map((e) => ({ id: e.id, code: e.code, title: e.title, lat: e.live_lat ?? e.lat, lng: e.live_lng ?? e.lng, status: e.status })),
      routes: s.users.filter((u) => u.role === "pmu").map((u, i) => ({
        code: `RT-${u.id}`,
        points: [0, 1, 2].map((k) => ({ lat: 28.70 + i * 0.02 + k * 0.004, lng: 77.13 + i * 0.03 + k * 0.005 })),
      })),
    });
  }
  if (seg[0] === "dashboard" && seg[1] === "ngo-overview") {
    const orgProjects = s.projects.filter((p) => p.org_id === (user?.org_id ?? 3));
    return jsonResponse({
      distributions: s.distributions.filter((d) => d.org_id === (user?.org_id ?? 3)),
      projects: orgProjects.length ? orgProjects : s.projects.slice(0, 2),
    });
  }

  /* ----------------------------------------------------------- alerts */
  if (seg[0] === "alerts" && seg.length === 1 && method === "GET") {
    return jsonResponse({ alerts: s.alerts });
  }
  if (seg[0] === "alerts" && seg[2] === "status" && method === "PATCH") {
    const a = s.alerts.find((x) => x.id === Number(seg[1]));
    if (!a) return jsonResponse({ detail: "alert not found" }, 404);
    a.status = opts.json?.to_status ?? a.status;
    auditLog(s, user, "alert.status_change", "alert", a.id, { to: a.status, note: opts.json?.note });
    return jsonResponse(a);
  }
  if (seg[0] === "alerts" && seg[2] === "dispatch" && method === "POST") {
    const a = s.alerts.find((x) => x.id === Number(seg[1]));
    if (!a) return jsonResponse({ detail: "alert not found" }, 404);
    const inspectors = s.users.filter((u) => u.role === "pmu");
    const inspector = inspectors[Math.floor(Math.random() * inspectors.length)];
    const p = s.projects.find((x) => x.id === a.project_id);
    const insp: any = {
      id: nextId(s, "insp"), code: `INS-${2000 + s.seq.insp}`, status: "assigned", blind: true,
      assignment_kind: "risk_priority", assigned_inspector_id: inspector.id, inspector_name: inspector.full_name,
      project_id: p?.id ?? null, project: p ? { code: p.code, name: p.name, scheme: p.scheme, category: p.category, address: p.address, org_name: p.org_name, lat: p.lat, lng: p.lng, geofence_radius_m: p.geofence_radius_m, risk_status: p.risk_status } : null,
      created_at: iso(0), assigned_at: iso(0), activated_at: null, arrival_at: null, submitted_at: null,
      reason: `Dispatched from ${a.code} (sealed)`, checklist_template: checklistFor(p?.category ?? "distribution"),
      evidence: [], route_timeline: [], route_warnings: [], commitment_hash: sha(), verification_passed: null, notes: null,
    };
    s.inspections.unshift(insp);
    a.status = "verifying";
    a.dispatched_inspection_id = insp.id;
    recomputeProjectRisk(p ?? {});
    auditLog(s, user, "alert.dispatch", "alert", a.id, { inspection: insp.code });
    return jsonResponse({ inspection: insp, note: "Blind inspection dispatched" });
  }
  if (seg[0] === "alerts" && seg[2] === "feedback" && method === "POST") {
    const a = s.alerts.find((x) => x.id === Number(seg[1]));
    if (!a) return jsonResponse({ detail: "alert not found" }, 404);
    a.feedback = opts.json?.feedback ?? null;
    auditLog(s, user, "alert.feedback", "alert", a.id, { feedback: a.feedback });
    return jsonResponse(a);
  }

  /* ------------------------------------------------------------ cases */
  if (seg[0] === "cases" && seg.length === 1 && method === "GET") {
    s.cases.forEach(recomputeCaseCounts);
    return jsonResponse({ cases: s.cases });
  }
  if (seg[0] === "cases" && seg.length === 1 && method === "POST") {
    const alertId = Number(q.get("alert_id"));
    const a = s.alerts.find((x) => x.id === alertId);
    const c = {
      id: nextId(s, "case"), code: `CAS-${300 + s.seq.case}`, title: a?.title ?? "Case from alert",
      status: "open", project_id: a?.project_id ?? null, project_name: a?.project_name ?? null,
      opened_at: iso(0), alert_count: a ? 1 : 0, evidence_count: 0, inspection_count: 0,
      closure_action: null, closure_note: null,
      timeline: [{ kind: "alert", at: iso(0), text: a ? `Opened from alert ${a.code}` : "Opened manually" }],
    };
    s.cases.unshift(c);
    if (a) { a.case_id = c.id; a.dispatched_inspection_id && c.timeline.push({ kind: "inspection", at: iso(0), text: "Linked dispatched inspection" }); }
    recomputeCaseCounts(c);
    auditLog(s, user, "case.opened", "case", c.id, { from_alert: alertId });
    return jsonResponse({ case_id: c.id, case_code: c.code });
  }
  if (seg[0] === "cases" && seg[2] === "close" && method === "POST") {
    const c = s.cases.find((x) => x.id === Number(seg[1]));
    if (!c) return jsonResponse({ detail: "case not found" }, 404);
    c.status = "closed";
    c.closure_action = opts.json?.closure_action ?? "clear";
    c.closure_note = opts.json?.closure_note ?? null;
    c.timeline.push({ kind: "closure", at: iso(0), text: `Closed (${c.closure_action}) after re-authenticated decision` });
    auditLog(s, user, "case.closed", "case", c.id, { action: c.closure_action });
    return jsonResponse(c);
  }
  if (seg[0] === "cases" && seg[2] === "report" && method === "GET") {
    const c = s.cases.find((x) => x.id === Number(seg[1]));
    if (!c) return jsonResponse({ detail: "case not found" }, 404);
    recomputeCaseCounts(c);
    const lines = [
      `Case ${c.code} — ${c.title}`, `Status: ${c.status}`, `Project: ${c.project_name ?? "—"}`,
      `Opened: ${c.opened_at}`, `Alerts: ${c.alert_count}  Evidence: ${c.evidence_count}  Inspections: ${c.inspection_count}`,
      "", "TIMELINE",
      ...c.timeline.map((t: any) => `- [${t.kind}] ${t.at} :: ${t.text}`),
      "", "This dossier is a demo artifact with sample data.",
    ];
    return new Response(buildPdf(`OmniWatch dossier — ${c.code}`, lines), {
      status: 200, headers: { "Content-Type": "application/pdf" },
    });
  }
  if (seg[0] === "cases" && seg.length === 2 && method === "GET") {
    const c = s.cases.find((x) => x.id === Number(seg[1]));
    if (!c) return jsonResponse({ detail: "case not found" }, 404);
    recomputeCaseCounts(c);
    const alerts = s.alerts.filter((a) => a.case_id === c.id);
    const inspIds = new Set(alerts.map((a) => a.dispatched_inspection_id).filter(Boolean));
    const insp = s.inspections.filter((i) => inspIds.has(i.id));
    const ev = state.evidence.filter((e) => inspIds.has(e.inspection_id));
    return jsonResponse({ case: c, alerts, inspections: insp, evidence: ev, timeline: c.timeline });
  }

  /* --------------------------------------------------------- evidence */
  if (seg[0] === "evidence" && seg.length === 1 && method === "GET") {
    let rows = s.evidence;
    const insp = q.get("inspection_id");
    if (insp) rows = rows.filter((e) => e.inspection_id === Number(insp));
    const limit = Number(q.get("limit") ?? 120);
    return jsonResponse({ evidence: rows.slice(0, limit) });
  }
  if (seg[0] === "evidence" && seg[2] === "verify" && method === "POST") {
    const e = s.evidence.find((x) => x.id === Number(seg[1]));
    if (!e) return jsonResponse({ detail: "not found" }, 404);
    return jsonResponse({ ok: true, sha256_match: true, chain_match: true });
  }
  if (seg[0] === "evidence" && seg[2] === "file" && method === "GET") {
    const e = s.evidence.find((x) => x.id === Number(seg[1]));
    if (!e) return new Response(null, { status: 404 });
    const blob = e._blob ?? (await demoEvidenceImage(e.metadata?.label ?? `evidence #${e.id}`));
    auditLog(s, user, "evidence.access", "evidence", e.id);
    return new Response(blob, { status: 200, headers: { "Content-Type": e.mime } });
  }
  if (seg[0] === "evidence" && seg.length === 2 && method === "GET") {
    const e = s.evidence.find((x) => x.id === Number(seg[1]));
    if (!e) return jsonResponse({ detail: "not found" }, 404);
    return jsonResponse({ evidence: e, integrity: { ok: true, sha256_match: true, chain_match: true } });
  }

  /* ------------------------------------------------------ inspections */
  if (seg[0] === "inspections" && seg[1] === "mine" && method === "GET") {
    const mine = s.inspections.filter((i) => user && i.assigned_inspector_id === user.id);
    return jsonResponse({
      assignments: mine.map((i) => ({
        id: i.id, code: i.code, status: i.status, blind: i.blind, assignment_kind: i.assignment_kind,
        assigned_at: i.assigned_at ?? i.created_at, reason: i.status === "assigned" ? null : i.reason,
      })),
    });
  }
  if (seg[0] === "inspections" && seg[1] === "dispatch" && method === "POST") {
    const p = s.projects.find((x) => x.id === Number(opts.json?.project_id));
    const inspectors = s.users.filter((u) => u.role === "pmu");
    const inspector = inspectors[Math.floor(Math.random() * inspectors.length)];
    const insp: any = {
      id: nextId(s, "insp"), code: `INS-${2000 + s.seq.insp}`, status: "assigned", blind: true,
      assignment_kind: opts.json?.kind ?? "spot_check", assigned_inspector_id: inspector.id,
      inspector_name: inspector.full_name, project_id: p?.id ?? null,
      project: p ? { code: p.code, name: p.name, scheme: p.scheme, category: p.category, address: p.address, org_name: p.org_name, lat: p.lat, lng: p.lng, geofence_radius_m: p.geofence_radius_m, risk_status: p.risk_status } : null,
      created_at: iso(0), assigned_at: iso(0), activated_at: null, arrival_at: null, submitted_at: null,
      reason: opts.json?.reason ?? null, checklist_template: checklistFor(p?.category ?? "distribution"),
      evidence: [], route_timeline: [], route_warnings: [], commitment_hash: sha(), verification_passed: null, notes: null,
    };
    s.inspections.unshift(insp);
    auditLog(s, user, "inspection.dispatch", "inspection", insp.id, { project: p?.code, kind: insp.assignment_kind });
    return jsonResponse({ inspection: insp, assignment: { method: "risk-priority hybrid", nonce: hex(16) } });
  }
  if (seg[0] === "inspections" && seg[2] === "device-check" && method === "POST") {
    return jsonResponse({
      verdict: "pass",
      signals: { play_integrity: "MEETS_DEVICE_INTEGRITY (demo)", emulator: false, rooted: false, adb: false },
    });
  }
  if (seg[0] === "inspections" && seg[2] === "activate" && method === "POST") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (!i) return jsonResponse({ detail: "not found" }, 404);
    i.status = "activated";
    i.activated_at = iso(0);
    i.blind = false;
    auditLog(s, user, "inspection.activated", "inspection", i.id);
    return jsonResponse({
      inspection_id: i.id, code: i.code, commitment_hash: i.commitment_hash, kind: i.assignment_kind,
      project: i.project, checklist: i.checklist_template,
    });
  }
  if (seg[0] === "inspections" && seg[2] === "start" && method === "POST") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (i) i.status = "in_progress";
    return jsonResponse(i ?? {});
  }
  if (seg[0] === "inspections" && seg[2] === "location" && method === "POST") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (!i?.project) return jsonResponse({ detail: "not found" }, 404);
    const d = approxDistanceM(Number(opts.json?.lat), Number(opts.json?.lng), i.project.lat, i.project.lng);
    const within = d <= (i.project.geofence_radius_m ?? 50);
    if (within && !i.arrival_at) i.arrival_at = iso(0);
    i.route_timeline.push({ ts: iso(0), within_geofence: within, distance_m: d });
    return jsonResponse({ within_geofence: within, distance_m: d });
  }
  if (seg[0] === "inspections" && seg[2] === "checklist" && method === "POST") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (i) i.checklist_answers = opts.json?.answers ?? [];
    return jsonResponse({ saved: true });
  }
  if (seg[0] === "inspections" && seg[2] === "submit" && method === "POST") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (!i) return jsonResponse({ detail: "not found" }, 404);
    i.status = "submitted";
    i.submitted_at = iso(0);
    i.notes = opts.json?.notes ?? null;
    const outside = (i.route_timeline ?? []).filter((l: any) => !l.within_geofence);
    i.route_warnings = outside.length ? [`${outside.length} location ping(s) outside geofence during visit`] : [];
    i.verification_passed = i.route_warnings.length === 0 && (i.evidence?.length ?? 0) > 0;
    auditLog(s, user, "inspection.submitted", "inspection", i.id);
    return jsonResponse({ route_warnings: i.route_warnings });
  }
  if (seg[0] === "inspections" && seg[2] === "evidence" && method === "POST" && opts.form) {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (!i) return jsonResponse({ detail: "not found" }, 404);
    const file = opts.form.get("file") as File | null;
    const prev = s.evidence[s.evidence.length - 1];
    const row = {
      id: nextId(s, "evidence"), inspection_id: i.id, case_id: null,
      kind: String(opts.form.get("kind") ?? "photo"), mime: file?.type ?? "image/jpeg",
      source: String(opts.form.get("source") ?? "live_camera"), captured_at: String(opts.form.get("captured_at") ?? iso(0)),
      lat: Number(opts.form.get("lat")) || i.project?.lat, lng: Number(opts.form.get("lng")) || i.project?.lng,
      geofence_ok: true, distance_m: Math.floor(Math.random() * 40),
      sha256: sha(), chain_prev_hash: prev ? prev.chain_hash : hex(64), chain_hash: sha(),
      metadata: { size: file?.size ?? 0, name: file?.name ?? "capture.jpg" },
      _blob: file ?? (await demoEvidenceImage(`capture for ${i.code}`)),
    };
    s.evidence.push(row);
    i.evidence.push(row);
    auditLog(s, user, "evidence.upload", "evidence", row.id, { inspection: i.code });
    return jsonResponse(row);
  }
  if (seg[0] === "inspections" && seg.length === 2 && method === "GET") {
    const i = s.inspections.find((x) => x.id === Number(seg[1]));
    if (!i) return jsonResponse({ detail: "not found" }, 404);
    if (i.blind && i.status === "assigned") {
      return jsonResponse({
        id: i.id, code: i.code, status: i.status, blind: true, assignment_kind: i.assignment_kind,
        inspector_name: i.inspector_name, reason: null, assigned_at: i.assigned_at,
      });
    }
    return jsonResponse(i);
  }
  if (seg[0] === "inspections" && seg.length === 1 && method === "GET") {
    return jsonResponse({ inspections: s.inspections });
  }

  /* -------------------------------------------------- projects / orgs */
  if (seg[0] === "projects" && seg.length === 1 && method === "GET") {
    return jsonResponse({ projects: s.projects });
  }
  if (seg[0] === "projects" && seg.length === 1 && method === "POST") {
    const p = {
      id: nextId(s, "project"), code: opts.json?.code, name: opts.json?.name, scheme: opts.json?.scheme,
      category: opts.json?.category ?? "centre", address: opts.json?.address ?? "",
      lat: Number(opts.json?.lat), lng: Number(opts.json?.lng), status: "active",
      reported_beneficiaries: Number(opts.json?.reported_beneficiaries) || 0,
      risk_status: "green", risk_score: 0.1, risk_reason: { drivers: [] }, org_id: Number(opts.json?.org_id),
      org_name: s.orgs.find((o) => o.id === Number(opts.json?.org_id))?.name,
      camera_count: 0, open_alerts: 0, geofence_radius_m: Number(opts.json?.geofence_radius_m) || 50,
      risk_last_update: iso(0),
    };
    s.projects.push(p);
    auditLog(s, user, "project.created", "project", p.id, { code: p.code });
    return jsonResponse(p);
  }
  if (seg[0] === "organizations" && method === "GET") {
    return jsonResponse(s.orgs);
  }

  /* ------------------------------------------------------------- cctv */
  if (seg[0] === "cctv" && seg.length === 1 && method === "GET") {
    return jsonResponse({ cameras: s.cameras });
  }
  if (seg[0] === "cctv" && seg.length === 1 && method === "POST") {
    const p = s.projects.find((x) => x.id === Number(opts.json?.project_id));
    const cam = {
      id: nextId(s, "cam"), project_id: p?.id, project_name: p?.name, name: opts.json?.name,
      source_type: opts.json?.source_type ?? "simulator", enabled: true,
      ingest_every_seconds: Number(opts.json?.ingest_every_seconds) || 30,
      last_ingest_at: null, last_frame_count: null, last_error: null,
    };
    s.cameras.push(cam);
    p && (p.camera_count = (p.camera_count ?? 0) + 1);
    auditLog(s, user, "cctv.registered", "camera", cam.id);
    return jsonResponse(cam);
  }
  if (seg[0] === "cctv" && seg[2] === "toggle" && method === "POST") {
    const c = s.cameras.find((x) => x.id === Number(seg[1]));
    if (c) c.enabled = !c.enabled;
    return jsonResponse(c ?? {});
  }
  if (seg[0] === "cctv" && seg[2] === "ingest" && method === "POST") {
    const c = s.cameras.find((x) => x.id === Number(seg[1]));
    if (!c) return jsonResponse({ detail: "not found" }, 404);
    const baseline = 10 + Math.random() * 4;
    const occupancy = Math.random() < 0.35 ? Math.floor(baseline * (2 + Math.random())) : Math.floor(baseline * (0.7 + Math.random() * 0.6));
    const flagged = occupancy > baseline * 1.8;
    c.last_ingest_at = iso(0);
    c.last_frame_count = occupancy;
    const ev = { id: nextId(s, "ccev"), camera_id: c.id, ts: iso(0), occupancy, items_handed: Math.max(0, Math.floor(occupancy / 4)), processed_by: "simulator" };
    s.cctvEvents.unshift(ev);
    auditLog(s, user, "cctv.ingest", "camera", c.id, { occupancy, flagged });
    return jsonResponse({ occupancy, baseline_ewma: Number(baseline.toFixed(2)), flagged });
  }
  if (seg[0] === "cctv" && seg[1] === "events") {
    const limit = Number(q.get("limit") ?? 120);
    return jsonResponse({ events: s.cctvEvents.slice(0, limit) });
  }
  if (seg[0] === "cctv" && seg[2] === "events") {
    const limit = Number(q.get("limit") ?? 80);
    return jsonResponse({ events: s.cctvEvents.filter((e) => e.camera_id === Number(seg[1])).slice(0, limit) });
  }

  /* --------------------------------------------------------------- qr */
  if (seg[0] === "qr" && seg[1] === "batches" && method === "POST") {
    const p = s.projects.find((x) => x.id === Number(opts.json?.project_id));
    const d = {
      id: nextId(s, "dist"), code: `DST-${500 + s.seq.dist}`, title: opts.json?.title ?? "New batch",
      distribution_date: new Date().toISOString().slice(0, 10), status: "active", consumed: 0,
      total_items: Number(opts.json?.count) || 10, project_id: p?.id ?? null,
      project_name: p?.name ?? null, org_id: user?.org_id ?? null, org_name: s.orgs.find((o) => o.id === user?.org_id)?.name,
    };
    s.distributions.unshift(d);
    for (let i = 1; i <= d.total_items; i++) {
      s.codes.push({ id: nextId(s, "code"), distribution_id: d.id, serial: i, code: `OW-${d.code}-${String(i).padStart(3, "0")}-${hex(6)}`, status: "issued", recipient_token: null, consumed_at: null });
    }
    auditLog(s, user, "qr.batch_issued", "distribution", d.id, { items: d.total_items });
    return jsonResponse(d);
  }
  if (seg[0] === "qr" && seg[1] === "verify" && method === "POST") {
    const c = s.codes.find((x) => x.code === String(opts.json?.code ?? "").trim());
    if (!c) return jsonResponse({ status: "unknown", message: "Code not recognised in the demo register." });
    if (c.status === "consumed") return jsonResponse({ status: "consumed", message: "Already handed over — verified successfully.", serial: c.serial });
    return jsonResponse({ status: c.status, message: "Issued and awaiting handover.", serial: c.serial });
  }
  if (seg[0] === "qr" && seg[1] === "scan" && method === "POST") {
    const code = String(opts.json?.code ?? "").trim();
    const c = s.codes.find((x) => x.code === code);
    const d = c ? s.distributions.find((x) => x.id === c.distribution_id) : null;
    const log = (ok: boolean, reason: string) => {
      s.scanLogs.unshift({ id: nextId(s, "scanlog"), ok, reason, code, created_at: iso(0), actor_name: user?.full_name ?? "demo", distribution_id: c?.distribution_id ?? null });
    };
    if (!c) { log(false, "unknown_code"); return jsonResponse({ ok: false, reason: "unknown_code", message: "Code not recognised (demo register)." }); }
    if (c.status === "consumed") { log(false, "already_consumed"); return jsonResponse({ ok: false, reason: "already_consumed", message: "This item was already handed over — replay blocked." }); }
    c.status = "consumed";
    c.consumed_at = iso(0);
    c.recipient_token = opts.json?.recipient_token ?? null;
    if (d) {
      d.consumed = (d.consumed ?? 0) + 1;
      if (d.consumed >= d.total_items) d.status = "completed";
    }
    log(true, "handed_over");
    auditLog(s, user, "qr.scan", "qr_code", c.id, { serial: c.serial });
    return jsonResponse({
      ok: true, serial: c.serial,
      consumed_today: s.distributions.filter((x) => x.org_id === user?.org_id).reduce((acc, x) => acc + (x.consumed ?? 0), 0),
      total_items: d?.total_items ?? 0,
    });
  }
  if (seg[0] === "qr" && seg[3] === "codes") {
    return jsonResponse({ codes: s.codes.filter((x) => x.distribution_id === Number(seg[2])) });
  }
  if (seg[0] === "qr" && seg[1] === "scan-logs") {
    const dist = q.get("distribution_id");
    const rows = dist ? s.scanLogs.filter((l) => l.distribution_id === Number(dist)) : s.scanLogs;
    return jsonResponse({ logs: rows });
  }

  /* --------------------------------------------------- outdoor events */
  if (seg[0] === "events" && seg.length === 1 && method === "GET") {
    return jsonResponse({ events: s.outdoorEvents });
  }
  if (seg[0] === "events" && seg.length === 1 && method === "POST") {
    const e = {
      id: nextId(s, "event"), code: `EVT-${400 + s.seq.event}`, title: opts.json?.title,
      scheduled_at: opts.json?.scheduled_at, registered_at: iso(0), status: "registered",
      lat: Number(opts.json?.lat), lng: Number(opts.json?.lng),
      org_name: s.orgs.find((o) => o.id === user?.org_id)?.name ?? "demo",
      project_id: opts.json?.project_id ? Number(opts.json.project_id) : null,
      live_lat: null, live_lng: null, last_broadcast_at: null,
    };
    s.outdoorEvents.unshift(e);
    auditLog(s, user, "event.registered", "outdoor_event", e.id);
    return jsonResponse(e);
  }
  if (seg[0] === "events" && seg[2] === "broadcast" && method === "POST") {
    const e = s.outdoorEvents.find((x) => x.id === Number(seg[1]));
    if (e) {
      e.live_lat = Number(opts.json?.lat) || e.lat;
      e.live_lng = Number(opts.json?.lng) || e.lng;
      e.last_broadcast_at = iso(0);
    }
    auditLog(s, user, "event.broadcast", "outdoor_event", e?.id ?? null);
    return jsonResponse(e ?? {});
  }

  /* ------------------------------------------------------------ audit */
  if (seg[0] === "audit" && method === "GET") {
    let rows = s.audit;
    const action = q.get("action");
    if (action) rows = rows.filter((e) => e.action === action);
    return jsonResponse({ events: rows });
  }

  return jsonResponse({ detail: `Demo backend has no handler for ${method} ${rawPath}` }, 404);
}

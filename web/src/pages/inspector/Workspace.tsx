import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Chip, Err, Ok, Panel, Btn, Field, Empty, TrustRow, Kv } from "../../components/ui";
import { apiErrorText, request, requestBlob } from "../../lib/api";
import { fmtTime, shortHash, titleCase } from "../../lib/format";
import { enqueueItem, loadQueue, syncQueue } from "../../lib/offline";

interface BlindAssignment {
  id: number; code: string; status: string; blind: boolean; assignment_kind: string;
  inspector_name?: string; reason?: string | null;
}
interface Reveal { inspection_id: number; code: string; commitment_hash?: string;
  kind: string; project: { code: string; name: string; scheme: string; category: string;
    address?: string | null; org_name?: string | null; lat: number; lng: number;
    geofence_radius_m: number; }; checklist: Array<{ id: string; item: string }>; }
interface FullInsp {
  id: number; code: string; status: string; assignment_kind?: string; activated_at?: string;
  arrival_at?: string | null; submitted_at?: string | null; project?: any; evidence?: any[];
  route_warnings?: string[]; notes?: string | null; result_summary?: any;
}

export default function InspectorWorkspace() {
  const { id } = useParams();
  const inspId = Number(id);
  const [assign, setAssign] = useState<BlindAssignment | null>(null);
  const [revealed, setRevealed] = useState<Reveal | null>(null);
  const [full, setFull] = useState<FullInsp | null>(null);
  const [device, setDevice] = useState<null | { verdict: string; signals: any }>(null);
  const [loc, setLoc] = useState<null | { within_geofence: boolean; distance_m: number }>(null);
  const [checklist, setChecklist] = useState<Array<{ id: string; item: string; passed: boolean; note: string }>>([]);
  const [pending, setPending] = useState(0);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const [answers, setAnswers] = useState<Record<string, boolean>>({});

  const loadBlind = useCallback(async () => {
    const r = await request<any>(`/api/inspections/${inspId}`);
    if (r && r.project === undefined && r.blind === true) {
      setAssign(r);
    } else {
      setAssign(r);
      setFull(r);
    }
  }, [inspId]);

  useEffect(() => { loadBlind().catch((e) => setErr(apiErrorText(e))); }, [loadBlind]);
  useEffect(() => { setPending(loadQueue().filter((q) => q.inspection_id === inspId).length); }, []);

  async function run(fn: () => Promise<unknown>, label: string) {
    setBusy(label); setErr(""); setMsg("");
    try { await fn(); } catch (e) { setErr(apiErrorText(e)); } finally { setBusy(""); }
  }

  async function doDeviceCheck() {
    await run(async () => {
      const r = await request<any>(`/api/inspections/${inspId}/device-check`, { method: "POST" });
      setDevice(r);
    }, "Checking device");
  }

  async function doActivate() {
    await run(async () => {
      const r = await request<Reveal>(`/api/inspections/${inspId}/activate`, { method: "POST" });
      setRevealed(r);
      setChecklist(r.checklist.map((c) => ({ id: c.id, item: c.item, passed: false, note: "" })));
      const det = await request<any>(`/api/inspections/${inspId}`);
      setFull(det);
    }, "Opening envelope");
  }

  async function doStart() {
    await run(async () => {
      await request(`/api/inspections/${inspId}/start`, { method: "POST" });
      refreshDetail();
    }, "Starting");
  }

  const refreshDetail = useCallback(async () => {
    if (!revealed && !full) return;
    const r = await request<any>(`/api/inspections/${inspId}`);
    setFull(r);
  }, [inspId, revealed, full]);

  async function doLocation(lat: number, lng: number) {
    await run(async () => {
      const r = await request<any>(`/api/inspections/${inspId}/location`,
        { method: "POST", json: { lat, lng, device: { source: "demo-gps" } } });
      setLoc(r);
      refreshDetail();
    }, "Reporting location");
  }

  async function saveChecklist() {
    await run(async () => {
      await request(`/api/inspections/${inspId}/checklist`, {
        method: "POST",
        json: { answers: checklist.map((c) => ({ ...c, passed: !!answers[c.id] })) },
      });
      setMsg("Checklist saved");
    }, "Saving");
  }

  async function doSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const notes = new FormData(e.currentTarget).get("notes") as string;
    await run(async () => {
      const r = await request<any>(`/api/inspections/${inspId}/submit`, { method: "POST", json: { notes } });
      setFull((f) => ({ ...(f as FullInsp), status: "submitted", route_warnings: r.route_warnings }));
      setMsg("Submitted — awaiting official review");
    }, "Submitting");
  }

  const project = revealed?.project ?? full?.project;

  return (
    <div className="stack" style={{ maxWidth: 1080 }}>
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Field inspection</h1>
        <Chip tone={assign?.status === "submitted" ? "green" : "amber"}>
          {assign?.status ?? full?.status ?? "…"}
        </Chip>
      </div>
      {err && <Err message={err} />}
      {msg && <Ok message={msg} />}

      <TrustRow states={[
        { label: "Authenticated", ok: true },
        { label: "Role verified (PMU)", ok: true },
        { label: "Device verified", ok: device?.verdict === "pass" },
        { label: "Task revealed", ok: !!revealed },
        { label: "Location verified", ok: loc?.within_geofence || !!full?.arrival_at },
        { label: "Evidence hashed", ok: (full?.evidence?.length ?? 0) > 0 },
        { label: "Sync pending", ok: pending === 0 ? null : false },
      ]} />

      {pending > 0 && (
        <div className="panel">
          <div className="panel-body row spread">
            <span><Chip tone="amber">Offline queue</Chip> {pending} capture(s) awaiting connection</span>
            <Btn kind="primary" onClick={async () => {
              const r = await syncQueue(inspId);
              setPending(loadQueue().filter((q) => q.inspection_id === inspId).length);
              setMsg(`Sync done: ${r.ok} uploaded, ${r.failed} failed`);
              refreshDetail();
            }}>Sync now</Btn>
          </div>
        </div>
      )}

      {assign && assign.blind && !revealed ? (
        <Envelope
          assign={assign}
          device={device}
          busy={busy}
          onDevice={doDeviceCheck}
          onActivate={doActivate}
        />
      ) : (
        <div className="stack">
          {project && (
            <div className="task-hero">
              <div className="row">
                <Chip tone="blue">Task revealed</Chip>
                <span className="mono">{full?.code ?? assign?.code}</span>
                <span className="caption">commitment {shortHash(revealed?.commitment_hash ?? full?.code)}</span>
              </div>
              <h2 style={{ margin: "10px 0 2px" }}>{project.name}</h2>
              <div className="caption">{project.org_name} · {project.scheme} · {project.address ?? ""}</div>
              <Kv rows={[
                ["Geofence reference", `${project.geofence_radius_m ?? 50} m`],
                ["Assignment kind", titleCase(revealed?.kind ?? full?.assignment_kind ?? "")],
                ["Arrival recorded", full?.arrival_at ? fmtTime(full.arrival_at) : "not yet"],
              ]} />
              <div className="row" style={{ marginTop: 10 }}>
                {(full?.status === "activated" || full?.status === "assigned" || assign?.status === "activated") &&
                  <Btn kind="primary" disabled={busy === "Starting"} onClick={doStart}>Start visit</Btn>}
                {!loc && project && (full?.status === "in_progress" || full?.status === "activated") && (
                  <>
                    <Btn small onClick={() => doLocation(project.lat, project.lng)}>Demo GPS: at site (inside geofence)</Btn>
                    <Btn small onClick={() => doLocation(project.lat + 0.02, project.lng)}>Demo GPS: 2 km away (outside)</Btn>
                  </>
                )}
                {loc && (
                  <div>
                    <Chip tone={loc.within_geofence ? "green" : "red"}>
                      {loc.within_geofence ? `Inside geofence (${Math.round(loc.distance_m)} m)` : `Outside geofence (${Math.round(loc.distance_m)} m)`}
                    </Chip>
                    <span className="caption"> validated server-side</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {checklist.length > 0 && full?.status !== "submitted" && (
            <Panel title="Field checklist" right={<Btn small onClick={saveChecklist} disabled={busy === "Saving"}>Save</Btn>}>
              <div className="stack">
                {checklist.map((c) => (
                  <label key={c.id} className="row" style={{ justifyContent: "flex-start" }}>
                    <input type="checkbox" checked={!!answers[c.id]}
                      onChange={(e) => setAnswers({ ...answers, [c.id]: e.target.checked })} />
                    <span>{c.item}</span>
                  </label>
                ))}
              </div>
            </Panel>
          )}

          {(full?.status === "in_progress" || full?.status === "activated" || full?.status === "assigned") && project && (
            <CapturePanel
              inspectionId={inspId}
              projectLat={project.lat}
              projectLng={project.lng}
              onUploaded={() => { refreshDetail(); }}
              offline={() => setPending(loadQueue().filter((q) => q.inspection_id === inspId).length)}
            />
          )}

          {(full?.evidence?.length ?? 0) > 0 && (
            <Panel title={`Captured evidence (${full?.evidence?.length ?? 0})`} bodyPad>
              <div className="row">
                {full?.evidence?.map((e) => (
                  <EvidenceThumb key={e.id} evidence={e} />
                ))}
              </div>
            </Panel>
          )}

          {full?.route_warnings && full.route_warnings.length > 0 && (
            <div className="error-box">Route integrity: {full.route_warnings.join("; ")}</div>
          )}

          {(full?.status === "in_progress") && (
            <Panel title="Submit report">
              <form className="stack" onSubmit={doSubmit}>
                <Field label="Field notes (what you verified)">
                  <textarea name="notes" rows={4} className="field" placeholder="Observed headcount, register status, QR scanning in use…" />
                </Field>
                <Btn kind="primary" type="submit" disabled={busy === "Submitting"}>Submit for review</Btn>
              </form>
            </Panel>
          )}
          {full?.status === "submitted" && <Ok message="Submitted. An authorised official will review the evidence and complete the inspection." />}
        </div>
      )}
    </div>
  );
}

function Envelope({ assign, device, busy, onDevice, onActivate }: {
  assign: BlindAssignment; device: any; busy: string;
  onDevice: () => void; onActivate: () => void;
}) {
  return (
    <Panel title="Blind assignment envelope (sealed)">
      <div className="stack">
        <p className="muted" style={{ marginTop: 0 }}>
          This task was assigned today via an auditable random draw. The target project,
          location and checklist are sealed until you pass the device-integrity check
          and activate the envelope. Future schedules are never visible.
        </p>
        <Kv rows={[
          ["Assignment code", assign.code],
          ["Kind", titleCase(assign.assignment_kind)],
          ["Assigned inspector", assign.inspector_name ?? "—"],
          ["Reason", assign.reason ?? "sealed"],
        ]} />
        {!device && <Btn kind="primary" disabled={!!busy} onClick={onDevice}>Run device-integrity check</Btn>}
        {device && (
          <div>
            <Chip tone={device.verdict === "pass" ? "green" : "red"}>
              Device check: {device.verdict}
            </Chip>
            <span className="caption"> (simulated Play Integrity signals)</span>
          </div>
        )}
        {device?.verdict === "pass" && (
          <Btn kind="primary" onClick={onActivate} disabled={!!busy}>Open envelope (reveal task)</Btn>
        )}
        {device?.verdict === "fail" && <Err message="Device integrity failed — activation blocked." />}
      </div>
    </Panel>
  );
}

function EvidenceThumb({ evidence }: { evidence: any }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let dead = false;
    requestBlob(`/api/evidence/${evidence.id}/file`)
      .then((b) => { if (!dead) setUrl(URL.createObjectURL(b)); })
      .catch(() => undefined);
    return () => { dead = true; if (url) URL.revokeObjectURL(url); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evidence.id]);
  return (
    <div className="thumb">
      {url ? <img src={url} alt="Evidence capture" width={84} height={63} loading="lazy" /> : <div style={{ height: 63, background: "var(--muted-2)" }} />}
      <div className="caption" style={{ padding: "2px 4px" }}>
        <Chip tone={evidence.geofence_ok ? "green" : evidence.geofence_ok === false ? "red" : "neutral"}>
          {evidence.geofence_ok ? "geo ok" : evidence.geofence_ok === false ? "out" : "n/a"}
        </Chip>{" "}
        <span className="mono">{shortHash(evidence.sha256, 8)}</span>
      </div>
    </div>
  );
}

function CapturePanel({ inspectionId, projectLat, projectLng, onUploaded, offline }: {
  inspectionId: number; projectLat: number; projectLng: number;
  onUploaded: () => void; offline: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [snap, setSnap] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function startCam() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      setStream(s);
    } catch { setErr("Camera unavailable — use the demo-simulated capture below."); }
  }
  useEffect(() => {
    if (stream && videoRef.current) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => undefined);
    }
    return () => stream?.getTracks().forEach((t) => t.stop());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream]);

  function snapshotCanvas() {
    const canvas = document.createElement("canvas");
    canvas.width = 640; canvas.height = 480;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#2563eb"; ctx.fillRect(0, 0, 640, 480);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 26px sans-serif";
    ctx.fillText("DEMO SIMULATED SITE PHOTO", 60, 200);
    ctx.font = "18px sans-serif";
    ctx.fillText(`omniwatch · ${new Date().toISOString()} · geo ${projectLat.toFixed(5)}, ${projectLng.toFixed(5)}`, 60, 250);
    return canvas;
  }

  async function capture(source: "live" | "demo") {
    setBusy(true); setErr("");
    let file: File;
    if (source === "demo") {
      const canvas = snapshotCanvas();
      const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", 0.85));
      file = new File([blob ?? new Blob()], "demo.jpg", { type: "image/jpeg" });
    } else {
      if (!videoRef.current) { setErr("Start the camera first"); setBusy(false); return; }
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current.videoWidth || 640;
      canvas.height = videoRef.current.videoHeight || 480;
      canvas.getContext("2d")!.drawImage(videoRef.current, 0, 0);
      const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", 0.9));
      file = new File([blob ?? new Blob()], "live.jpg", { type: "image/jpeg" });
    }
    try {
      if (navigator.onLine) {
        const form = new FormData();
        form.append("file", file);
        form.append("kind", "photo");
        form.append("source", source === "live" ? "live_camera" : "demo_simulated");
        form.append("lat", String(projectLat));
        form.append("lng", String(projectLng));
        form.append("captured_at", new Date().toISOString());
        const resp = await fetch(`/api/inspections/${inspectionId}/evidence`, {
          method: "POST",
          headers: { Authorization: `Bearer ${sessionStorage.getItem("ow_access_token") ?? ""}` },
          body: form,
        });
        if (!resp.ok) throw new Error((await resp.json().catch(() => ({ detail: "upload failed" }))).detail);
        setSnap(URL.createObjectURL(file));
        onUploaded();
      } else {
        await enqueueItem("photo", file, inspectionId, { lat: projectLat, lng: projectLng });
        offline();
        setErr("Offline — photo queued for sync.");
      }
    } catch (e) { setErr(apiErrorText(e)); } finally { setBusy(false); }
  }

  return (
    <Panel title="Live geo/time-bound capture">
      <div className="grid cols-2">
        <div>
          <div className="capture-zone">
            {snap ? <img src={snap} alt="capture" /> : stream ? <video ref={videoRef} muted playsInline /> : <Empty text="Camera preview" />}
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            {!stream && <Btn onClick={startCam}>Open live camera</Btn>}
            {stream && <Btn kind="primary" onClick={() => capture("live")} disabled={busy}>Capture live photo</Btn>}
            <Btn onClick={() => capture("demo")} disabled={busy} title="Clearly labelled demo-simulated capture">
              Demo capture (simulated)
            </Btn>
          </div>
          {err && <Err message={err} />}
          <p className="caption">Photos are captured inside the app only — gallery uploads are rejected server-side. Timestamp, GPS and inspection ID are hashed into the evidence chain.</p>
        </div>
        <div className="stack">
          <div className="flow"><span className="node">Capture</span><span className="arrow">→</span>
            <span className="node">SHA-256</span><span className="arrow">→</span>
            <span className="node human">Chain-of-custody</span></div>
          {stream && (
            <div className="row"><Chip tone="blue">camera live</Chip>
              <span className="caption">geotag: demo GPS at site pin</span></div>
          )}
        </div>
      </div>
    </Panel>
  );
}

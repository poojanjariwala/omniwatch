import { useState } from "react";
import { Chip, Err, Panel, Btn, Field, Empty } from "../../components/ui";
import { apiErrorText, request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, titleCase } from "../../lib/format";

interface Camera { id: number; project_id: number; project_name?: string; name: string;
  source_type: string; enabled: boolean; ingest_every_seconds: number; last_ingest_at?: string;
  last_frame_count?: number | null; last_error?: string | null; }
interface CctvEv { id: number; camera_id: number; ts: string; occupancy: number; items_handed: number | null;
  processed_by: string; }

export default function GovCctv() {
  const cams = useGet<{ cameras: Camera[] }>("/api/cctv", [], { pollMs: 20000 });
  const [active, setActive] = useState<Camera | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [showNew, setShowNew] = useState(false);

  const events = useGet<{ events: CctvEv[] }>(
    active ? `/api/cctv/${active.id}/events?limit=80` : "/api/cctv/events?limit=120", [active?.id],
  );

  async function toggle(c: Camera) {
    try {
      await request(`/api/cctv/${c.id}/toggle`, { method: "POST" });
      cams.refetch();
    } catch (e) { setMsg(apiErrorText(e)); }
  }

  async function ingest(c: Camera) {
    setBusy(true); setMsg("");
    try {
      const r = await request<any>(`/api/cctv/${c.id}/ingest`, { method: "POST" });
      setMsg(`Ingested: occupancy ${r.occupancy}, baseline ${r.baseline_ewma}, flagged=${!!r.flagged}`);
      cams.refetch();
      if (active?.id === c.id) events.refetch();
    } catch (e) { setMsg(apiErrorText(e)); } finally { setBusy(false); }
  }

  const occSeries = (events.data?.events ?? []).slice().reverse().map((e) => e.occupancy);
  const maxOcc = Math.max(10, ...occSeries);

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>CCTV & AI events</h1>
        <Btn kind="primary" onClick={() => setShowNew(true)}>Add camera</Btn>
      </div>
      {msg && <div className="ok-box">{msg}</div>}
      <Panel title={`Cameras (${cams.data?.cameras.length ?? 0})`} bodyPad={false}>
        <table className="tbl">
          <thead><tr><th>Camera</th><th>Project</th><th>Source</th><th>Ingest</th><th>Last ingest</th>
            <th>Last count</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {(cams.data?.cameras ?? []).map((c) => (
              <tr key={c.id} className={active?.id === c.id ? "" : "rowlink"}
                onClick={() => setActive(c)}>
                <td><b>{c.name}</b>{c.last_error && <div className="error-box">{c.last_error}</div>}</td>
                <td>{c.project_name ?? c.project_id}</td>
                <td><Chip tone="neutral">{titleCase(c.source_type)}</Chip></td>
                <td>{c.ingest_every_seconds}s</td>
                <td className="caption">{c.last_ingest_at ? fmtTime(c.last_ingest_at) : "never"}</td>
                <td>{c.last_frame_count ?? "—"}</td>
                <td><Chip tone={c.enabled ? "green" : "neutral"}>{c.enabled ? "on" : "off"}</Chip></td>
                <td>
                  <div className="row" onClick={(e) => e.stopPropagation()}>
                    <Btn small disabled={busy} onClick={() => ingest(c)}>Run ingest</Btn>
                    <Btn small onClick={() => toggle(c)}>{c.enabled ? "Disable" : "Enable"}</Btn>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!cams.loading && !cams.data?.cameras.length && <Empty text="No cameras configured" />}
      </Panel>

      <div className="grid cols-2">
        <Panel title={active ? `Event series — ${active.name}` : "Recent CCTV events"} bodyPad={false}>
          {occSeries.length > 1 && (
            <svg viewBox={`0 0 ${Math.max(120, occSeries.length * 6)} 60`} className="spark"
              preserveAspectRatio="none" style={{ width: "100%", height: 90, display: "block" }}>
              <polyline
                fill="none" stroke="#2563eb" strokeWidth="1.5"
                points={occSeries.map((o, i) => `${i * 6},${60 - (o / maxOcc) * 55}`).join(" ")}
              />
            </svg>
          )}
          <table className="tbl">
            <thead><tr><th>Time</th><th>Occupancy</th><th>Items handed</th><th>Engine</th></tr></thead>
            <tbody>
              {(events.data?.events ?? []).slice(0, 24).map((e) => (
                <tr key={e.id}>
                  <td className="caption">{fmtTime(e.ts)}</td>
                  <td><b>{e.occupancy}</b></td>
                  <td>{e.items_handed ?? "—"}</td>
                  <td><Chip tone="neutral">{e.processed_by}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
          {events.error && <Err message={events.error} />}
        </Panel>
        <Panel title="How the anomaly engine explains signals" bodyPad>
          <p className="muted" style={{ marginTop: 0 }}>
            Each ingest window is compared against the project's adaptive EWMA baseline.
            Sustained deviations raise an <b>explainable alert</b> — never a verdict.
          </p>
          <ul className="siglist">
            <li>Occupancy observed vs baseline × ratio</li>
            <li>Tip-off burst rule (rate of entry)</li>
            <li>Items handed across the desk tripwire (LineZone)</li>
            <li>Alert cards show what / when / where / signals / recommended verification</li>
          </ul>
          <Field label="Detector backend">
            <div className="row"><Chip tone="blue">YOLOv8 + ByteTrack</Chip>
              <Chip tone="neutral">supervision LineZone</Chip>
              <Chip tone="neutral">simulator fallback (CV_MODE=auto)</Chip></div>
          </Field>
        </Panel>
      </div>

      {showNew && <CameraForm onClose={() => setShowNew(false)} onDone={() => { cams.refetch(); setShowNew(false); }} />}
    </div>
  );
}

function CameraForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const projects = useGet<{ projects: any[] }>("/api/projects");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setMsg("");
    const fd = new FormData(e.currentTarget);
    try {
      await request("/api/cctv", { method: "POST", json: {
        project_id: Number(fd.get("project_id")),
        name: String(fd.get("name")),
        source_type: String(fd.get("source_type")),
        url: String(fd.get("url") || "") || null,
        ingest_every_seconds: Number(fd.get("ingest") || 30),
      } });
      onDone();
    } catch (err: any) { setMsg(err.message); } finally { setBusy(false); }
  }
  return (
    <div className="panel">
      <div className="panel-head"><span className="panel-title">Configure camera</span>
        <Btn small onClick={onClose}>✕</Btn></div>
      <form className="panel-body grid cols-3" onSubmit={submit}>
        <Field label="Project"><select name="project_id" className="field" required>
          {(projects.data?.projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
        </select></Field>
        <Field label="Camera name"><input name="name" className="field" required /></Field>
        <Field label="Source type"><select name="source_type" className="field">
          <option value="simulator">Simulator (demo)</option>
          <option value="file">Video file</option><option value="rtsp">RTSP stream</option>
          <option value="mjpeg">MJPEG</option>
        </select></Field>
        <Field label="URL (file path / rtsp:// ...)"><input name="url" className="field" placeholder="/data/clip.mp4" /></Field>
        <Field label="Ingest every (s)"><input name="ingest" type="number" className="field" defaultValue={30} /></Field>
        <div className="row" style={{ alignSelf: "end" }}>
          <Btn kind="primary" type="submit" disabled={busy}>Save camera</Btn>
          {msg && <Err message={msg} />}
        </div>
      </form>
    </div>
  );
}

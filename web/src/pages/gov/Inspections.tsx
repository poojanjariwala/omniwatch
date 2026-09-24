import { useEffect, useState } from "react";
import { Chip, Err, Kv, Modal, Panel, Btn, Field, Empty, TrustRow } from "../../components/ui";
import { requestBlob } from "../../lib/api";
import { apiErrorText, request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, shortHash, statusTone, titleCase } from "../../lib/format";

interface Insp {
  id: number; code: string; status: string; assignment_kind: string;
  assigned_inspector_id: number; inspector_name?: string | null;
  created_at?: string; activated_at?: string; arrival_at?: string | null;
  submitted_at?: string | null; reason?: string | null; blind?: boolean;
  project?: { code?: string; name?: string; risk_status?: string } | null;
  evidence?: Array<any>; route_timeline?: Array<any>; route_warnings?: string[];
  commitment_hash?: string | null; verification_passed?: boolean | null;
}

export default function GovInspections() {
  const list = useGet<{ inspections: Insp[] }>("/api/inspections", [], { pollMs: 20000 });
  const projects = useGet<{ projects: Array<{ id: number; code: string; name: string }> }>("/api/projects");
  const [sel, setSel] = useState<Insp | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function dispatch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setMsg("");
    const fd = new FormData(e.currentTarget);
    try {
      const r = await request<any>("/api/inspections/dispatch", {
        method: "POST",
        json: {
          project_id: Number(fd.get("project_id")),
          kind: String(fd.get("kind")),
          reason: String(fd.get("reason") || ""),
        },
      });
      setMsg(`Assigned ${r.inspection.code} → ${r.inspection.inspector_name ?? `inspector #${r.inspection.assigned_inspector_id}`}. ${r.assignment.method} draw, nonce ${r.assignment.nonce.slice(0, 10)}…`);
      list.refetch();
    } catch (err: any) { setMsg(err.message); } finally { setBusy(false); }
  }

  return (
    <div className="stack">
      <div className="row spread"><h1 style={{ margin: 0 }}>Inspections & dispatch</h1></div>
      <Panel title="Dispatch a blind inspection (auditable random + proximity)">
        <form className="grid cols-3" onSubmit={dispatch}>
          <Field label="Project"><select name="project_id" className="field" required>
            {(projects.data?.projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
          </select></Field>
          <Field label="Assignment kind"><select name="kind" className="field">
            <option value="risk_priority">Risk priority / random hybrid</option>
            <option value="random_surge">Random surge follow-up</option>
            <option value="spot_check">Random spot check</option>
            <option value="scheduled">Scheduled</option>
          </select></Field>
          <Field label="Reason"><input name="reason" className="field" /></Field>
          <div className="row" style={{ gridColumn: "1 / -1" }}>
            <Btn kind="primary" type="submit" disabled={busy}>Dispatch (sealed until activation)</Btn>
            {msg && <div className="ok-box">{msg}</div>}
          </div>
        </form>
      </Panel>

      <Panel title={`Open inspections (${list.data?.inspections.length ?? 0})`} bodyPad={false}>
        <table className="tbl">
          <thead><tr><th>Code</th><th>Kind</th><th>Project</th><th>Inspector</th><th>Status</th>
            <th>Blind</th><th>Assigned</th><th>Verification</th></tr></thead>
          <tbody>
            {(list.data?.inspections ?? []).filter((i) => !["completed", "cancelled"].includes(i.status)).map((i) => (
              <tr key={i.id} className="rowlink" onClick={() => setSel(i)}>
                <td className="mono">{i.code}</td>
                <td>{titleCase(i.assignment_kind)}</td>
                <td>{i.project?.name ?? "—"}</td>
                <td>{i.inspector_name ?? `#${i.assigned_inspector_id}`}</td>
                <td><Chip tone={statusTone(i.status)}>{i.status}</Chip></td>
                <td><Chip tone={i.blind ? "amber" : "green"}>{i.blind ? "sealed" : "open"}</Chip></td>
                <td className="caption">{fmtTime(i.created_at)}</td>
                <td>{i.verification_passed == null ? "—" : i.verification_passed ? <Chip tone="green">passed</Chip> : <Chip tone="red">failed</Chip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!list.loading && !list.data?.inspections.filter((i) => i.status !== "completed").length && <Empty text="No open inspections" />}
        {list.error && <Err message={list.error} />}
      </Panel>

      {sel && (
        <Modal title={`Inspection ${sel.code}`} wide onClose={() => setSel(null)}>
          <div className="grid cols-2-1">
            <div className="stack">
              <div className="row">
                <Chip tone={statusTone(sel.status)}>{sel.status}</Chip>
                <Chip tone="neutral">{titleCase(sel.assignment_kind)}</Chip>
                <Chip tone={sel.blind ? "amber" : "green"}>{sel.blind ? "blind envelope sealed" : "task revealed"}</Chip>
                <span className="mono caption">commit {shortHash(sel.commitment_hash)}</span>
              </div>
              <h3 style={{ margin: 0 }}>{sel.project?.name ?? "—"}</h3>
              <div className="caption">{sel.project?.code} · reason: {sel.reason ?? "—"}</div>
              <TrustRow states={[
                { label: "Authenticated", ok: true },
                { label: "Device verified", ok: !!sel.activated_at },
                { label: "Location verified", ok: !!sel.arrival_at },
                { label: "Submitted", ok: sel.status === "submitted" || sel.status === "completed" },
              ]} />
              {(sel.route_warnings?.length ?? 0) > 0 && (
                <div className="error-box">Route integrity warnings: {sel.route_warnings?.join("; ")}</div>
              )}
              <Panel title="Route integrity timeline" bodyPad={false}>
                <table className="tbl">
                  <thead><tr><th>Event</th><th>Time</th><th>Within geofence</th><th>Distance</th></tr></thead>
                  <tbody>
                    <tr><td>Assigned (blind)</td><td className="caption">{fmtTime(sel.created_at)}</td><td>—</td><td>—</td></tr>
                    <tr><td>Activated (envelope opened)</td><td className="caption">{fmtTime(sel.activated_at)}</td><td>—</td><td>—</td></tr>
                    <tr><td>First geofence arrival</td><td className="caption">{fmtTime(sel.arrival_at)}</td><td><Chip tone="green">inside</Chip></td><td>≤ radius</td></tr>
                    <tr><td>Submitted</td><td className="caption">{fmtTime(sel.submitted_at)}</td><td>—</td><td>—</td></tr>
                    {(sel.route_timeline ?? []).filter((l) => !l.within_geofence).slice(0, 6).map((l: any, i: number) => (
                      <tr key={`o${i}`}>
                        <td>Location ping (outside)</td><td className="caption">{fmtTime(l.ts)}</td>
                        <td><Chip tone="red">outside</Chip></td>
                        <td className="caption">{l.distance_m ? `${Math.round(l.distance_m)} m` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            </div>
            <div className="stack">
              <Kv rows={[
                ["Inspector", sel.inspector_name ?? "—"],
                ["Evidence items", String(sel.evidence?.length ?? 0)],
                ["Geofence", `${sel.project ? "50 m (reference)" : "—"}`],
                ["Checklist", "see field report"],
              ]} />
              <Panel title="Evidence thumbnails" bodyPad>
                {(sel.evidence ?? []).length === 0 && <Empty text="No evidence uploaded" />}
                <div className="row">
                  {(sel.evidence ?? []).map((e) => (
                    <EvidenceThumb key={e.id} evidence={e} />
                  ))}
                </div>
              </Panel>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function EvidenceThumb({ evidence }: { evidence: any }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let dead = false;
    requestBlob(`/api/evidence/${evidence.id}/file`)
      .then((b) => { if (!dead) setUrl(URL.createObjectURL(b)); })
      .catch(() => undefined);
    return () => { dead = true; };
  }, [evidence.id]);
  return (
    <div className="thumb">
      {url ? <img src={url} alt="evidence" width={84} height={63} loading="lazy" /> : <div style={{ height: 63, background: "var(--muted-2)" }} />}
      <div className="caption" style={{ padding: "2px 4px" }}>
        geo {evidence.geofence_ok ? "ok" : "out"} · <span className="mono">{shortHash(evidence.sha256, 8)}</span>
      </div>
    </div>
  );
}

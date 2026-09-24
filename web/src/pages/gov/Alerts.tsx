import { useState } from "react";
import { Chip, Err, Kv, Modal, Panel, Btn, Field, Ok } from "../../components/ui";
import { apiErrorText, request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, sevTone, statusTone, titleCase } from "../../lib/format";

interface Alert {
  id: number; code: string; kind: string; severity: string; title: string; summary: string;
  project_id: number | null; project_name?: string; occurred_at: string;
  signals: Array<{ type: string; [k: string]: any }>; risk_signal: number;
  recommended_action: string; status: string; feedback?: string; case_id?: number | null;
  ai_generated?: boolean;
}

export default function GovAlerts() {
  const { data, error, loading, refetch } = useGet<{ alerts: Alert[] }>("/api/alerts", [], { pollMs: 15000 });
  const [sel, setSel] = useState<Alert | null>(null);
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");

  async function act(fn: () => Promise<unknown>, okMsg: string) {
    setMsg("");
    try {
      await fn();
      setMsg(okMsg);
      refetch();
    } catch (e) { setMsg(apiErrorText(e)); }
  }

  const alerts = (data?.alerts ?? []).filter(
    (a) => (!kind || a.kind === kind) && (!status || a.status === status),
  );

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Alert queue</h1>
        <div className="row">
          <select className="field" style={{ width: 160 }} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            {Array.from(new Set((data?.alerts ?? []).map((a) => a.kind))).map((k) => (
              <option key={k} value={k}>{titleCase(k)}</option>
            ))}
          </select>
          <select className="field" style={{ width: 150 }} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {["open", "in_review", "verifying", "action_taken", "closed"].map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>
      {error && <Err message={error} />}
      <Panel title={`Alerts (${alerts.length})`} bodyPad={false}>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead><tr>
              <th>Severity</th><th>Project</th><th>What happened</th><th>Time</th>
              <th>Location</th><th>Signals</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id} className="rowlink" onClick={() => { setSel(a); setNote(""); }}>
                  <td><Chip tone={sevTone(a.severity)}>{a.severity}</Chip></td>
                  <td>{a.project_name ?? "—"}</td>
                  <td style={{ maxWidth: 340 }}>
                    <b>{a.title}</b>
                    <div className="caption">{a.summary}</div>
                  </td>
                  <td className="caption">{fmtTime(a.occurred_at)}</td>
                  <td className="mono caption">{(a as any).location ? `${(a as any).location.lat?.toFixed(4)}, ${(a as any).location.lng?.toFixed(4)}` : "—"}</td>
                  <td><Chip tone="neutral">{a.signals?.length ?? 0} signals</Chip></td>
                  <td><Chip tone={statusTone(a.status)}>{a.status}</Chip></td>
                  <td><Btn small onClick={(e) => { e?.stopPropagation(); setSel(a); }}>Review</Btn></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !alerts.length && <div className="empty">No alerts match the filters</div>}
      </Panel>

      {sel && (
        <Modal title={`Alert ${sel.code}`} wide onClose={() => setSel(null)}>
          <div className="grid cols-2-1">
            <div className="stack">
              <div className="row">
                <Chip tone={sevTone(sel.severity)}>{sel.severity}</Chip>
                <Chip tone="neutral">{titleCase(sel.kind)}</Chip>
                <Chip tone={statusTone(sel.status)}>{sel.status}</Chip>
                <span className="caption">{fmtTime(sel.occurred_at)}</span>
              </div>
              <h3 style={{ margin: 0 }}>{sel.title}</h3>
              <p style={{ margin: 0 }}>{sel.summary}</p>
              {sel.feedback && <Chip tone="blue">Model feedback: {sel.feedback}</Chip>}
              <Field label="What · where · when">
                <ul className="siglist">
                  {sel.signals?.map((s, i) => (
                    <li key={i}>
                      <b>{titleCase(s.type)}</b> — {Object.entries(s)
                        .filter(([k]) => k !== "type")
                        .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
                        .join(" · ")}
                    </li>
                  ))}
                </ul>
              </Field>
              <Field label="Recommended verification">
                <div className="ok-box">{sel.recommended_action || "Human review required."}</div>
              </Field>
            </div>
            <div className="stack">
              <Kv rows={[
                ["Risk signal", sel.risk_signal?.toFixed(2) ?? "—"],
                ["AI generated", sel.ai_generated ? "yes (advisory)" : "no"],
                ["Case", sel.case_id ? `#${sel.case_id}` : "none"],
              ]} />
              <Btn onClick={() => act(async () => {
                await request(`/api/alerts/${sel.id}/status`, { method: "PATCH", json: { to_status: "in_review", note } });
                setSel({ ...sel, status: "in_review" });
              }, "Moved to review")}>Mark in review</Btn>
              <Btn kind="primary" onClick={() => act(async () => {
                await request(`/api/alerts/${sel.id}/dispatch`, { method: "POST", json: { note } });
                setSel({ ...sel, status: "verifying" });
              }, "Blind inspection dispatched (auditable)")}>Dispatch blind inspection</Btn>
              <Btn onClick={() => act(async () => {
                const r = await request<{ case_code: string }>(`/api/cases?alert_id=${sel.id}&note=${encodeURIComponent(note)}`, { method: "POST" });
                setSel({ ...sel, case_id: sel.case_id ?? -1 });
                setMsg(`Case opened: ${r.case_code}`);
              }, "Case opened")}>Open case</Btn>
              <Field label="Decision note"><textarea className="field" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
              <div className="row">
                <Btn small onClick={() => act(async () => {
                  await request(`/api/alerts/${sel.id}/feedback`, { method: "POST", json: { feedback: "true_positive", note } });
                }, "Feedback recorded (TP)")}>True positive</Btn>
                <Btn small onClick={() => act(async () => {
                  await request(`/api/alerts/${sel.id}/feedback`, { method: "POST", json: { feedback: "false_positive", note } });
                }, "Feedback recorded (FP)")}>False positive</Btn>
                <Btn small onClick={() => act(async () => {
                  await request(`/api/alerts/${sel.id}/feedback`, { method: "POST", json: { feedback: "inconclusive", note } });
                }, "Feedback recorded")}>Inconclusive</Btn>
              </div>
            </div>
          </div>
          {msg && <Ok message={msg} />}
        </Modal>
      )}
    </div>
  );
}

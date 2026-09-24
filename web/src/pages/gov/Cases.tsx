import { useState } from "react";
import { Chip, Err, Kv, Modal, Panel, Btn, Empty } from "../../components/ui";
import ReauthBtn from "../../components/ReauthBtn";
import { request, requestBlob, apiErrorText } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, shortHash, statusTone, titleCase } from "../../lib/format";

interface CaseRow { id: number; code: string; title: string; status: string;
  project_id: number | null; project_name?: string | null; opened_at: string;
  alert_count: number; evidence_count: number; inspection_count: number;
  closure_action?: string | null; closure_note?: string | null; }
interface CaseDetail {
  case: CaseRow; alerts: any[]; inspections: any[]; evidence: any[]; timeline: any[];
}

export default function GovCases() {
  const cases = useGet<{ cases: CaseRow[] }>("/api/cases", [], { pollMs: 20000 });
  const alerts = useGet<{ alerts: any[] }>("/api/alerts");
  const [selId, setSelId] = useState<number | null>(null);
  const detail = useGet<CaseDetail | null>(selId ? `/api/cases/${selId}` : "", [selId]);
  const [msg, setMsg] = useState("");
  const [openCaseAlert, setOpenCaseAlert] = useState<number | null>(null);
  const [note, setNote] = useState("");

  async function openNewCase() {
    if (openCaseAlert == null) return;
    try {
      const r = await request<{ case_id: number }>(
        `/api/cases?alert_id=${openCaseAlert}&note=${encodeURIComponent(note)}`,
        { method: "POST" });
      setMsg(`Case opened: ${r.case_id}`);
      setOpenCaseAlert(null);
      cases.refetch();
    } catch (e) { setMsg(apiErrorText(e)); }
  }

  async function downloadDossier() {
    if (!selId) return;
    try {
      const blob = await requestBlob(`/api/cases/${selId}/report`, { sensitive: true });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `dossier-case-${selId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setMsg(apiErrorText(e)); }
  }

  const d = detail.data as CaseDetail | null;

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Cases & audit reports</h1>
        <Btn kind="primary" onClick={() => setOpenCaseAlert(-1)}>Open case from alert</Btn>
      </div>
      {msg && <div className="ok-box">{msg}</div>}
      <Panel title={`Cases (${cases.data?.cases.length ?? 0})`} bodyPad={false}>
        <table className="tbl">
          <thead><tr><th>Case</th><th>Project</th><th>Alerts</th><th>Evidence</th><th>Inspections</th>
            <th>Opened</th><th>Status</th></tr></thead>
          <tbody>
            {(cases.data?.cases ?? []).map((c) => (
              <tr key={c.id} className="rowlink" onClick={() => setSelId(c.id)}>
                <td><b>{c.title}</b><div className="mono caption">{c.code}</div></td>
                <td>{c.project_name ?? "—"}</td>
                <td>{c.alert_count}</td><td>{c.evidence_count}</td><td>{c.inspection_count}</td>
                <td className="caption">{fmtTime(c.opened_at)}</td>
                <td><Chip tone={statusTone(c.status)}>{c.status}</Chip></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!cases.loading && !cases.data?.cases.length && <Empty text="No cases — raise one from an alert" />}
        {cases.error && <Err message={cases.error} />}
      </Panel>

      {openCaseAlert === -1 && (
        <Modal title="Open a case from an alert" onClose={() => setOpenCaseAlert(null)}>
          <select className="field" value={openCaseAlert ?? -1} onChange={(e) => setOpenCaseAlert(Number(e.target.value) || -1)}>
            {(alerts.data?.alerts ?? []).filter((a) => !a.case_id).slice(0, 30).map((a: any) => (
              <option key={a.id} value={a.id}>{a.code} — {a.title}</option>
            ))}
          </select>
          <input className="field" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Btn kind="primary" disabled={openCaseAlert === -1} onClick={openNewCase}>Open case</Btn>
        </Modal>
      )}

      {selId && d && (
        <Modal title={`Case ${d.case.code}`} wide onClose={() => setSelId(null)}>
          <div className="row">
            <Chip tone={statusTone(d.case.status)}>{d.case.status}</Chip>
            <Chip tone="neutral">{d.case.project_name ?? "—"}</Chip>
            <span className="caption">opened {fmtTime(d.case.opened_at)}</span>
          </div>
          <div className="humandivider">
            AI detect · prioritise · explain → <b>authorised official verify · decide · escalate</b>.
            Case closure requires password re-authentication.
          </div>
          <h3 style={{ margin: "8px 0" }}>Timeline</h3>
          <div className="chain-timeline" style={{ maxHeight: 300, overflow: "auto" }}>
            {d.timeline.map((t: any, i: number) => (
              <div key={i} className="chain-item">
                <Chip tone="neutral">{t.kind}</Chip> <span className="caption">{fmtTime(t.at)}</span>
                <div style={{ fontSize: 13 }}>{t.text}</div>
              </div>
            ))}
          </div>
          <div className="grid cols-2">
            <Panel title="Linked alerts" bodyPad>
              {(d.alerts ?? []).map((a: any) => (
                <div key={a.id} className="caption" style={{ padding: "3px 0" }}>
                  {a.code} — {a.title} ({a.status})
                </div>
              ))}
            </Panel>
            <Panel title="Evidence hashes" bodyPad>
              {(d.evidence ?? []).map((e: any) => (
                <div key={e.id} className="mono caption" style={{ padding: "2px 0" }}>
                  ev-{e.id} {shortHash(e.sha256, 16)}
                </div>
              ))}
            </Panel>
          </div>
          <div className="row spread">
            <ReauthBtn label="Generate PDF dossier (SHA-256)" onDone={async () => { await downloadDossier(); setMsg("Dossier generated — check your downloads"); }} />
            <ReauthBtn
              kind="danger"
              label="Close case (official decision)"
              onDone={async () => {
                await request(`/api/cases/${selId}/close`, {
                  method: "POST", sensitive: true,
                  json: { closure_action: "clear", closure_note: "Human decision after review" },
                });
                setMsg("Case closed — audit recorded");
                cases.refetch();
                setSelId(null);
              }}
            />
          </div>
          <Kv rows={[["Closed by", "authorised official only"], ["Closure", d.case.status === "closed" ? d.case.closure_action ?? "—" : "open"]]} />
        </Modal>
      )}
    </div>
  );
}

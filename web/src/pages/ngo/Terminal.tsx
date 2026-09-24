import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Chip, Empty, Err, Ok, Panel, Btn, Field, Modal } from "../../components/ui";
import { apiErrorText, request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, titleCase } from "../../lib/format";

interface Dist { id: number; code: string; title: string; distribution_date: string;
  status: string; consumed: number; total_items: number; project_id: number;
  project_name?: string | null; org_name?: string | null; }
interface CodeRow { id: number; code: string; serial: number; status: string;
  recipient_token?: string | null; consumed_at?: string | null; }
interface ScanLog { id: number; ok: boolean; reason: string; code?: string | null;
  created_at: string; actor_name?: string | null; }

export default function NgoTerminal() {
  const ov = useGet<any>("/api/dashboard/ngo-overview", [], { pollMs: 15000 });
  const dists = ov.data?.distributions ?? [];
  const projects = ov.data?.projects ?? [];
  const [distId, setDistId] = useState<number | null>(null);
  const [codes, setCodes] = useState<CodeRow[]>([]);
  const [logs, setLogs] = useState<ScanLog[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [scanning, setScanning] = useState<CodeRow | null>(null);
  const [recipient, setRecipient] = useState("");
  const [scanMsg, setScanMsg] = useState("");

  async function pickDist(id: number) {
    setDistId(id);
    setMsg(""); setErr("");
    const [c, l] = await Promise.all([
      request<{ codes: CodeRow[] }>(`/api/qr/distributions/${id}/codes`),
      request<{ logs: ScanLog[] }>(`/api/qr/scan-logs?distribution_id=${id}`),
    ]);
    setCodes(c.codes); setLogs(l.logs);
    const fresh = c.codes.find((x) => x.status === "issued");
    setScanning(fresh ?? null);
  }

  async function scan(row: CodeRow) {
    setBusy(`scan-${row.id}`); setScanMsg("");
    try {
      const r = await request<any>("/api/qr/scan", {
        method: "POST",
        json: { code: row.code, recipient_token: recipient || null },
      });
      if (r.ok) {
        setScanMsg(`Handout recorded: item #${r.serial} · ${r.consumed_today}/${r.total_items} today`);
        const fresh = await request<{ codes: CodeRow[] }>(`/api/qr/distributions/${distId}/codes`);
        setCodes(fresh.codes);
      } else {
        setScanMsg(`Blocked — ${titleCase(r.reason)}: ${r.message}`);
        ov.refetch();
        const fresh = await request<{ codes: CodeRow[] }>(`/api/qr/distributions/${distId}/codes`);
        setCodes(fresh.codes);
      }
      const l = await request<{ logs: ScanLog[] }>(`/api/qr/scan-logs?distribution_id=${distId}`);
      setLogs(l.logs);
    } catch (e) { setScanMsg(apiErrorText(e)); } finally { setBusy(""); }
  }

  const todayTotal = dists.reduce((s: number, d: Dist) => s + (d.consumed ?? 0), 0);

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>NGO terminal</h1>
        <div className="panel" style={{ padding: "8px 16px", textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{todayTotal}</div>
          <div className="caption">QR handouts recorded</div>
        </div>
      </div>
      <div className="ok-box">This interface shows operational records only. Risk scores, internal alerts and inspection schedules are never visible to NGO staff.</div>
      {err && <Err message={err} />}
      {msg && <Ok message={msg} />}

      <div className="grid cols-2">
        <Panel title="Active distributions" bodyPad={false}
          right={<CreateBatch onCreated={() => ov.refetch()} projects={projects} />}>
          <table className="tbl">
            <thead><tr><th>Distribution</th><th>Date</th><th>Handed out</th><th>Status</th></tr></thead>
            <tbody>
              {dists.map((d: Dist) => (
                <tr key={d.id} className={distId === d.id ? "" : "rowlink"}
                  onClick={() => pickDist(d.id)}>
                  <td>{d.title}<div className="caption">{d.code} · {d.project_name}</div></td>
                  <td className="caption">{d.distribution_date}</td>
                  <td>
                    <Chip tone={d.consumed >= d.total_items ? "green" : "amber"}>
                      {d.consumed}/{d.total_items}
                    </Chip>
                  </td>
                  <td><Chip tone="neutral">{d.status}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!ov.loading && !dists.length && <Empty text="No distributions yet" />}
        </Panel>

        <Panel title={distId ? "Scan console (desk terminal)" : "Select a distribution to scan"} bodyPad>
          {!distId && <Empty text="Pick a distribution on the left" />}
          {distId && (
            <div className="stack">
              {scanning ? (
                <>
                  <div className="row">
                    <QRCodeSVG value={scanning.code} size={120} level="M" />
                    <div>
                      <div><b>Item #{scanning.serial}</b></div>
                      <div className="mono caption">{scanning.code}</div>
                      <div className="caption">Recipient token (optional demo binding)</div>
                      <input className="field" value={recipient}
                        onChange={(e) => setRecipient(e.target.value)}
                        placeholder="e.g. BEN-001 (demo)" style={{ maxWidth: 200 }} />
                    </div>
                  </div>
                  <Btn kind="primary" onClick={() => scan(scanning)} disabled={!!busy}>
                    Scan this item (hand over)
                  </Btn>
                  {scanMsg && <div className={scanMsg.startsWith("Blocked") ? "error-box" : "ok-box"}>{scanMsg}</div>}
                </>
              ) : (
                <div className="ok-box">All items in this distribution have been handed out.</div>
              )}
              <div className="caption">Scanning is verified server-side — reused/replayed codes are blocked and logged for government review only.</div>
            </div>
          )}
        </Panel>
      </div>

      {distId && (
        <Panel title={`Item register — distribution #${distId}`} bodyPad={false}>
          <table className="tbl">
            <thead><tr><th>Serial</th><th>Status</th><th>Recipient token</th><th>Consumed at</th><th></th></tr></thead>
            <tbody>
              {codes.slice(0, 60).map((c) => (
                <tr key={c.id}>
                  <td className="mono">#{c.serial}</td>
                  <td><Chip tone={c.status === "consumed" ? "green" : "amber"}>{c.status}</Chip></td>
                  <td className="mono caption">{c.recipient_token ?? "—"}</td>
                  <td className="caption">{c.consumed_at ? fmtTime(c.consumed_at) : "—"}</td>
                  <td>{c.status === "issued" && <Btn small disabled={!!busy} onClick={() => scan(c)}>Hand over</Btn>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}

      {distId && (
        <Panel title="Recent scan attempts (success & error reasons)" bodyPad={false}>
          <table className="tbl">
            <thead><tr><th>Time</th><th>Code</th><th>Outcome</th><th>Reason</th></tr></thead>
            <tbody>
              {logs.slice(0, 25).map((l) => (
                <tr key={l.id}>
                  <td className="caption">{fmtTime(l.created_at)}</td>
                  <td className="mono caption">{l.code ?? "—"}</td>
                  <td><Chip tone={l.ok ? "green" : "red"}>{l.ok ? "success" : "blocked"}</Chip></td>
                  <td>{titleCase(l.reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!logs.length && <Empty text="No scans yet" />}
        </Panel>
      )}
    </div>
  );
}

function CreateBatch({ onCreated, projects }: { onCreated: () => void; projects: any[] }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setMsg("");
    const fd = new FormData(e.currentTarget);
    try {
      await request("/api/qr/batches", {
        method: "POST",
        json: {
          project_id: Number(fd.get("project_id")),
          title: String(fd.get("title")),
          count: Number(fd.get("count")),
        },
      });
      setOpen(false); onCreated();
    } catch (ex: any) { setMsg(ex.message); } finally { setBusy(false); }
  }
  if (!open) return <Btn small kind="primary" onClick={() => setOpen(true)}>Issue QR batch</Btn>;
  return (
    <Modal title="Issue a QR item batch" onClose={() => setOpen(false)}>
      <form className="stack" onSubmit={submit}>
        <Field label="Project (own organisation)"><select name="project_id" className="field" required>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></Field>
        <Field label="Batch title"><input name="title" className="field" required /></Field>
        <Field label="Number of items"><input name="count" type="number" min={1} max={5000} className="field" defaultValue={10} /></Field>
        {msg && <Err message={msg} />}
        <Btn kind="primary" type="submit" disabled={busy}>Issue codes</Btn>
      </form>
    </Modal>
  );
}

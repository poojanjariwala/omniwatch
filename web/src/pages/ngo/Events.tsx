import { useState } from "react";
import { Chip, Empty, Err, Ok, Panel, Btn, Field, Modal } from "../../components/ui";
import { apiErrorText, request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, statusTone } from "../../lib/format";

interface Ev { id: number; code: string; title: string; scheduled_at: string;
  registered_at: string; status: string; lat: number; lng: number;
  org_name?: string | null; project_id?: number | null; live_lat?: number | null;
  live_lng?: number | null; last_broadcast_at?: string | null; }

export default function NgoEvents() {
  const events = useGet<{ events: Ev[] }>("/api/events", [], { pollMs: 15000 });
  const ov = useGet<any>("/api/dashboard/ngo-overview");
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

  async function register(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy("register"); setMsg("");
    const fd = new FormData(e.currentTarget);
    const when = new Date(fd.get("scheduled_at") as string).toISOString();
    try {
      await request("/api/events", {
        method: "POST",
        json: {
          title: String(fd.get("title")),
          description: String(fd.get("description") || ""),
          project_id: Number(fd.get("project_id")) || null,
          lat: Number(fd.get("lat")), lng: Number(fd.get("lng")),
          scheduled_at: when,
          address: String(fd.get("address") || ""),
        },
      });
      setMsg("Event registered — awaiting government approval.");
      setOpen(false); events.refetch();
    } catch (ex) { setMsg(apiErrorText(ex)); } finally { setBusy(""); }
  }

  async function broadcast(ev: Ev) {
    setBusy(`b-${ev.id}`); setMsg("");
    try {
      await request(`/api/events/${ev.id}/broadcast`, {
        method: "POST", json: { lat: ev.lat, lng: ev.lng },
      });
      setMsg("Live location broadcast — event flagged for possible random spot-check.");
      events.refetch();
    } catch (ex) { setMsg(apiErrorText(ex)); } finally { setBusy(""); }
  }

  const defaultProject = ov.data?.projects?.[0];
  const defaultWhen = new Date(Date.now() + 3 * 86400e3).toISOString().slice(0, 16);

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Outdoor events</h1>
        <Btn kind="primary" onClick={() => setOpen(true)}>Register an outdoor event</Btn>
      </div>
      {msg && <Ok message={msg} />}
      <Panel title={`Registered events (${events.data?.events.length ?? 0})`} bodyPad={false}>
        <table className="tbl">
          <thead><tr><th>Event</th><th>Scheduled</th><th>Registered</th><th>Status</th><th>GPS</th><th>Broadcast</th></tr></thead>
          <tbody>
            {(events.data?.events ?? []).map((ev) => (
              <tr key={ev.id}>
                <td>{ev.title}<div className="mono caption">{ev.code}</div></td>
                <td className="caption">{fmtTime(ev.scheduled_at)}</td>
                <td className="caption">{fmtTime(ev.registered_at)}</td>
                <td><Chip tone={statusTone(ev.status)}>{ev.status}</Chip></td>
                <td className="mono caption">{ev.lat?.toFixed(5)}, {ev.lng?.toFixed(5)}</td>
                <td>
                  {ev.status === "approved" && (
                    <Btn small disabled={!!busy} onClick={() => broadcast(ev)}>Broadcast live location</Btn>
                  )}
                  {ev.last_broadcast_at && <span className="caption"> {fmtTime(ev.last_broadcast_at)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!events.loading && !events.data?.events.length && <Empty text="No events registered" />}
        {events.error && <Err message={events.error} />}
      </Panel>
      <p className="caption">Off-site distributions must be registered with the exact GPS location at least 48 hours in advance (reference rule). On event day, live location broadcast allows a random spot-check to be dispatched.</p>
      {open && (
        <Modal title="Register an outdoor event (48-h rule)" wide onClose={() => setOpen(false)}>
          <form className="grid cols-2" onSubmit={register}>
            <Field label="Event title"><input name="title" className="field" required placeholder="Village distribution camp" /></Field>
            <Field label="Project (optional)"><select name="project_id" className="field">
              <option value="">— none —</option>
              {(ov.data?.projects ?? []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></Field>
            <Field label="GPS latitude (pin)"><input name="lat" step="any" className="field" required defaultValue={defaultProject?.lat} /></Field>
            <Field label="GPS longitude (pin)"><input name="lng" step="any" className="field" required defaultValue={defaultProject?.lng} /></Field>
            <Field label="Start time (≥48 h ahead)"><input name="scheduled_at" type="datetime-local" className="field" required defaultValue={defaultWhen} /></Field>
            <Field label="Address"><input name="address" className="field" /></Field>
            <Field label="Description"><input name="description" className="field" /></Field>
            <div className="row" style={{ alignSelf: "end" }}>
              <Btn kind="primary" type="submit" disabled={busy === "register"}>Register</Btn>
            </div>
          </form>
          <Err message={msg} />
        </Modal>
      )}
    </div>
  );
}

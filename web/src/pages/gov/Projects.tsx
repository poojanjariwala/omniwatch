import { useState } from "react";
import { Chip, Empty, Err, Panel, Btn, Field } from "../../components/ui";
import { request } from "../../lib/api";
import { useGet } from "../../lib/hooks";
import { fmtTime, riskTone, titleCase } from "../../lib/format";

interface Project {
  id: number; code: string; name: string; scheme: string; category: string;
  address?: string | null; lat: number; lng: number; status: string;
  reported_beneficiaries: number; risk_status?: string; risk_score?: number;
  risk_reason?: any; org_name?: string; camera_count?: number; open_alerts?: number;
  geofence_radius_m?: number; risk_last_update?: string; org_id?: number;
}

export default function GovProjects() {
  const { data, error, loading, refetch } = useGet<{ projects: Project[] }>("/api/projects");
  const [showNew, setShowNew] = useState(false);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  function openNew() {
    setShowNew(true);
    request<any[]>("/api/organizations").then(setOrgs).catch(() => setOrgs([]));
  }

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setMsg("");
    const fd = new FormData(e.currentTarget);
    try {
      await request("/api/projects", {
        method: "POST",
        json: {
          org_id: Number(fd.get("org_id")),
          code: String(fd.get("code")),
          name: String(fd.get("name")),
          scheme: String(fd.get("scheme")),
          category: String(fd.get("category")),
          address: String(fd.get("address") || ""),
          lat: Number(fd.get("lat")), lng: Number(fd.get("lng")),
          geofence_radius_m: Number(fd.get("radius") || 50),
          reported_beneficiaries: Number(fd.get("reported") || 0),
        },
      });
      setShowNew(false);
      refetch();
    } catch (err: any) {
      setMsg(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Project registry</h1>
        <Btn kind="primary" onClick={openNew}>Register project</Btn>
      </div>
      {error && <Err message={error} />}
      <Panel title={`Projects (${data?.projects.length ?? 0})`} bodyPad={false}>
        <table className="tbl">
          <thead><tr><th>Code</th><th>Project</th><th>Scheme</th><th>Category</th><th>Org</th>
            <th>Risk</th><th>Cameras</th><th>Open alerts</th><th>Reported</th><th>Updated</th></tr></thead>
          <tbody>
            {data?.projects.map((p) => (
              <tr key={p.id}>
                <td className="mono">{p.code}</td>
                <td>{p.name}<div className="caption">{p.address}</div></td>
                <td>{p.scheme}</td>
                <td><Chip tone="neutral">{titleCase(p.category)}</Chip></td>
                <td>{p.org_name ?? p.org_id}</td>
                <td>
                  <Chip tone={riskTone(p.risk_status ?? p.risk_score ?? 0)}>
                    {p.risk_status ?? "—"} {typeof p.risk_score === "number" ? `· ${p.risk_score.toFixed(2)}` : ""}
                  </Chip>
                </td>
                <td>{p.camera_count ?? 0}</td>
                <td><Chip tone={p.open_alerts ? "red" : "green"}>{p.open_alerts ?? 0}</Chip></td>
                <td>{p.reported_beneficiaries}</td>
                <td className="caption">{p.risk_last_update ? fmtTime(p.risk_last_update) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !data?.projects.length && <Empty />}
      </Panel>
      {showNew && (
        <div className="panel" style={{ position: "sticky", bottom: 0, zIndex: 10 }}>
          <div className="panel-head"><span className="panel-title">Register project (SAMPLE)</span>
            <Btn small onClick={() => setShowNew(false)}>Close</Btn></div>
          <form className="panel-body grid cols-3" onSubmit={create}>
            <Field label="Org"><select name="org_id" className="field" required>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select></Field>
            <Field label="Code"><input name="code" className="field" required placeholder="REG-XX" /></Field>
            <Field label="Name"><input name="name" className="field" required /></Field>
            <Field label="Scheme"><input name="scheme" className="field" required /></Field>
            <Field label="Category"><select name="category" className="field">
              <option value="centre">Centre</option><option value="distribution">Distribution</option>
              <option value="outdoor">Outdoor</option><option value="skill">Skill</option>
            </select></Field>
            <Field label="Reported beneficiaries"><input name="reported" type="number" className="field" /></Field>
            <Field label="Latitude"><input name="lat" step="any" className="field" required /></Field>
            <Field label="Longitude"><input name="lng" step="any" className="field" required /></Field>
            <Field label="Geofence radius (m)"><input name="radius" type="number" className="field" defaultValue={50} /></Field>
            <Field label="Address"><input name="address" className="field" /></Field>
            <div />
            <div className="row"><Btn kind="primary" type="submit" disabled={busy}>Create</Btn>{msg && <span className="error-box">{msg}</span>}</div>
          </form>
        </div>
      )}
    </div>
  );
}

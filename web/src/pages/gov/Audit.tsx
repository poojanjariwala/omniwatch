import { useState } from "react";
import { Chip, Empty, Err, Panel } from "../../components/ui";
import { useGet } from "../../lib/hooks";
import { fmtTime } from "../../lib/format";

export default function GovAudit() {
  const [action, setAction] = useState("");
  const { data, error, loading, refetch } = useGet<{ events: any[] }>(
    `/api/audit${action ? `?action=${action}` : ""}`, [action], { pollMs: 15000 });

  const actions = new Set((data?.events ?? []).map((e) => e.action));

  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>Audit log</h1>
      <div className="row">
        <span className="caption">Authentication, authorisation failures, assignments, evidence access and report generation are logged. Passwords and tokens are never logged.</span>
      </div>
      <Panel
        title={`Audit events (${data?.events.length ?? 0})`}
        bodyPad={false}
        right={
          <select className="field" style={{ width: 240 }} value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {Array.from(actions).map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        }
      >
        <table className="tbl">
          <thead><tr><th>Time</th><th>Actor</th><th>Role</th><th>Action</th><th>Object</th><th>ID</th><th>Detail</th></tr></thead>
          <tbody>
            {(data?.events ?? []).slice(0, 200).map((e) => (
              <tr key={e.id}>
                <td className="caption">{fmtTime(e.ts)}</td>
                <td>{e.actor_id ?? "system"}</td>
                <td><Chip tone="neutral">{e.actor_role ?? "—"}</Chip></td>
                <td><b>{e.action}</b></td>
                <td>{e.object_type}</td>
                <td className="mono caption">{e.object_id ?? "—"}</td>
                <td className="caption">{JSON.stringify(e.detail ?? {}).slice(0, 120)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {error && <Err message={error} />}
        {!loading && !data?.events.length && <Empty text="No audit events" />}
      </Panel>
    </div>
  );
}

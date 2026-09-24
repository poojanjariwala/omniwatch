import { useNavigate } from "react-router-dom";
import { Chip, Empty, Err, Panel, TrustRow } from "../../components/ui";
import { useGet } from "../../lib/hooks";
import { fmtTime, statusTone, titleCase } from "../../lib/format";

export default function InspectorTasks() {
  const nav = useNavigate();
  const { data, error, loading, refetch } = useGet("/api/inspections/mine", [], { pollMs: 15000 });
  const rows = (data as any)?.assignments ?? [];

  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <div className="row spread">
        <h1 style={{ margin: 0 }}>My assignments</h1>
        <span className="caption">Same-day blind assignments only — future schedules are never visible.</span>
      </div>
      <TrustRow states={[{ label: "Authenticated", ok: true },
        { label: "Device verified", ok: false }, { label: "Task sealed", ok: rows.every((r: any) => r.blind) }]} />
      {error && <Err message={error} />}
      <div className="stack">
        {rows.map((r: any) => (
          <div key={r.id} className="task-hero" onClick={() => nav(`/inspector/tasks/${r.id}`)}
            style={{ cursor: "pointer" }}>
            <div className="row spread">
              <div>
                <div className="row">
                  <Chip tone="amber">BLIND</Chip>
                  <span className="mono">{r.code}</span>
                  <Chip tone={statusTone(r.status)}>{r.status}</Chip>
                </div>
                <div className="caption" style={{ marginTop: 6 }}>
                  {titleCase(r.assignment_kind)} · assigned {fmtTime(r.assigned_at)}
                </div>
                {r.reason && <div className="caption">Context note sealed until activation.</div>}
              </div>
              <button className="btn primary">Open task envelope</button>
            </div>
          </div>
        ))}
        {!loading && rows.length === 0 && <Empty text="No assignments today" />}
      </div>
    </div>
  );
}

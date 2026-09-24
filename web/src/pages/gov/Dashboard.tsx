import { lazy, Suspense } from "react";
import { useNavigate } from "react-router-dom";
// Lazy chunk: leaflet + OpMap load only when the dashboard renders (the
// inspector/NGO/beneficiary roles never download the map bundle).
const OpMap = lazy(() => import("../../components/OpMap"));
import type { EventMarker, InspectorMarker, ProjectMarker, RouteLine } from "../../components/OpMap";
import { Chip, Dot, Empty, Err, Panel } from "../../components/ui";
import { useGet } from "../../lib/hooks";
import { fmtTime, riskTone, sevTone, statusTone, titleCase, truncate } from "../../lib/format";

interface AlertRow { id: number; code: string; kind: string; severity: string; title: string;
  summary: string; project_id: number | null; project_name?: string; occurred_at: string;
  signals: unknown[]; risk_signal: number; recommended_action: string; status: string; }
interface InspRow { id: number; code: string; status: string; project?: { code?: string; name?: string };
  inspector_name?: string; assigned_at?: string; assignment_kind?: string; reason?: string; }
interface MapData {
  projects: ProjectMarker[]; inspectors: InspectorMarker[];
  outdoor_events: EventMarker[]; routes: RouteLine[];
}

export default function GovDashboard() {
  const nav = useNavigate();
  const ov = useGet<any>("/api/dashboard/overview", [], { pollMs: 20000 });
  const map = useGet<MapData>("/api/dashboard/map", [], { pollMs: 30000 });

  const summary = ov.data?.summary;
  const counts: Array<[string, string | number, string]> = summary ? [
    ["Projects", summary.projects.total, "c-blue"],
    ["Risk red / amber", `${summary.projects.red} / ${summary.projects.amber}`, "c-red"],
    ["Open alerts", summary.alerts.open, "c-amber"],
    ["Critical", summary.alerts.critical, "c-red"],
    ["Open inspections", summary.inspections.open, "c-blue"],
    ["Cameras", summary.cameras, "c-green"],
    ["Active outdoor events", summary.active_events, "c-amber"],
  ] : [];

  return (
    <div className="stack">
      {ov.error && <Err message={ov.error} />}
      <div className="row spread">
        <h1 style={{ margin: 0 }}>Command dashboard</h1>
        <div className="row">
          {counts.map(([k, v, tone]) => (
            <Panel key={k} className="" bodyPad={false}>
              <div style={{ padding: "10px 16px", textAlign: "center" }}>
                <div className={`stat-num ${tone}`}>{v}</div>
                <div className="caption">{k}</div>
              </div>
            </Panel>
          ))}
        </div>
      </div>

      <div className="dash-grid">
        <div className="map-zone">
          <Panel title="Operational map — projects · risk · inspectors · events" bodyPad={false}>
            <div className="map-wrap" style={{ height: 540 }}>
              {map.data && (
                <Suspense fallback={
                  <div className="empty" style={{ paddingTop: 240 }}>Loading map…</div>
                }>
                  <OpMap
                    projects={map.data.projects}
                    inspectors={map.data.inspectors}
                    events={map.data.outdoor_events}
                    routes={map.data.routes}
                  />
                </Suspense>
              )}
            </div>
          </Panel>
        </div>

        <div className="queue-zone">
          <Panel title={`Alert queue (${ov.data?.alerts?.length ?? 0})`} bodyPad={false}
            right={<button className="btn small" onClick={() => nav("/gov/alerts")}>Open queue</button>}>
            <div className="stack" style={{ padding: 10 }}>
              {(ov.data?.alerts ?? []).length === 0 && !ov.loading && <Empty text="No open alerts" />}
              {(ov.data?.alerts ?? []).slice(0, 7).map((a: AlertRow) => (
                <button key={a.id} className={`alert-card sev-${a.severity}`} onClick={() => nav("/gov/alerts")}>
                  <div className="row">
                    <Chip tone={sevTone(a.severity)}>{a.severity}</Chip>
                    <Chip tone="neutral">{titleCase(a.kind)}</Chip>
                    <span className="caption">{fmtTime(a.occurred_at)}</span>
                  </div>
                  <div style={{ fontWeight: 600 }}>{truncate(a.title, 90)}</div>
                  <div className="caption">{a.project_name ?? "—"} · risk {a.risk_signal?.toFixed?.(2) ?? a.risk_signal}</div>
                </button>
              ))}
            </div>
          </Panel>
        </div>

        <div className="timeline-zone">
          <Panel title={`Inspection dispatch queue (${ov.data?.inspections?.length ?? 0})`} bodyPad={false}
            right={<button className="btn small" onClick={() => nav("/gov/inspections")}>Dispatch</button>}>
            <table className="tbl">
              <thead><tr><th>Code</th><th>Kind</th><th>Project</th><th>Inspector</th><th>Status</th><th>Assigned</th></tr></thead>
              <tbody>
                {(ov.data?.inspections ?? []).slice(0, 8).map((i: InspRow) => (
                  <tr key={i.id} className="rowlink" onClick={() => nav("/gov/inspections")}>
                    <td className="mono">{i.code}</td>
                    <td>{titleCase(i.assignment_kind ?? "")}</td>
                    <td>{i.project?.name ?? "—"}</td>
                    <td>{i.inspector_name ?? "—"}</td>
                    <td><Chip tone={statusTone(i.status)}>{i.status}</Chip></td>
                    <td className="caption">{fmtTime(i.assigned_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(ov.data?.inspections ?? []).length === 0 && !ov.loading && <Empty />}
          </Panel>
        </div>

        <div className="bottom-zone">
          <Panel title="Inspector field status" bodyPad={false}>
            <table className="tbl">
              <thead><tr><th>Inspector</th><th>Open inspections</th><th>Last position</th></tr></thead>
              <tbody>
                {(ov.data?.inspector_status ?? []).map((s: any) => (
                  <tr key={s.id}>
                    <td>{s.full_name}</td>
                    <td><Chip tone={s.open_inspections > 0 ? "amber" : "green"}>{s.open_inspections}</Chip></td>
                    <td className="caption">{s.last_position_at ? fmtTime(s.last_position_at) : "not reporting"} </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(ov.data?.inspector_status ?? []).length === 0 && <Empty text="No inspectors reporting" />}
          </Panel>
        </div>
      </div>

      {map.data && (
        <div className="caption" style={{ marginTop: -6 }}>
          <Dot tone="green" /> healthy · <Dot tone="amber" /> review · <Dot tone="red" /> critical · map data is sample in DEMO mode
        </div>
      )}
    </div>
  );
}

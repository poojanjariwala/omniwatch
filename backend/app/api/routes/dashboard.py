"""Tier-1 command dashboard: overview counts, live map, alert/inspection queues."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.rbac import CurrentUser, Db, GovernmentUser, scope_organizations, scope_projects
from app.models.cv import Camera
from app.models.ops import (
    Alert, Distribution, Inspection, InspectionLocation, OutdoorEvent, Project, QrCode,
)
from app.models.users import Organization, User
from app.schemas.serializers import (
    alert_public, inspection_full, outdoor_event_public, project_public,
)

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/overview")
def overview(db: Db, user: GovernmentUser):
    projects = scope_projects(user, db)
    project_ids = [p.id for p in projects]
    org_names = {o.id: o.name for o in db.query(Organization).all()}

    def _count(model, *, project_col=None, extra=None):
        if project_col is not None and not project_ids:
            return 0  # scoped role with no projects sees nothing
        q = db.query(model)
        if project_col is not None:
            q = q.filter(project_col.in_(project_ids))
        if extra is not None:
            q = q.filter(*extra)
        return q.count()

    open_alerts = (db.query(Alert)
                   .filter(Alert.project_id.in_(project_ids) if project_ids else Alert.id > 0,
                           Alert.status.in_(("open", "in_review", "verifying", "action_taken")))
                   .order_by(Alert.occurred_at.desc()).limit(25).all()) if project_ids else []
    open_inspections = (db.query(Inspection)
                        .filter(Inspection.status.in_(("assigned", "activated", "in_progress")))
                        .order_by(Inspection.created_at.desc()).limit(20).all())
    if user.role == "state" and project_ids:
        open_inspections = [i for i in open_inspections if i.project_id in project_ids]

    inspectors = db.query(User).filter(User.role == "pmu", User.is_active.is_(True))
    if user.role == "state" and user.state_code:
        # Regional authorities see only their own state's field staff.
        inspectors = inspectors.filter(User.state_code == user.state_code)
    inspectors = inspectors.order_by(User.full_name).all()

    alert_rows = []
    for a in open_alerts:
        p = db.get(Project, a.project_id) if a.project_id else None
        alert_rows.append(alert_public(a, project_name=p.name if p else None))

    inspection_rows = []
    for i in open_inspections:
        p = db.get(Project, i.project_id) if i.project_id else None
        insp = db.get(User, i.assigned_inspector_id)
        inspection_rows.append(inspection_full(i, project=p, inspector=insp,
                                               include_evidence=False))

    inspector_status = [{
        "id": u.id, "full_name": u.full_name, "lat": u.lat, "lng": u.lng,
        "last_position_at": u.last_position_at.isoformat() if u.last_position_at else None,
        "open_inspections": sum(1 for x in inspection_rows
                                if x["assigned_inspector_id"] == u.id),
    } for u in inspectors]

    org_ids = scope_organizations(user, db)
    active_events = (db.query(OutdoorEvent)
                     .filter(OutdoorEvent.status.in_(("approved", "active")))
                     .filter(OutdoorEvent.org_id.in_(org_ids) if org_ids else True)
                     .count())
    summary = {
        "projects": {"total": len(projects),
                     "green": sum(1 for p in projects if p.risk_status == "green"),
                     "amber": sum(1 for p in projects if p.risk_status == "amber"),
                     "red": sum(1 for p in projects if p.risk_status == "red")},
        "alerts": {"open": len(open_alerts),
                   "critical": sum(1 for a in open_alerts if a.severity == "critical")},
        "inspections": {"open": len(open_inspections)},
        "cameras": _count(Camera, project_col=Camera.project_id),
        "active_events": active_events,
    }
    return {
        "summary": summary,
        "alerts": alert_rows,
        "inspections": inspection_rows,
        "inspector_status": inspector_status,
    }


@router.get("/dashboard/map")
def map_view(db: Db, user: GovernmentUser):
    """Operational map layers: projects, events, inspectors, inspection routes."""
    projects = scope_projects(user, db)
    org_names = {o.id: o.name for o in db.query(Organization).all()}
    open_statuses = ("assigned", "activated", "in_progress")

    project_markers = [{
        "id": p.id, "code": p.code, "name": p.name, "lat": p.lat, "lng": p.lng,
        "risk_status": p.risk_status, "risk_score": p.risk_score,
        "category": p.category, "org_name": org_names.get(p.org_id),
    } for p in projects]

    inspectors = db.query(User).filter(User.role == "pmu",
                                       User.is_active.is_(True),
                                       User.lat.isnot(None),
                                       User.lng.isnot(None)).all()
    inspector_markers = [{
        "id": u.id, "full_name": u.full_name, "lat": u.lat, "lng": u.lng,
        "last_position_at": u.last_position_at.isoformat() if u.last_position_at else None,
    } for u in inspectors]

    events = (db.query(OutdoorEvent)
              .filter(OutdoorEvent.status.in_(("registered", "approved", "active")))
              .order_by(OutdoorEvent.scheduled_at).all())
    if user.role == "state":
        state_orgs = {o.id for o in db.query(Organization)
                      .filter(Organization.state_code == user.state_code).all()}
        events = [e for e in events if e.org_id in state_orgs]
    event_markers = [outdoor_event_public(e, org_name=org_names.get(e.org_id)) for e in events]

    open_inspections = (db.query(Inspection)
                        .filter(Inspection.status.in_(open_statuses)).all())
    if user.role == "state":
        project_ids = {p.id for p in projects}
        open_inspections = [i for i in open_inspections if i.project_id in project_ids]
    routes = []
    for insp in open_inspections:
        p = db.get(Project, insp.project_id) if insp.project_id else None
        if p is None:
            continue
        # Route = inspector's last reported position -> project geofence centre.
        # (insp.lat/lng only mirror the project; the GPS heartbeats are authoritative.)
        points = [{"lat": p.lat, "lng": p.lng}]
        latest_loc = (db.query(InspectionLocation)
                      .filter(InspectionLocation.inspection_id == insp.id)
                      .order_by(InspectionLocation.ts.desc()).first())
        if latest_loc is not None:
            points.insert(0, {"lat": latest_loc.lat, "lng": latest_loc.lng})
        routes.append({
            "inspection_id": insp.id, "code": insp.code,
            "project_id": p.id, "points": points, "kind": insp.assignment_kind,
        })

    return {
        "projects": project_markers,
        "inspectors": inspector_markers,
        "outdoor_events": event_markers,
        "routes": routes,
    }


@router.get("/dashboard/ngo-overview")
def ngo_overview(db: Db, user: CurrentUser):
    """NGO (Tier 3) operational view — deliberately excludes risk/alerts/schedules."""
    if user.role != "ngo" or user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="NGO staff only")
    projects = db.query(Project).filter(Project.org_id == user.org_id).all()
    org = db.get(Organization, user.org_id)
    out_projects = []
    for p in projects:
        from app.schemas.serializers import project_public
        consumed = db.query(QrCode).filter(QrCode.project_id == p.id,
                                           QrCode.status == "consumed").count()
        item = project_public(p, for_role="ngo", org_name=org.name if org else None)
        item["qr_consumed_total"] = consumed
        out_projects.append(item)
    distributions = (db.query(Distribution)
                     .filter(Distribution.org_id == user.org_id)
                     .order_by(Distribution.created_at.desc()).limit(30).all())
    dists = []
    for d in distributions:
        from app.schemas.serializers import distribution_public
        from app.services.qr import distribution_stats
        stats = distribution_stats(db, d.id)
        p = db.get(Project, d.project_id) if d.project_id else None
        dists.append(distribution_public(d, **stats, project_name=p.name if p else None,
                                         org_name=org.name if org else None))
    events = (db.query(OutdoorEvent).filter(OutdoorEvent.org_id == user.org_id)
              .order_by(OutdoorEvent.scheduled_at.desc()).limit(20).all())
    return {
        "projects": out_projects,
        "distributions": dists,
        "events": [outdoor_event_public(e, org_name=org.name if org else None)
                   for e in events],
    }

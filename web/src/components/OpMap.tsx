import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { riskTone } from "../lib/format";

export interface ProjectMarker {
  id: number; code: string; name: string; lat: number; lng: number;
  risk_status?: string; risk_score?: number; org_name?: string; category?: string;
}
export interface InspectorMarker {
  id: number; full_name: string; lat: number; lng: number;
}
export interface EventMarker {
  id: number; code: string; title: string; lat: number; lng: number; status?: string;
}
export interface RouteLine {
  code: string; points: Array<{ lat: number; lng: number }>;
}

function makeIcon(color: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="34" viewBox="0 0 24 34">
    <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 22 12 22s12-13 12-22C24 5.4 18.6 0 12 0z"
      fill="${color}" stroke="#111827" stroke-width="1.5"/>
    <circle cx="12" cy="12" r="5" fill="#ffffff"/>
  </svg>`;
  return L.divIcon({ html: svg, className: "", iconSize: [26, 34], iconAnchor: [13, 32] });
}

export default function OpMap({
  projects = [], inspectors = [], events = [], routes = [],
}: {
  projects?: ProjectMarker[]; inspectors?: InspectorMarker[];
  events?: EventMarker[]; routes?: RouteLine[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!host.current || mapRef.current) return;
    const map = L.map(host.current, { zoomControl: true }).setView([22.5, 79], 5);
    mapRef.current = map;
    // ArcGIS World Light Gray Base: flat pale style matching the design system.
    // CARTO began watermarking tiles for some browser referrers ("API KEY
    // REQUIRED"); ArcGIS World tiles are served without per-app keys.
    // errorTileUrl: flat neutral square so outages degrade to a clean grid.
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles © Esri — Esri, DeLorme, NAVTEQ",
        maxZoom: 16,
      errorTileUrl:
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='256' height='256'%3E%3Crect width='256' height='256' fill='%23eef0f2'/%3E%3C/svg%3E",
    }).addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    const add = (f: () => void) => { try { f(); } catch { /* noop */ } };

    projects.forEach((p) => {
      add(() => {
        const tone = riskTone(p.risk_status ?? p.risk_score ?? 0);
        const color = tone === "red" ? "#dc2626" : tone === "amber" ? "#d97706" : "#059669";
        const m = L.marker([p.lat, p.lng], { icon: makeIcon(color) })
          .bindPopup(`<b>${p.name}</b><br/>${p.code} · risk ${p.risk_status ?? "—"}`);
        m.addTo(layer);
      });
    });
    inspectors.forEach((i) => {
      add(() => {
        const ic = makeIcon("#2563eb");
        L.marker([i.lat, i.lng], { icon: ic })
          .bindPopup(`<b>Inspector</b><br/>${i.full_name}`).addTo(layer);
      });
    });
    events.forEach((e) => {
      add(() => {
        L.circleMarker([e.lat, e.lng], { radius: 7, color: "#111827",
          fillColor: "#f59e0b", fillOpacity: 1, weight: 1.5 })
          .bindPopup(`<b>${e.title}</b><br/>${e.code} · ${e.status ?? ""}`).addTo(layer);
      });
    });
    routes.forEach((r) => {
      add(() => {
        L.polyline(r.points.map((p) => [p.lat, p.lng] as [number, number]),
          { color: "#2563eb", dashArray: "6 5", weight: 2 })
          .bindPopup(`Inspection ${r.code}`).addTo(layer);
      });
    });

    const pts: Array<[number, number]> = [
      ...projects.map((p) => [p.lat, p.lng] as [number, number]),
      ...inspectors.map((i) => [i.lat, i.lng] as [number, number]),
      ...events.map((e) => [e.lat, e.lng] as [number, number]),
    ];
    if (pts.length > 0) map.fitBounds(L.latLngBounds(pts).pad(0.15));

    return () => {
      layer.clearLayers();
      layer.remove();
    };
  }, [projects, inspectors, events, routes]);

  return <div ref={host} className="map-wrap" aria-label="Operational map" />;
}

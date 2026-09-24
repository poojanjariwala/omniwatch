import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { getStoredUser, logoutRemote } from "../lib/api";
import { DEMO_PERSONAS } from "../lib/demo";

function demoMode(): boolean {
  // Demo banner shows when the browser believes sample data may be loaded.
  try {
    return localStorage.getItem("ow_demo_mode") === "1";
  } catch {
    return false;
  }
}

export default function Shell() {
  const user = getStoredUser();
  const navigate = useNavigate();
  const location = useLocation();
  const isDemo = demoMode() || Boolean(DEMO_PERSONAS.find((p) => p.email === user?.email));
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the drawer whenever the route changes (nav tap or programmatic nav).
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // Escape closes the drawer; body scroll is locked while it is open.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  async function doLogout() {
    await logoutRemote();
    navigate("/login", { replace: true });
  }

  const gov = user?.role === "dosje" || user?.role === "state";
  const nav: Array<{ to: string; label: string }> = [];
  if (gov) {
    nav.push({ to: "/gov/dashboard", label: "Command dashboard" });
    nav.push({ to: "/gov/projects", label: "Project registry" });
    nav.push({ to: "/gov/alerts", label: "Alert queue" });
    nav.push({ to: "/gov/cctv", label: "CCTV & events" });
    nav.push({ to: "/gov/inspections", label: "Inspections & dispatch" });
    nav.push({ to: "/gov/evidence", label: "Evidence console" });
    nav.push({ to: "/gov/cases", label: "Cases & audit reports" });
    nav.push({ to: "/gov/audit", label: "Audit log" });
  } else if (user?.role === "pmu") {
    nav.push({ to: "/inspector/tasks", label: "My assignments" });
    nav.push({ to: "/verify", label: "Beneficiary verify" });
  } else if (user?.role === "ngo") {
    nav.push({ to: "/ngo/terminal", label: "NGO terminal" });
    nav.push({ to: "/ngo/events", label: "Outdoor events" });
  } else {
    nav.push({ to: "/verify", label: "Verify a handout" });
  }

  return (
    <div className="shell">
      {isDemo && <div className="demo-banner">DEMO MODE — all data shown is SAMPLE data</div>}
      <div className="app-body">
        <aside id="sidenav" className={`sidenav ${drawerOpen ? "open" : ""}`} aria-label="Primary navigation">
          <div className="brand">
            <div className="name">OMNIWATCH</div>
            <div className="tagline">Evidence-backed verification</div>
          </div>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `navlink ${isActive ? "active" : ""}`}>
              {n.label}
            </NavLink>
          ))}
        </aside>
        {drawerOpen && (
          <div className="drawer-scrim" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
        )}
        <div className="content">
          {/* Mobile-only top bar: hamburger + brand + identity */}
          <div className="mobilebar">
            <button
              type="button"
              className="hamburger"
              aria-label={drawerOpen ? "Close menu" : "Open menu"}
              aria-expanded={drawerOpen}
              aria-controls="sidenav"
              onClick={() => setDrawerOpen((v) => !v)}
            >
              <span /><span /><span />
            </button>
            <div className="brand compact">
              <div className="name">OMNIWATCH</div>
            </div>
            <div className="row" style={{ gap: 8, marginLeft: "auto" }}>
              <ChipLike>{user?.role ?? ""}</ChipLike>
              <button className="btn small" onClick={doLogout}>Sign out</button>
            </div>
          </div>

          {/* Desktop-only flow strip */}
          <div className="topline">
            <div className="flow">
              <span className="node">OmniWatch</span>
              <span className="arrow">·</span>
              <span className="caption">Monitoring → verification → audit</span>
            </div>
            <div className="row" style={{ gap: 8 }}>
              <ChipLike>{user?.role ?? ""}</ChipLike>
              <span className="caption">{user?.full_name}</span>
              <button className="btn small" onClick={doLogout}>Sign out</button>
            </div>
          </div>

          <Outlet />
        </div>
      </div>
    </div>
  );
}

function ChipLike({ children }: { children: React.ReactNode }) {
  return <span className="chip blue">{children}</span>;
}

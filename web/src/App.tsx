import { Navigate, Route, Routes } from "react-router-dom";
import { getStoredUser } from "./lib/api";
import Shell from "./components/Shell";
import LoginPage from "./pages/LoginPage";
import GovDashboard from "./pages/gov/Dashboard";
import GovProjects from "./pages/gov/Projects";
import GovAlerts from "./pages/gov/Alerts";
import GovCctv from "./pages/gov/Cctv";
import GovInspections from "./pages/gov/Inspections";
import GovCases from "./pages/gov/Cases";
import GovEvidence from "./pages/gov/Evidence";
import GovAudit from "./pages/gov/Audit";
import InspectorTasks from "./pages/inspector/Tasks";
import InspectorWorkspace from "./pages/inspector/Workspace";
import NgoTerminal from "./pages/ngo/Terminal";
import NgoEvents from "./pages/ngo/Events";
import VerifyPage from "./pages/VerifyPage";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = getStoredUser();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Shell />
          </RequireAuth>
        }
      >
        <Route index element={<RoleHome />} />
        <Route path="gov/dashboard" element={<GovDashboard />} />
        <Route path="gov/projects" element={<GovProjects />} />
        <Route path="gov/alerts" element={<GovAlerts />} />
        <Route path="gov/cctv" element={<GovCctv />} />
        <Route path="gov/inspections" element={<GovInspections />} />
        <Route path="gov/cases" element={<GovCases />} />
        <Route path="gov/evidence" element={<GovEvidence />} />
        <Route path="gov/audit" element={<GovAudit />} />
        <Route path="inspector/tasks" element={<InspectorTasks />} />
        <Route path="inspector/tasks/:id" element={<InspectorWorkspace />} />
        <Route path="ngo/terminal" element={<NgoTerminal />} />
        <Route path="ngo/events" element={<NgoEvents />} />
        <Route path="verify" element={<VerifyPage />} />
      </Route>
    </Routes>
  );
}

function RoleHome() {
  const user = getStoredUser();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "dosje" || user.role === "state") return <Navigate to="/gov/dashboard" replace />;
  if (user.role === "pmu") return <Navigate to="/inspector/tasks" replace />;
  if (user.role === "ngo") return <Navigate to="/ngo/terminal" replace />;
  return <Navigate to="/verify" replace />;
}

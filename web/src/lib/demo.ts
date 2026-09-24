/** Demo login identities — mirrored from backend/app/bootstrap.py. */
export interface DemoPersona {
  role: string;
  label: string;
  email: string;
  password: string;
}

export const DEMO_PERSONAS: DemoPersona[] = [
  { role: "dosje", label: "DoSJE official", email: "admin@omniwatch.demo.in", password: "Admin@Demo123" },
  { role: "pmu", label: "Inspector (PMU)", email: "rakesh@pmu.demo.in", password: "Pmu@Demo123" },
  { role: "ngo", label: "NGO terminal", email: "ngo@demo.org", password: "Ngo@Demo123" },
  { role: "ngo2", label: "NGO terminal (2nd org)", email: "ngo2@demo.org", password: "Ngo2@Demo123" },
  { role: "state", label: "State authority", email: "state@omniwatch.demo.in", password: "State@Demo123" },
];

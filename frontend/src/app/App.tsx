import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ErrorLine, Loading } from "../components/ui";
import { Admin } from "../features/Admin";
import { Approvals } from "../features/Approvals";
import { CustomerPage } from "../features/Customer";
import { Customers } from "../features/Customers";
import { Evaluation } from "../features/Evaluation";
import { Executive } from "../features/Executive";
import { SafetyCenter } from "../features/Safety";
import { Pay } from "../features/Pay";
import { Portal } from "../features/Portal";
import { Today } from "../features/Today";
import { storedRole, storeCode, storeRole } from "../lib/api";
import { useMe } from "../lib/hooks";
import type { Role } from "../lib/schemas";
import { href, useRoute, type Route } from "./route";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: true } } });

export function App() {
  return (
    <QueryClientProvider client={client}>
      <Shell />
    </QueryClientProvider>
  );
}

const ROLES: { role: Role; label: string; what: string }[] = [
  { role: "collector", label: "Collector", what: "Review drafts, record replies, resolve disputes." },
  { role: "admin", label: "Admin", what: "Everything a collector does, plus sending, clock, reset and demo tools." },
  { role: "viewer", label: "Viewer", what: "Read-only: every screen, no actions." },
];

/** S-01: pick a role. A hosted demo asks for that role's access code; on a laptop the code stays empty. */
function SignIn({ onPick }: { onPick: (r: Role, code: string) => void }) {
  const [code, setCode] = useState("");
  return (
    <main className="mx-auto max-w-xl px-4 py-16">
      <h1 className="font-display text-display font-semibold">Collections Agent</h1>
      <p className="mb-8 text-text-muted">Choose a demo role to continue. Every number you will see comes from the ledger.</p>
      <label className="mb-6 block">
        <span className="mb-1 block font-semibold">Access code</span>
        <input
          type="password"
          autoComplete="off"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="min-h-11 w-full rounded border border-border bg-surface px-3"
        />
        <span className="text-label text-text-muted">Leave empty when running on your own machine.</span>
      </label>
      <ul className="space-y-3">
        {ROLES.map((r) => (
          <li key={r.role}>
            <button
              type="button"
              onClick={() => onPick(r.role, code)}
              className="w-full rounded border border-border bg-surface p-4 text-left hover:border-accent"
            >
              <span className="block font-semibold">{r.label}</span>
              <span className="text-text-muted">{r.what}</span>
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}

const NAV: { route: Route; label: string; adminOnly?: boolean }[] = [
  { route: { page: "today" }, label: "Today" },
  { route: { page: "executive" }, label: "CFO view" },
  { route: { page: "approvals" }, label: "Approvals" },
  { route: { page: "customers" }, label: "Customers" },
  { route: { page: "safety" }, label: "AI Safety" },
  { route: { page: "evals" }, label: "Evaluation" },
  { route: { page: "admin" }, label: "Admin", adminOnly: true },
];

function Shell() {
  const route = useRoute();
  const [role, setRole] = useState<Role | null>(storedRole);
  const qc = useQueryClient();
  const pick = (r: Role | null, code = "") => {
    storeCode(code);
    storeRole(r);
    setRole(r);
    qc.clear();
  };
  if (route.page === "pay") return <Pay token={route.token} />; // public: the customer has no role
  if (route.page === "portal") return <Portal token={route.token} />; // public: the link is the credential
  if (!role) return <SignIn onPick={pick} />;
  return <Console role={role} onSignOut={() => pick(null)} />;
}

function Console({ role, onSignOut }: { role: Role; onSignOut: () => void }) {
  const route = useRoute();
  const me = useMe();
  const current = route.page === "customer" ? "customers" : route.page;
  if (me.isPending) return <Loading what="your session" />;
  if (me.error) {
    return (
      <main className="p-8">
        <ErrorLine error={me.error} />
        <div className="mt-4">
          <Button onClick={onSignOut}>Choose a role again</Button>
        </div>
      </main>
    );
  }
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav aria-label="Main" className="flex shrink-0 flex-row flex-wrap gap-1 border-b border-border bg-surface p-2 md:w-40 md:flex-col md:flex-nowrap md:border-r md:border-b-0">
        <span className="hidden px-2 py-3 font-display text-title font-semibold md:block">Collections</span>
        {NAV.filter((n) => !n.adminOnly || role === "admin").map((n) => (
          <a
            key={n.label}
            href={href(n.route)}
            aria-current={current === n.route.page ? "page" : undefined}
            className="flex min-h-11 shrink-0 items-center rounded px-3 font-semibold whitespace-nowrap text-text-muted hover:bg-bg-subtle aria-[current=page]:bg-accent-subtle aria-[current=page]:text-accent"
          >
            {n.label}
          </a>
        ))}
        <div className="ml-auto flex flex-row items-center gap-2 md:mt-auto md:ml-0 md:flex-col md:items-stretch">
          <ThemeToggle />
          <p className="hidden px-2 text-label text-text-muted md:block">
            {me.data.display_name}
          </p>
          <button type="button" onClick={onSignOut} className="min-h-11 rounded px-3 text-left text-label text-link underline">
            Switch role
          </button>
        </div>
      </nav>
      <main className="mx-auto w-full max-w-console min-w-0 flex-1 p-4 md:p-6">
        {route.page === "today" && <Today />}
        {route.page === "approvals" && <Approvals role={role} />}
        {route.page === "customers" && <Customers />}
        {route.page === "customer" && <CustomerPage key={route.id} id={route.id} role={role} />}
        {route.page === "admin" && (role === "admin" ? <Admin /> : <p>Admin is for the admin role.</p>)}
        {route.page === "evals" && <Evaluation />}
        {route.page === "executive" && <Executive />}
        {route.page === "safety" && <SafetyCenter />}
      </main>
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => localStorage.getItem("ca.theme") ?? "system");
  const next = theme === "system" ? "dark" : theme === "dark" ? "light" : "system";
  const apply = () => {
    if (next === "system") {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem("ca.theme");
    } else {
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("ca.theme", next);
    }
    setTheme(next);
  };
  return (
    <button type="button" onClick={apply} className="min-h-11 rounded px-3 text-left text-label text-text-muted hover:bg-bg-subtle">
      Theme: {theme}
    </button>
  );
}

// Apply a stored theme before first paint of the console.
const saved = localStorage.getItem("ca.theme");
if (saved) document.documentElement.setAttribute("data-theme", saved);

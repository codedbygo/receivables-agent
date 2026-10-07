import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  Eye,
  FlaskConical,
  Inbox,
  IndianRupee,
  LayoutDashboard,
  LogOut,
  Monitor,
  Moon,
  Settings2,
  ShieldCheck,
  Sun,
  UserCog,
  Users,
  Wallet,
  type LucideIcon, MailOpen } from "lucide-react";
import { useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { Button, ErrorLine, Loading } from "@/components/kit";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Admin } from "@/features/Admin";
import { IncomingReplies } from "@/features/Google";
import { Approvals } from "@/features/Approvals";
import { CustomerPage } from "@/features/Customer";
import { Customers } from "@/features/Customers";
import { Evaluation } from "@/features/Evaluation";
import { Executive } from "@/features/Executive";
import { Pay } from "@/features/Pay";
import { Portal } from "@/features/Portal";
import { SafetyCenter } from "@/features/Safety";
import { Today } from "@/features/Today";
import { storedRole, storeCode, storeRole } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Role } from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { href, useRoute, type Route } from "./route";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: true } } });

export function App() {
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Shell />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

const ROLES: { role: Role; label: string; what: string; icon: LucideIcon }[] = [
  { role: "collector", label: "Collector", what: "Review drafts, record replies, resolve disputes.", icon: Inbox },
  { role: "admin", label: "Admin", what: "Everything a collector does, plus sending, clock, reset and demo tools.", icon: UserCog },
  { role: "viewer", label: "Viewer", what: "Read-only: every screen, no actions.", icon: Eye },
];

function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5 font-semibold tracking-tight", className)}>
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <Wallet aria-hidden className="size-4" />
      </span>
      <span className={"md:group-data-collapsed/side:sr-only"}>Collections Agent</span>
    </span>
  );
}

/** S-01: pick a role. A hosted demo asks for that role's access code; on a laptop the code stays empty. */
function SignIn({ onPick }: { onPick: (r: Role, code: string) => void }) {
  const [code, setCode] = useState("");
  return (
    <main className="grid min-h-screen place-items-center bg-linear-to-b from-primary-subtle to-background px-4 py-12">
      <div className="w-full max-w-md">
        <Brand className="mb-8 justify-center text-xl" />
        <div className="rounded-2xl border bg-card p-6 shadow-lg shadow-black/5 sm:p-8">
          <h1 className="text-xl font-semibold tracking-tight">Sign in to the console</h1>
          <p className="mt-1 mb-6 text-sm text-muted-foreground">
            Every number you will see comes from the ledger, never from the model.
          </p>
          <div className="mb-6 space-y-1.5">
            <Label htmlFor="code">Access code</Label>
            <Input
              id="code"
              type="password"
              name="access-code"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="h-11"
            />
            <p className="text-xs text-muted-foreground">Leave empty when running on your own machine.</p>
          </div>
          <p className="mb-2 text-sm font-medium">Continue as</p>
          <ul className="space-y-2">
            {ROLES.map((r) => (
              <li key={r.role}>
                <button
                  type="button"
                  onClick={() => onPick(r.role, code)}
                  className="group flex w-full items-center gap-3 rounded-xl border bg-card p-3 text-left transition-colors hover:border-primary/50 hover:bg-primary-subtle"
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground">
                    <r.icon aria-hidden className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">{r.label}</span>
                    <span className="block text-sm text-muted-foreground">{r.what}</span>
                  </span>
                  <ChevronRight aria-hidden className="size-4 text-muted-foreground group-hover:text-primary" />
                </button>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheck aria-hidden className="size-3.5" />
          Every outbound message passes guardrails and human approval.
        </p>
      </div>
    </main>
  );
}

/** Sidebar widths in px: icons only, the drag range, the default, and the width below which it snaps shut. */
const SIDE = { collapsed: 64, min: 200, open: 240, max: 400, snap: 140 };

const NAV: { route: Route; label: string; icon: LucideIcon; adminOnly?: boolean }[] = [
  { route: { page: "today" }, label: "Today", icon: LayoutDashboard },
  { route: { page: "executive" }, label: "CFO view", icon: IndianRupee },
  { route: { page: "approvals" }, label: "Approvals", icon: Inbox },
  { route: { page: "inbox" }, label: "Incoming replies", icon: MailOpen },
  { route: { page: "customers" }, label: "Customers", icon: Users },
  { route: { page: "safety" }, label: "AI Safety", icon: ShieldCheck },
  { route: { page: "evals" }, label: "Evaluation", icon: FlaskConical },
  { route: { page: "admin" }, label: "Admin", icon: Settings2, adminOnly: true },
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
  const [width, setWidth] = useState(() => Number(localStorage.getItem("ca.sidebar-width")) || SIDE.open);
  const collapsed = width === SIDE.collapsed;
  const resize = (w: number) => {
    // Like VS Code: dragged narrow enough, the sidebar snaps to icons only.
    const next = w < SIDE.snap ? SIDE.collapsed : Math.min(SIDE.max, Math.max(SIDE.min, w));
    localStorage.setItem("ca.sidebar-width", String(next));
    setWidth(next);
  };
  const drag = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const move = (m: PointerEvent) => resize(m.clientX);
    const up = () => {
      document.body.classList.remove("cursor-col-resize", "select-none");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    document.body.classList.add("cursor-col-resize", "select-none");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  if (me.isPending) {
    return (
      <main className="grid min-h-screen place-items-center">
        <Loading what="your session" />
      </main>
    );
  }
  if (me.error) {
    return (
      <main className="mx-auto grid min-h-screen max-w-lg content-center gap-4 p-8">
        <ErrorLine error={me.error} />
        <div>
          <Button onClick={onSignOut}>Choose a role again</Button>
        </div>
      </main>
    );
  }
  const initials = me.data.display_name
    .replace(/\(.*\)/, "")
    .trim()
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <nav
        aria-label="Main"
        data-collapsed={collapsed || undefined}
        style={{ "--side-w": `${width}px` } as CSSProperties}
        className="group/side flex shrink-0 flex-row items-center gap-1 overflow-x-auto border-b border-sidebar-border bg-sidebar p-2 text-sidebar-foreground md:border-r md:border-b-0 md:sticky md:top-0 md:h-screen md:w-(--side-w) md:flex-col md:data-collapsed:p-2 md:items-stretch md:gap-0 md:overflow-visible md:p-3"
      >
        <a href={href({ page: "today" })} className="hidden rounded-lg px-2 py-3 text-sidebar-strong md:mb-4 md:block">
          <Brand />
        </a>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
          aria-valuenow={width}
          aria-valuemin={SIDE.collapsed}
          aria-valuemax={SIDE.max}
          tabIndex={0}
          title="Drag to resize, double-click to collapse or expand"
          onPointerDown={drag}
          onDoubleClick={() => resize(collapsed ? SIDE.open : SIDE.collapsed)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") resize(width - 24);
            else if (e.key === "ArrowRight") resize(collapsed ? SIDE.min : width + 24);
            else if (e.key === "Enter") resize(collapsed ? SIDE.open : SIDE.collapsed);
            else if (e.key === "Home") resize(SIDE.collapsed); // the separator pattern: Home and End go to min and max
            else if (e.key === "End") resize(SIDE.max);
          }}
          className="absolute inset-y-0 -right-1 z-10 hidden w-2 cursor-col-resize outline-none after:absolute after:inset-y-0 after:left-1/2 after:w-px focus-visible:after:bg-ring md:block"
        />
        <p className="hidden px-3 pb-2 text-xs font-medium tracking-wider text-sidebar-muted uppercase md:block md:group-data-collapsed/side:hidden">Workspace</p>
        {NAV.filter((n) => !n.adminOnly || role === "admin").map((n) => (
          <a
            key={n.label}
            href={href(n.route)}
            title={collapsed ? n.label : undefined}
            aria-current={current === n.route.page ? "page" : undefined}
            className="flex min-h-10 shrink-0 items-center gap-3 rounded-lg px-3 text-sm font-medium whitespace-nowrap transition-colors hover:bg-sidebar-active hover:text-sidebar-strong aria-[current=page]:bg-sidebar-active aria-[current=page]:text-sidebar-strong md:mb-0.5"
          >
            <n.icon
              aria-hidden
              className={cn("size-4", current === n.route.page ? "text-sidebar-primary" : "text-sidebar-muted")}
            />
            <span className="md:group-data-collapsed/side:sr-only">{n.label}</span>
          </a>
        ))}
        <div className="ml-auto flex items-center gap-1 md:mt-auto md:ml-0 md:flex-col md:items-stretch md:gap-2 md:border-t md:border-sidebar-border md:pt-3">
          <ThemeToggle />
          <div className="hidden items-center gap-3 rounded-lg px-2 py-2 md:flex md:group-data-collapsed/side:hidden">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-sidebar-active text-xs font-semibold text-sidebar-strong">
              {initials}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-sidebar-strong">{me.data.display_name}</span>
              <span className="block text-xs text-sidebar-muted capitalize">{role}</span>
            </span>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm whitespace-nowrap hover:bg-sidebar-active hover:text-sidebar-strong"
          >
            <LogOut aria-hidden className="size-4 text-sidebar-muted" />
            <span className="md:group-data-collapsed/side:sr-only">Switch role</span>
          </button>
        </div>
      </nav>
      <main className="mx-auto w-full max-w-console min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
        {route.page === "today" && <Today />}
        {route.page === "approvals" && <Approvals role={role} />}
        {route.page === "inbox" && <IncomingReplies role={role} />}
        {route.page === "customers" && <Customers role={role} />}
        {route.page === "customer" && <CustomerPage key={route.id} id={route.id} role={role} />}
        {route.page === "admin" && (role === "admin" ? <Admin /> : <p>Admin is for the admin role.</p>)}
        {route.page === "evals" && <Evaluation />}
        {route.page === "executive" && <Executive />}
        {route.page === "safety" && <SafetyCenter />}
      </main>
    </div>
  );
}

const THEMES = { system: Monitor, dark: Moon, light: Sun } as const;

function ThemeToggle() {
  const [theme, setTheme] = useState(() => (localStorage.getItem("ca.theme") ?? "system") as keyof typeof THEMES);
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
  const Icon = THEMES[theme];
  return (
    <button
      type="button"
      onClick={apply}
      aria-label={`Theme: ${theme}. Switch to ${next}`}
      className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm whitespace-nowrap hover:bg-sidebar-active hover:text-sidebar-strong"
    >
      <Icon aria-hidden className="size-4 text-sidebar-muted" />
      <span className="hidden capitalize md:inline md:group-data-collapsed/side:hidden">Theme: {theme}</span>
    </button>
  );
}

// Apply a stored theme before first paint of the console.
const saved = localStorage.getItem("ca.theme");
if (saved) document.documentElement.setAttribute("data-theme", saved);

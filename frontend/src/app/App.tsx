import { QueryCache, QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import {
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
import { z } from "zod";
import { api, ApiError } from "@/lib/api";
import { keys, useAction, useDashboard, useMe } from "@/lib/hooks";
import * as S from "@/lib/schemas";
import { cn } from "@/lib/utils";
import { href, useRoute, type Route } from "./route";

const client: QueryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: true } },
  // A session that ended (expired, signed out elsewhere, switched off by an admin) sends any screen back to sign in.
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (error instanceof ApiError && error.status === 401 && query.queryKey[0] !== keys.me[0]) {
        void client.resetQueries({ queryKey: keys.me });
      }
    },
  }),
});

export function App() {
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Shell />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

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

/** S-01: sign in as a person, with an email and password or with Google (HACK-011, ADR-0019). */
function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useAction(() => api("/auth/login", S.User, { method: "POST", body: { email: email.trim(), password } }));
  const fromGoogle = new URLSearchParams(window.location.search).get("signin_error");
  return (
    <main className="grid min-h-screen place-items-center bg-linear-to-b from-primary-subtle to-background px-4 py-12">
      <div className="w-full max-w-md">
        <Brand className="mb-8 justify-center text-xl" />
        <div className="rounded-2xl border bg-card p-6 shadow-lg shadow-black/5 sm:p-8">
          <h1 className="text-xl font-semibold tracking-tight">Sign in to the console</h1>
          <p className="mt-1 mb-6 text-sm text-muted-foreground">
            Every number you will see comes from the ledger, never from the model.
          </p>
          <a
            href="/api/v1/auth/google"
            className="flex h-11 w-full items-center justify-center gap-2 rounded-md border bg-card text-sm font-medium transition-colors hover:border-primary/50 hover:bg-primary-subtle"
          >
            Continue with Google
          </a>
          <p className="my-5 flex items-center gap-3 text-xs text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
            or with your email
          </p>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              login.mutate(undefined);
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                name="email"
                autoComplete="username"
                required
                maxLength={254}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-11"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                autoComplete="current-password"
                required
                maxLength={200}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-11"
              />
            </div>
            {login.error ? <ErrorLine error={login.error} /> : fromGoogle && <ErrorLine error={new Error(fromGoogle)} plain />}
            <Button type="submit" variant="primary" busy={login.isPending} disabled={!email.trim() || !password}>
              Sign in
            </Button>
          </form>
          <p className="mt-5 text-xs text-muted-foreground">No account, or forgot your password? Ask an admin.</p>
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

type NavItem = { route: Route; label: string; icon: LucideIcon; adminOnly?: boolean };

/** Daily work first, reporting second, settings last. */
const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Work",
    items: [
      { route: { page: "today" }, label: "Today", icon: LayoutDashboard },
      { route: { page: "approvals" }, label: "Approvals", icon: Inbox },
      { route: { page: "inbox" }, label: "Incoming replies", icon: MailOpen },
      { route: { page: "customers" }, label: "Customers", icon: Users },
    ],
  },
  {
    section: "Insights",
    items: [
      { route: { page: "executive" }, label: "CFO view", icon: IndianRupee },
      { route: { page: "safety" }, label: "AI Safety", icon: ShieldCheck },
      { route: { page: "evals" }, label: "Evaluation", icon: FlaskConical },
    ],
  },
  { section: "Settings", items: [{ route: { page: "admin" }, label: "Admin", icon: Settings2, adminOnly: true }] },
];

function Shell() {
  const route = useRoute();
  const me = useMe();
  const qc = useQueryClient();
  const signOut = useAction(() => api("/auth/logout", z.null(), { method: "POST" }));
  if (route.page === "pay") return <Pay token={route.token} />; // public: the customer has no role
  if (route.page === "portal") return <Portal token={route.token} />; // public: the link is the credential
  if (me.isPending) {
    return (
      <main className="grid min-h-screen place-items-center">
        <Loading what="your session" />
      </main>
    );
  }
  if (me.error instanceof ApiError && me.error.status === 401) return <SignIn />;
  if (me.error) {
    return (
      <main className="mx-auto grid min-h-screen max-w-lg content-center gap-4 p-8">
        <ErrorLine error={me.error} />
        <div>
          <Button onClick={() => void me.refetch()}>Try again</Button>
        </div>
      </main>
    );
  }
  // Whoever signs in next must not see this person's cached screens.
  return <Console me={me.data} onSignOut={() => signOut.mutate(undefined, { onSettled: () => void qc.resetQueries() })} />;
}

function Console({ me, onSignOut }: { me: S.User; onSignOut: () => void }) {
  const route = useRoute();
  const role = me.role;
  const pending = useDashboard().data?.pending_approvals ?? 0;
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
  const initials = me.display_name
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
        {NAV.map(({ section, items }) => {
          const shown = items.filter((n) => !n.adminOnly || role === "admin");
          if (shown.length === 0) return null;
          return (
            <div key={section} className="contents md:mb-4 md:block">
              <p className="hidden px-3 pb-1.5 text-xs font-medium tracking-wider text-sidebar-muted uppercase md:block md:group-data-collapsed/side:hidden">
                {section}
              </p>
              {shown.map((n) => (
                <a
                  key={n.label}
                  href={href(n.route)}
                  title={collapsed ? n.label : undefined}
                  aria-current={current === n.route.page ? "page" : undefined}
                  className="relative flex min-h-10 shrink-0 items-center gap-3 rounded-lg px-3 text-sm font-medium whitespace-nowrap transition-colors hover:bg-sidebar-active hover:text-sidebar-strong aria-[current=page]:bg-sidebar-active aria-[current=page]:text-sidebar-strong md:mb-0.5"
                >
                  <n.icon
                    aria-hidden
                    className={cn("size-4 shrink-0", current === n.route.page ? "text-sidebar-primary" : "text-sidebar-muted")}
                  />
                  <span className="md:group-data-collapsed/side:sr-only">{n.label}</span>
                  {n.route.page === "approvals" && pending > 0 && (
                    <span className="num ml-auto rounded-full bg-primary px-1.5 py-px text-xs font-semibold text-primary-foreground md:group-data-collapsed/side:absolute md:group-data-collapsed/side:top-1 md:group-data-collapsed/side:right-1 md:group-data-collapsed/side:px-1">
                      {pending}
                      <span className="sr-only"> waiting</span>
                    </span>
                  )}
                </a>
              ))}
            </div>
          );
        })}
        <div className="ml-auto flex items-center gap-1 md:mt-auto md:ml-0 md:flex-col md:items-stretch md:gap-2 md:border-t md:border-sidebar-border md:pt-3">
          <ThemeToggle />
          <div className="hidden items-center gap-3 rounded-lg px-2 py-2 md:flex md:group-data-collapsed/side:hidden">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-sidebar-active text-xs font-semibold text-sidebar-strong">
              {initials}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-sidebar-strong">{me.display_name}</span>
              <span className="block text-xs text-sidebar-muted capitalize">{role}</span>
            </span>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm whitespace-nowrap hover:bg-sidebar-active hover:text-sidebar-strong"
          >
            <LogOut aria-hidden className="size-4 text-sidebar-muted" />
            <span className="md:group-data-collapsed/side:sr-only">Sign out</span>
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

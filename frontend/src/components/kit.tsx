/** Console building blocks on shadcn/ui. Colour comes from theme tokens only; status is never colour alone. */
import type { LucideIcon } from "lucide-react";
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronLeft, Inbox, Info, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Button as UIButton } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog as UIDialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table as UITable, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "quiet" | "danger";
  busy?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
  kbd?: string;
  icon?: LucideIcon;
};

const VARIANTS = {
  primary: "default",
  quiet: "outline",
  danger: "outline",
} as const;

export function Button({ children, onClick, variant = "quiet", busy, disabled, type = "button", kbd, icon: Icon }: ButtonProps) {
  return (
    <UIButton
      type={type}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      variant={VARIANTS[variant]}
      className={cn(
        "h-9 font-semibold",
        variant === "danger" && "border-danger/40 text-danger hover:bg-danger-subtle hover:text-danger",
      )}
    >
      {busy ? <Loader2 aria-hidden className="animate-spin" /> : Icon && <Icon aria-hidden />}
      {children}
      {kbd && (
        <kbd className="hidden rounded border border-current/30 px-1 font-mono text-xs opacity-70 md:inline">{kbd}</kbd>
      )}
    </UIButton>
  );
}

const TONES = {
  HIGH: "bg-danger-subtle text-danger ring-danger/25",
  MEDIUM: "bg-warning-subtle text-warning ring-warning/25",
  LOW: "bg-muted text-muted-foreground ring-border",
  ok: "bg-success-subtle text-success ring-success/25",
  bad: "bg-danger-subtle text-danger ring-danger/25",
  wait: "bg-warning-subtle text-warning ring-warning/25",
  info: "bg-info-subtle text-info ring-info/25",
  plain: "bg-muted text-muted-foreground ring-border",
};

type Tone = keyof typeof TONES;

const STATUS_TONE: Record<string, Tone> = {
  pending_approval: "wait",
  approved: "info",
  sent: "ok",
  failed: "bad",
  rejected: "bad",
  paid: "ok",
  partially_paid: "wait",
  unpaid: "plain",
  disputed: "bad",
  pending: "wait",
  fulfilled: "ok",
  partially_fulfilled: "wait",
  missed: "bad",
  open: "bad",
  resolved: "ok",
  matched: "ok",
  needs_verification: "wait",
  WAIT_FOR_APPROVAL: "wait",
  ESCALATED: "bad",
  STOPPED_LIMIT: "bad",
  NO_ACTION: "plain",
  FAILED: "bad",
};

/** A pill with a dot and the word: colour plus text, never colour alone. */
export function Badge({ value, tone }: { value: string; tone?: Tone }) {
  const t = TONES[tone ?? STATUS_TONE[value] ?? (value in TONES ? (value as Tone) : "plain")];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ring-inset",
        t,
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {value.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}
    </span>
  );
}

export function BandBadge({ band }: { band: string | null }) {
  return band ? <Badge value={band} tone={band as Tone} /> : <span className="text-muted-foreground">None</span>;
}

export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section aria-label={title}>
      <Card className="gap-0 py-0 shadow-xs">
        <CardHeader className="border-b px-5 py-3.5 [.border-b]:pb-3.5">
          <CardTitle className="text-base font-semibold">
            <h2>{title}</h2>
          </CardTitle>
          {action && <CardAction>{action}</CardAction>}
        </CardHeader>
        <CardContent className="px-5 py-4">{children}</CardContent>
      </Card>
    </section>
  );
}

/** One header for every page: optional breadcrumb, the title (with an optional badge beside it), a line under it, actions right. */
export function PageHeader({
  title,
  description,
  children,
  back,
  badge,
}: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  back?: { href: string; label: string };
  badge?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {back && (
        <nav aria-label="Breadcrumb" className="mb-2">
          <a
            href={back.href}
            className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft aria-hidden className="size-4" />
            {back.label}
          </a>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-display leading-tight font-semibold tracking-tight">{title}</h1>
            {badge}
          </div>
          {description && <p className="mt-1 text-muted-foreground">{description}</p>}
        </div>
        {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
      </div>
    </header>
  );
}

/** A small rounded fact beside a page title, such as the demo date. */
export function MetaChip({ icon: Icon, label, value, mono }: { icon: LucideIcon; label: string; value: ReactNode; mono?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-sm shadow-xs">
      <Icon aria-hidden className="size-4 text-primary" />
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("num font-semibold", mono && "font-mono")}>{value}</span>
    </span>
  );
}

export type Stat = { label: string; value: ReactNode; hint?: ReactNode; alert?: boolean };

/** Related figures in one card split by hairlines, instead of a grid of separate cards. `alert` colours the figure. */
export function StatStrip({ stats }: { stats: Stat[] }) {
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border shadow-xs lg:auto-cols-fr lg:grid-flow-col lg:grid-cols-none">
      {stats.map((s) => (
        <div key={s.label} className="min-w-0 bg-card p-4 max-lg:odd:last:col-span-2 md:p-5">
          <dt className="truncate text-sm font-medium text-muted-foreground">{s.label}</dt>
          <dd className={cn("num mt-1 text-xl leading-tight font-semibold tracking-tight md:text-2xl", s.alert && "text-danger")}>
            {s.value}
          </dd>
          {s.hint && <dd className="mt-1 truncate text-sm text-muted-foreground">{s.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

const NOTICE = {
  info: ["border-info/30 bg-info-subtle text-info", Info],
  warning: ["border-warning/30 bg-warning-subtle text-warning", AlertTriangle],
  success: ["border-success/30 bg-success-subtle text-success", CheckCircle2],
  danger: ["border-danger/30 bg-danger-subtle text-danger", AlertCircle],
} as const;

/** A status banner: tone, icon and text; announced to screen readers. */
export function Notice({ tone = "info", children }: { tone?: keyof typeof NOTICE; children: ReactNode }) {
  const [cls, Icon] = NOTICE[tone];
  return (
    <div role="status" className={cn("flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm", cls)}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 break-words">{children}</div>
    </div>
  );
}

export function Empty({ children, icon: Icon = Inbox }: { children: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="flex flex-col items-center gap-3 px-4 py-10 text-center text-muted-foreground">
      <span className="grid size-10 place-items-center rounded-full bg-muted">
        <Icon aria-hidden className="size-5" />
      </span>
      <p className="max-w-sm text-sm">{children}</p>
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="flex items-center gap-2 py-4 text-muted-foreground">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      Loading {what}…
    </p>
  );
}

/** `plain` hides the error code and request id: the customer portal shows people the message only (HACK-004). */
export function ErrorLine({ error, plain = false }: { error: unknown; plain?: boolean }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-subtle px-4 py-3 text-danger">
      <AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0" />
      <span>
        {e ? (
          <>
            {!plain && <span className="font-mono font-semibold">{e.code}: </span>}
            {e.message}
            {!plain && e.requestId && <span className="font-mono text-xs opacity-80"> (request {e.requestId})</span>}
            {e.details.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {e.details.map((d) => (
                  <li key={d.field + d.reason}>
                    {d.field}: {d.reason}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          "Error: something went wrong. Reload and try again."
        )}
      </span>
    </p>
  );
}

/** Modal dialog (Radix): focus is trapped, Escape and the backdrop close it. */
export function Dialog({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <UIDialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton={false} className="max-h-dvh overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-title">{title}</DialogTitle>
          <DialogDescription className="sr-only">{title}</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </UIDialog>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-4 block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30";

export function Table({ head, children, numeric = [] }: { head: string[]; children: ReactNode; numeric?: number[] }) {
  return (
    <UITable>
      <TableHeader className="sticky top-0 bg-card">
        <TableRow className="hover:bg-transparent">
          {head.map((h, i) => (
            <TableHead
              key={h}
              scope="col"
              className={cn("text-xs font-semibold tracking-wide text-muted-foreground uppercase", numeric.includes(i) && "text-right")}
            >
              {h}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>{children}</TableBody>
    </UITable>
  );
}

export const td = "border-b px-3 py-3 align-top";
export const tdNum = "num border-b px-3 py-3 text-right align-top";

type FactorRow = { code: string; label: string; value: string; points: number; rule: string };

/** "Why?" for a score: each factor, its value from the ledger, the rule and the points it added. */
export function WhyFactors({ factors, score }: { factors: FactorRow[]; score: number }) {
  const max = Math.max(1, ...factors.map((f) => Math.abs(f.points)));
  return (
    <div>
      <ul className="divide-y divide-border">
        {factors.map((f) => (
          <li key={f.code} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 py-2">
            <span>
              <span className="font-semibold">{f.label}</span> <span className="num text-text-muted">{f.value}</span>
            </span>
            <span className={`num text-right font-semibold ${f.points < 0 ? "text-success" : ""}`}>
              {f.points > 0 ? "+" : ""}
              {f.points}
            </span>
            <span className="text-label text-text-muted">{f.rule}</span>
            <span aria-hidden className="h-1.5 w-24 rounded bg-bg-subtle">
              <span
                className={`block h-full rounded ${f.points < 0 ? "bg-success" : "bg-primary"}`}
                style={{ width: `${(Math.abs(f.points) / max) * 100}%` }}
              />
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-label text-text-muted">
        Score {score}: the points above, rounded. Decision factors and rules computed from the ledger, not model reasoning.
      </p>
    </div>
  );
}

/** How figures are computed: closed by default so the page leads with the figures, one click away for the curious. */
export function Definitions({ title, entries }: { title: string; entries: Record<string, string> }) {
  return (
    <details className="group rounded-xl border bg-card shadow-xs">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-5 py-3.5 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        {title}
        <ChevronDown aria-hidden className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <dl className="grid gap-x-8 gap-y-3 border-t px-5 py-4 md:grid-cols-2">
        {Object.entries(entries).map(([key, text]) => (
          <div key={key}>
            <dt className="text-sm font-semibold first-letter:uppercase">{key.replaceAll("_", " ")}</dt>
            <dd className="text-label text-muted-foreground">{text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/** Horizontal bars for a small labelled series; values are shown as text too, so the bar is decoration. */
export function BarList({ data, format }: { data: { label: string; value: number }[]; format: (v: number) => string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) return <Empty>No data yet.</Empty>;
  return (
    <ul className="space-y-3">
      {data.map((d) => (
        <li key={d.label} className="grid grid-cols-[minmax(0,7rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-muted-foreground first-letter:uppercase">{d.label.replaceAll("_", " ")}</span>
          <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span className="block h-full rounded-full bg-primary" style={{ width: `${(d.value / max) * 100}%` }} />
          </span>
          <span className="num min-w-16 text-right font-medium">{format(d.value)}</span>
        </li>
      ))}
    </ul>
  );
}

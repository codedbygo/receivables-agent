/** Shared components from docs/design/components.md. Colours come from role tokens only. */
import { useEffect, useRef, type ReactNode } from "react";
import { ApiError } from "../lib/api";

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "quiet" | "danger";
  busy?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
  kbd?: string;
};

const VARIANTS = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover active:bg-accent-active border border-accent",
  quiet: "bg-surface text-text border border-border-strong hover:bg-bg-subtle",
  danger: "bg-surface text-danger border border-danger hover:bg-danger-subtle",
};

export function Button({ children, onClick, variant = "quiet", busy, disabled, type = "button", kbd }: ButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex h-9 items-center gap-2 rounded px-4 font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]}`}
    >
      {busy && <span aria-hidden className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
      {kbd && (
        <kbd className="hidden rounded border border-current px-1 font-mono text-label opacity-70 md:inline">{kbd}</kbd>
      )}
    </button>
  );
}

const TONES: Record<string, string> = {
  HIGH: "bg-danger-subtle text-danger border-danger",
  MEDIUM: "bg-warning-subtle text-warning border-warning",
  LOW: "bg-bg-subtle text-text-muted border-border-strong",
  ok: "bg-success-subtle text-success border-success",
  bad: "bg-danger-subtle text-danger border-danger",
  wait: "bg-warning-subtle text-warning border-warning",
  info: "bg-info-subtle text-info border-info",
  plain: "bg-bg-subtle text-text-muted border-border",
};

const STATUS_TONE: Record<string, keyof typeof TONES> = {
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

/** Colour plus the word, never colour alone. */
export function Badge({ value, tone }: { value: string; tone?: keyof typeof TONES }) {
  const t = TONES[tone ?? STATUS_TONE[value] ?? (value in TONES ? value : "plain")];
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-label font-semibold whitespace-nowrap ${t}`}>
      {value.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}
    </span>
  );
}

export function BandBadge({ band }: { band: string | null }) {
  return band ? <Badge value={band} tone={band as "HIGH"} /> : <span className="text-text-muted">None</span>;
}

export function Figure({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-label font-semibold tracking-wide text-text-muted uppercase">{label}</div>
      <div className="num font-display text-display leading-tight font-semibold md:text-figure">{value}</div>
      {hint && <div className="text-label text-text-muted">{hint}</div>}
    </div>
  );
}

export function Panel({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded border border-border bg-surface" aria-label={title}>
      <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
        <h2 className="font-display text-title font-semibold">{title}</h2>
        {action}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-2 text-text-muted">{children}</p>;
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="py-2 text-text-muted">
      Loading {what}…
    </p>
  );
}

export function ErrorLine({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  return (
    <p role="alert" className="rounded border border-danger bg-danger-subtle px-3 py-2 text-danger">
      {e ? (
        <>
          <span className="font-mono">{e.code}</span>: {e.message}
          {e.requestId && <span className="font-mono text-label"> (request {e.requestId})</span>}
        </>
      ) : (
        "Error: something went wrong. Reload and try again."
      )}
    </p>
  );
}

/** Native modal dialog: focus is trapped and Escape closes it. */
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
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-label={title}
      className="m-auto w-full max-w-2xl rounded border border-border bg-overlay p-0 text-text backdrop:bg-black/50"
    >
      {open && (
        <div className="p-6">
          <h2 className="mb-4 font-display text-heading font-semibold">{title}</h2>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mb-4 block">
      <span className="mb-1 block text-label font-semibold text-text-muted">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded border border-border-strong bg-surface px-3 py-2 text-text placeholder:text-text-disabled";

export function Table({ head, children, numeric = [] }: { head: string[]; children: ReactNode; numeric?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-border-strong text-label text-text-muted uppercase">
            {head.map((h, i) => (
              <th key={h} scope="col" className={`px-2 py-2 font-semibold ${numeric.includes(i) ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export const td = "border-b border-border px-2 py-2 align-top";
export const tdNum = "num border-b border-border px-2 py-2 text-right align-top";

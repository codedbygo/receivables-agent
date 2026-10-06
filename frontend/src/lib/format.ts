/** Display only. Every amount arrives from the API as integer paise computed by the ledger. */
export function inr(paise: number): string {
  if (!Number.isSafeInteger(paise) || paise < 0) return "₹—";
  const rupees = Math.floor(paise / 100);
  const rem = paise % 100;
  const digits = String(rupees);
  let head = digits.slice(0, -3);
  const tail = digits.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  const body = groups.length ? [...groups, tail].join(",") : tail;
  return `₹${body}` + (rem ? `.${String(rem).padStart(2, "0")}` : "");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-05" or an ISO timestamp -> "05 Oct 2026" (the calendar date as written, no timezone shift). */
export function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  const month = MONTHS[Number(m) - 1];
  return y && month && d ? `${d} ${month} ${y}` : iso;
}

/** ISO timestamp -> "05 Oct 2026, 14:05" in India time. */
export function stamp(iso: string): string {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return iso;
  const ist = new Date(t.getTime() + 330 * 60_000).toISOString();
  return `${day(ist)}, ${ist.slice(11, 16)}`;
}

/** Rupees a person typed become integer paise here, the only place the console and portal make an amount. */
export function rupeesToPaise(text: string): number | null {
  const t = text.replaceAll(",", "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  const [r = "0", p = ""] = t.split(".");
  const paise = Number(r) * 100 + Number(p.padEnd(2, "0"));
  return Number.isSafeInteger(paise) && paise > 0 ? paise : null;
}

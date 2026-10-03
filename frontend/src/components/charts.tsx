/** Small single-series charts in plain HTML: thin rounded bars, a baseline, selective direct labels, a hover
tooltip on every mark and a screen-reader table. Values arrive computed; the chart only lays them out. */
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type Bar = { label: string; value: number; display: string };

/** Vertical bars. `labels`: every bar (few, ordered buckets), only the peak and the last, or none (narrow bars). */
export function ColumnChart({
  data,
  caption,
  tones,
  labels = "ends",
}: {
  data: Bar[];
  caption: string;
  tones?: string[];
  labels?: "all" | "ends" | "none";
}) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const peak = data.findIndex((d) => d.value === max);
  return (
    <figure className="flex h-full flex-col">
      <div className="flex h-44 items-end gap-2 border-b" aria-hidden>
        {data.map((d, i) => (
          <Tooltip key={d.label}>
            <TooltipTrigger asChild>
              <div className="group flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
                {(labels === "all" || (labels === "ends" && (i === peak || i === data.length - 1))) && (
                  <span className="num max-w-full truncate text-xs font-semibold">{d.display}</span>
                )}
                <div
                  className={cn(
                    "w-full max-w-12 rounded-t-sm transition-opacity group-hover:opacity-80",
                    tones?.[i] ?? "bg-primary",
                  )}
                  style={{ height: `${Math.max(d.value > 0 ? 2 : 0, (d.value / max) * 100)}%` }}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <span className="font-semibold">{d.label}</span> <span className="num">{d.display}</span>
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
      <div className="mt-2 flex gap-2" aria-hidden>
        {data.map((d) => (
          <span key={d.label} className="min-w-0 flex-1 truncate text-center text-xs text-muted-foreground">
            {d.label}
          </span>
        ))}
      </div>
      <figcaption className="sr-only">{caption}</figcaption>
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.label}>
              <th scope="row">{d.label}</th>
              <td>{d.display}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export type Segment = { label: string; value: number; tone: string };

/** Parts of a whole as one bar with 2px gaps, plus a legend that names every part with its count and share. */
export function ProportionBar({ data, caption, unit }: { data: Segment[]; caption: string; unit: string }) {
  const total = data.reduce((n, d) => n + d.value, 0);
  const shown = data.filter((d) => d.value > 0);
  return (
    <figure>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" aria-hidden>
        {shown.map((d) => (
          <Tooltip key={d.label}>
            <TooltipTrigger asChild>
              <div className={cn("h-full first:rounded-l-full last:rounded-r-full", d.tone)} style={{ flexGrow: d.value }} />
            </TooltipTrigger>
            <TooltipContent>
              {d.label}: <span className="num">{d.value}</span> {unit}
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
      <figcaption className="sr-only">{caption}</figcaption>
      <ul className="mt-4 grid grid-cols-2 gap-3">
        {data.map((d) => (
          <li key={d.label} className="flex items-center gap-2">
            <span aria-hidden className={cn("size-2.5 shrink-0 rounded-full", d.tone)} />
            <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{d.label}</span>
            <span className="num text-sm font-semibold">{d.value}</span>
            <span className="num w-10 text-right text-xs text-muted-foreground">
              {total ? Math.round((d.value / total) * 100) : 0}%
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

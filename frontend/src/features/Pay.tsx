/** S-17 Payment link (public, SIMULATED; US-03-004). No role: the signed token is the credential. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, ErrorLine, Loading } from "../components/ui";
import { api } from "../lib/api";
import { inr } from "../lib/format";
import * as S from "../lib/schemas";

export function Pay({ token }: { token: string }) {
  const link = useQuery({ queryKey: ["pay", token], queryFn: () => api(`/pay/${token}`, S.PayLink), retry: false });
  const pay = useMutation({ mutationFn: () => api(`/pay/${token}`, S.PaymentOut, { method: "POST" }) });
  return (
    <main className="mx-auto max-w-lg px-4 py-12">
      <p role="note" className="mb-6 rounded border-2 border-warning bg-warning-subtle px-4 py-3 text-center font-semibold text-warning">
        SIMULATED payment page for the demo. No money moves.
      </p>
      {link.isPending && <Loading what="the invoice" />}
      <ErrorLine error={link.error} />
      {link.data && (
        <section className="rounded border border-border bg-surface p-6" aria-label="Invoice">
          <p className="text-text-muted">{link.data.customer_name}</p>
          <h1 className="font-display text-display font-semibold">
            Pay <span className="font-mono">{link.data.invoice_number}</span>
          </h1>
          <p className="num my-6 font-display text-figure font-semibold">{inr(link.data.amount_paise)}</p>
          {pay.data ? (
            <p role="status" className="font-semibold text-success">
              Paid {inr(pay.data.amount_paise)}. The invoice is settled in the ledger.
            </p>
          ) : link.data.amount_paise === 0 ? (
            <p className="font-semibold text-success">This invoice is already paid.</p>
          ) : (
            <Button variant="primary" busy={pay.isPending} onClick={() => pay.mutate()}>
              Pay {inr(link.data.amount_paise)} (simulated)
            </Button>
          )}
          <div className="mt-4">
            <ErrorLine error={pay.error} />
          </div>
        </section>
      )}
    </main>
  );
}

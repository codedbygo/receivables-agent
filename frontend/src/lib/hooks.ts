/** Query keys and hooks. The TanStack Query cache is the only copy of server data. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import * as S from "./schemas";

export const keys = {
  me: ["me"] as const,
  dashboard: ["dashboard"] as const,
  customers: ["customers"] as const,
  priorities: ["priorities"] as const,
  customer: (id: string) => ["customer", id] as const,
  messages: (status: string | null, customerId: string | null) => ["messages", status, customerId] as const,
  run: (id: string) => ["run", id] as const,
  runs: ["runs"] as const,
  settings: ["settings"] as const,
  guardrails: ["guardrails"] as const,
  evals: ["evals"] as const,
  payments: ["payments"] as const,
  executive: ["executive"] as const,
  safety: ["safety"] as const,
  followUps: ["follow-ups"] as const,
};

const Timeline = z.object({ data: z.array(S.TimelineEvent), next_action: z.string() });

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => api("/auth/me", S.User), retry: false });
export const useDashboard = () => useQuery({ queryKey: keys.dashboard, queryFn: () => api("/dashboard", S.Dashboard) });
export const useExecutive = () => useQuery({ queryKey: keys.executive, queryFn: () => api("/executive", S.Executive) });
export const useSafety = () => useQuery({ queryKey: keys.safety, queryFn: () => api("/safety", S.Safety) });
export const useFollowUps = () =>
  useQuery({ queryKey: keys.followUps, queryFn: () => api("/follow-ups?filter[status]=open&limit=20", S.page(S.FollowUp)) });
export const useCustomers = () =>
  useQuery({ queryKey: keys.customers, queryFn: () => api("/customers", S.page(S.Customer)) });
export const usePriorities = () =>
  useQuery({ queryKey: keys.priorities, queryFn: () => api("/priorities?limit=50", S.page(S.Priority)) });

export function useCustomer(id: string) {
  return useQuery({
    queryKey: keys.customer(id),
    queryFn: async () => {
      const [customer, invoices, priority, timeline, runs, promises, disputes, messages, followUps] = await Promise.all([
        api(`/customers/${id}`, S.Customer),
        api(`/customers/${id}/invoices`, S.page(S.Invoice)),
        api(`/customers/${id}/priority`, S.Priority),
        api(`/customers/${id}/timeline`, Timeline),
        api(`/customers/${id}/runs`, S.page(S.Run)),
        api(`/promises?filter[customer_id]=${id}`, S.page(S.Promise_)),
        api(`/disputes?filter[customer_id]=${id}`, S.page(S.Dispute)),
        api(`/messages?filter[customer_id]=${id}`, S.page(S.Message)),
        api(`/follow-ups?filter[customer_id]=${id}`, S.page(S.FollowUp)),
      ]);
      return {
        customer,
        invoices: invoices.data,
        priority,
        timeline: timeline.data,
        nextAction: timeline.next_action,
        runs: runs.data,
        promises: promises.data,
        disputes: disputes.data,
        messages: messages.data,
        followUps: followUps.data,
      };
    },
  });
}

export function useMessages(status: string | null, customerId: string | null = null) {
  const q = new URLSearchParams();
  if (status) q.set("filter[status]", status);
  if (customerId) q.set("filter[customer_id]", customerId);
  return useQuery({
    queryKey: keys.messages(status, customerId),
    queryFn: () => api(`/messages?${q.toString()}`, S.page(S.Message)),
  });
}

export const useRun = (id: string | null) =>
  useQuery({ queryKey: keys.run(id ?? ""), queryFn: () => api(`/runs/${id}`, S.Run), enabled: id !== null });
export const useRuns = () => useQuery({ queryKey: keys.runs, queryFn: () => api("/runs?limit=20", S.page(S.Run)) });
export const useSettings = () => useQuery({ queryKey: keys.settings, queryFn: () => api("/admin/settings", S.Settings) });
export const useGuardrailEvents = () =>
  useQuery({ queryKey: keys.guardrails, queryFn: () => api("/admin/guardrail-events?limit=20", S.page(S.GuardrailEvent)) });
export const useEval = () => useQuery({ queryKey: keys.evals, queryFn: () => api("/evals/latest", S.EvalReport), retry: false });
export const usePayments = () =>
  useQuery({ queryKey: keys.payments, queryFn: () => api("/payments?limit=30", S.page(S.Payment)) });

/** Every mutation refreshes everything: one action can move totals, queue, timeline and settings at once. */
export function useAction<A, R>(fn: (args: A) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation<R, Error, A>({ mutationFn: fn, onSettled: () => qc.invalidateQueries() });
}

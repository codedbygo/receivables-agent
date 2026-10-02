/** Hash routes: #/today, #/approvals, #/customers, #/customers/<uuid>, #/admin, #/evals. */
import { useSyncExternalStore } from "react";

export type Route =
  | { page: "today" }
  | { page: "approvals" }
  | { page: "customers" }
  | { page: "customer"; id: string }
  | { page: "admin" }
  | { page: "evals" }
  | { page: "pay"; token: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function parse(hash: string): Route {
  const [, page, id] = hash.replace(/^#/, "").split("/");
  if (page === "customers" && id && UUID.test(id)) return { page: "customer", id };
  if (page === "pay" && id && /^INV-\d+\.\d+\.[0-9a-f]{32}$/.test(id)) return { page: "pay", token: id };
  if (page === "approvals" || page === "customers" || page === "admin" || page === "evals") return { page };
  return { page: "today" };
}

export const href = (r: Route): string =>
  r.page === "customer" ? `#/customers/${r.id}` : r.page === "pay" ? `#/pay/${r.token}` : `#/${r.page}`;

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export const useRoute = (): Route => parse(useSyncExternalStore(subscribe, () => window.location.hash));

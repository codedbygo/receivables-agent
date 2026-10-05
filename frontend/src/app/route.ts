/** Hash routes: #/today, #/executive, #/safety, #/approvals, #/customers, #/customers/<uuid>, #/admin, #/evals. */
import { useSyncExternalStore } from "react";

export type Route =
  | { page: "today" }
  | { page: "approvals" }
  | { page: "customers" }
  | { page: "customer"; id: string }
  | { page: "admin" }
  | { page: "evals" }
  | { page: "executive" }
  | { page: "safety" }
  | { page: "pay"; token: string }
  | { page: "portal"; token: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function parse(hash: string): Route {
  const [, page, id] = hash.replace(/^#/, "").split("/");
  if (page === "customers" && id && UUID.test(id)) return { page: "customer", id };
  if (page === "pay" && id && /^INV-\d+\.\d+\.[0-9a-f]{32}$/.test(id)) return { page: "pay", token: id };
  if (page === "portal" && id && /^[A-Za-z0-9_-]{20,100}$/.test(id)) return { page: "portal", token: id };
  if (page === "approvals" || page === "customers" || page === "admin" || page === "evals" || page === "executive" || page === "safety")
    return { page };
  return { page: "today" };
}

export const href = (r: Route): string =>
  r.page === "customer"
    ? `#/customers/${r.id}`
    : r.page === "pay" || r.page === "portal"
      ? `#/${r.page}/${r.token}`
      : `#/${r.page}`;

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export const useRoute = (): Route => parse(useSyncExternalStore(subscribe, () => window.location.hash));

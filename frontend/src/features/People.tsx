/** People who can sign in (HACK-011, ADR-0019): an admin adds them, changes their role, sets a new password or
switches them off. Nobody signs themselves up. */
import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Dialog, ErrorLine, Field, inputClass, Loading, Panel, Table, td } from "@/components/kit";
import { api } from "@/lib/api";
import { useAction, useMe, usePeople } from "@/lib/hooks";
import * as S from "@/lib/schemas";

const ROLES = ["admin", "collector", "viewer"] as const;

export function PeoplePanel() {
  const people = usePeople();
  const me = useMe();
  const [adding, setAdding] = useState(false);
  const [resetting, setResetting] = useState<S.Person | null>(null);
  const change = useAction(({ id, ...body }: { id: string; role?: S.Role; active?: boolean }) =>
    api(`/users/${id}`, S.Person, { method: "PATCH", body }),
  );
  return (
    <Panel
      title="People"
      action={
        <Button icon={UserPlus} onClick={() => setAdding(true)}>
          Add a person
        </Button>
      }
    >
      {people.isPending ? (
        <Loading what="people" />
      ) : people.error ? (
        <ErrorLine error={people.error} />
      ) : (
        <Table head={["Name", "Email", "Role", "Sign-in", ""]}>
          {people.data.data.map((p) => {
            const self = p.id === me.data?.id;
            return (
              <tr key={p.id} className={p.active ? "" : "text-muted-foreground"}>
                <td className={td}>{p.display_name}</td>
                <td className={td}>{p.email}</td>
                <td className={td}>
                  <label className="sr-only" htmlFor={`role-${p.id}`}>
                    Role for {p.email}
                  </label>
                  <select
                    id={`role-${p.id}`}
                    className={inputClass}
                    value={p.role}
                    disabled={self || !p.active || change.isPending}
                    onChange={(e) => change.mutate({ id: p.id, role: S.Role.parse(e.target.value) })}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td className={td}>
                  <span className="flex flex-wrap gap-1">
                    <Badge value={p.has_password ? "password or Google" : "Google only"} tone="plain" />
                    {p.locked && <Badge value="locked" tone="wait" />}
                    {!p.active && <Badge value="switched off" tone="bad" />}
                  </span>
                </td>
                <td className={td}>
                  <span className="flex flex-wrap justify-end gap-2">
                    {p.active && <Button onClick={() => setResetting(p)}>Set password</Button>}
                    {!self && (
                      <Button
                        variant={p.active ? "danger" : "quiet"}
                        busy={change.isPending && change.variables?.id === p.id}
                        onClick={() => change.mutate({ id: p.id, active: !p.active })}
                      >
                        {p.active ? "Switch off" : "Switch on"}
                      </Button>
                    )}
                  </span>
                </td>
              </tr>
            );
          })}
        </Table>
      )}
      <ErrorLine error={change.error} />
      {adding && <AddPerson onClose={() => setAdding(false)} />}
      {resetting && <SetPassword person={resetting} onClose={() => setResetting(null)} />}
    </Panel>
  );
}

function AddPerson({ onClose }: { onClose: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<S.Role>("collector");
  const [password, setPassword] = useState("");
  const add = useAction(() =>
    api("/users", S.Person, {
      method: "POST",
      body: { email: email.trim(), display_name: name.trim(), role, ...(password ? { password } : {}) },
    }),
  );
  return (
    <Dialog title="Add a person" open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <Field label="Email">
          <input className={inputClass} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required maxLength={254} />
        </Field>
        <Field label="Name shown on their actions">
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required maxLength={100} />
        </Field>
        <Field label="Role">
          <select className={inputClass} value={role} onChange={(e) => setRole(S.Role.parse(e.target.value))}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Temporary password (at least 10 characters; leave empty for Google sign-in only)">
          <input
            className={inputClass}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={10}
            maxLength={200}
          />
        </Field>
        <ErrorLine error={add.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={add.isPending} disabled={!email.trim() || !name.trim()}>
            Add
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function SetPassword({ person, onClose }: { person: S.Person; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const set = useAction(() => api(`/users/${person.id}`, S.Person, { method: "PATCH", body: { password } }));
  return (
    <Dialog title={`Set a new password for ${person.email}`} open onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          set.mutate(undefined, { onSuccess: onClose });
        }}
      >
        <p className="mb-3 text-text-muted">Give it to them in person or by phone. It also clears a lock from wrong passwords.</p>
        <Field label="New password (at least 10 characters)">
          <input
            className={inputClass}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={10}
            maxLength={200}
          />
        </Field>
        <ErrorLine error={set.error} />
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" busy={set.isPending} disabled={password.length < 10}>
            Set password
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

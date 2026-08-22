import { FormEvent, useEffect, useState } from "react";
import { ApiRequestError, createOperator, disableOperator, listOperators } from "./api";
import type { Operator } from "./types";

export function OperatorsView() {
  const [operators, setOperators] = useState<Operator[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"operator" | "admin">("operator");
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    listOperators()
      .then(setOperators)
      .catch((caught: unknown) => {
        setError(caught instanceof ApiRequestError ? caught.message : "Could not load operators");
      });
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createOperator(username, password, role);
      setUsername("");
      setPassword("");
      refresh();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not create operator");
    }
  }

  return (
    <section className="panel">
      <h2>Operators</h2>
      {error ? <p className="error">{error}</p> : null}
      <ul>
        {operators.map((item) => (
          <li key={item.id}>
            {item.username} · {item.role}
            {item.enabled ? "" : " · disabled"}
            {item.enabled ? (
              <button type="button" onClick={() => disableOperator(item.id).then(refresh)}>
                Disable
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <form onSubmit={onCreate}>
        <h3>Add operator</h3>
        <label>
          Identity
          <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>
          Secret
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value as "operator" | "admin")}>
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button type="submit">Add</button>
      </form>
    </section>
  );
}

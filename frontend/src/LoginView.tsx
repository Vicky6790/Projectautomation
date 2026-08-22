import { useState, type FormEvent } from "react";
import { ApiRequestError, signIn } from "./api";
import type { Operator } from "./types";

export function LoginView({ onSignedIn }: { onSignedIn: (operator: Operator) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await signIn(username, password));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={onSubmit}>
      <h2>Sign in</h2>
      <p className="muted">This environment requires an operator session.</p>
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
      {error ? <p className="error">{error}</p> : null}
      <button type="submit" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

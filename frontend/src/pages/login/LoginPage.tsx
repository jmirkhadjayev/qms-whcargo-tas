import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { homePathFor } from "../../auth/roles";
import { useLogin, useMe } from "../../auth/useAuth";
import { uz } from "../../i18n/uz";

export function LoginPage() {
  const { data: user } = useMe();
  const login = useLogin({ failed: uz.login.failed, network: uz.login.networkError });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState(false);

  if (user) return <Navigate to={homePathFor(user.role)} replace />;

  const usernameMissing = touched && username.trim() === "";
  const passwordMissing = touched && password === "";

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (username.trim() === "" || password === "") return;
    login.mutate({ username: username.trim(), password });
  }

  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4">
      <form
        onSubmit={onSubmit}
        noValidate
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded bg-accent font-mono text-lg font-semibold text-ink">
            YN
          </span>
          <div>
            <div className="font-semibold text-ink">{uz.app.name}</div>
            <div className="text-xs text-slate-500">{uz.app.airport}</div>
          </div>
        </div>
        <h1 className="mb-4 text-xl font-semibold text-ink">{uz.login.title}</h1>

        <label className="mb-1 block text-sm font-medium" htmlFor="username">
          {uz.login.username}
        </label>
        <input
          id="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="mb-1 w-full rounded border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        {usernameMissing && <p className="mb-2 text-sm text-red-600">{uz.login.required}</p>}

        <label className="mb-1 mt-3 block text-sm font-medium" htmlFor="password">
          {uz.login.password}
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-1 w-full rounded border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        {passwordMissing && <p className="mb-2 text-sm text-red-600">{uz.login.required}</p>}

        {login.error && (
          <p role="alert" className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
            {login.error.message}
          </p>
        )}

        <button
          type="submit"
          disabled={login.isPending}
          className="mt-5 w-full rounded bg-ink px-4 py-2.5 font-medium text-white hover:bg-ink/90 disabled:opacity-60"
        >
          {login.isPending ? uz.login.submitting : uz.login.submit}
        </button>
      </form>
    </div>
  );
}

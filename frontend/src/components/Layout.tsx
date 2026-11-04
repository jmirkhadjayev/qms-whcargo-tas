import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { ROLE_SECTIONS, SECTION_PATH } from "../auth/roles";
import { useLogout, useMe } from "../auth/useAuth";
import { uz } from "../i18n/uz";

function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

const dateFmt = new Intl.DateTimeFormat("uz-Latn", {
  timeZone: "Asia/Tashkent",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const timeFmt = new Intl.DateTimeFormat("uz-Latn", {
  timeZone: "Asia/Tashkent",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function Layout() {
  const { data: user } = useMe();
  const logout = useLogout();
  const now = useNow();
  if (!user) return null;

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-8 gap-y-2 bg-ink px-4 py-3 text-white sm:px-6">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded bg-accent font-mono text-lg font-semibold text-ink">
            YN
          </span>
          <div className="leading-tight">
            <div className="font-semibold">{uz.app.name}</div>
            <div className="text-xs text-slate-300">{uz.app.airport}</div>
          </div>
        </div>
        <nav className="order-last flex w-full gap-1 sm:order-none sm:w-auto">
          {ROLE_SECTIONS[user.role].map((section) => (
            <NavLink
              key={section}
              to={SECTION_PATH[section]}
              className={({ isActive }) =>
                `rounded px-3 py-1.5 text-sm ${
                  isActive ? "bg-accent font-medium text-ink" : "text-slate-200 hover:bg-white/10"
                }`
              }
            >
              {uz.sections[section]}
            </NavLink>
          ))}
        </nav>
        <div className="num ml-auto hidden text-right text-sm text-slate-200 sm:block">
          <div>{dateFmt.format(now)}</div>
          <div className="text-base text-white">{timeFmt.format(now)}</div>
        </div>
        <div className="ml-auto flex items-center gap-3 text-sm sm:ml-0 sm:border-l sm:border-white/20 sm:pl-6">
          <div className="text-right leading-tight">
            <div className="font-medium">{user.full_name}</div>
            <div className="text-xs text-slate-300">{uz.roles[user.role]}</div>
          </div>
          <button
            type="button"
            onClick={() => logout.mutate()}
            className="rounded border border-white/30 px-3 py-1.5 hover:bg-white/10"
          >
            {uz.layout.logout}
          </button>
        </div>
      </header>
      <main className="p-4 sm:p-6">
        <Outlet />
      </main>
    </div>
  );
}

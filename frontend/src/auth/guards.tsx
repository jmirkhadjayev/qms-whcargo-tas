import { Navigate, Outlet } from "react-router-dom";

import { uz } from "../i18n/uz";
import { canOpen, homePathFor, type RoleCode, type SectionKey } from "./roles";
import { useMe } from "./useAuth";

/** Any logged-in user; anonymous visitors go to /login. */
export function RequireAuth() {
  const { data: user, isLoading } = useMe();
  if (isLoading) return <p className="p-6">{uz.app.loading}</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/** Pages that are not a menu section (e.g. the ticket print page) but still limited to some roles. */
export function RequireRoles({ roles }: { roles: RoleCode[] }) {
  const { data: user, isLoading } = useMe();
  if (isLoading) return <p className="p-6">{uz.app.loading}</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) return <Navigate to={homePathFor(user.role)} replace />;
  return <Outlet />;
}

/** Only roles that may open `section`; others are sent to their own home page. */
export function RequireSection({ section }: { section: SectionKey }) {
  const { data: user, isLoading } = useMe();
  if (isLoading) return <p className="p-6">{uz.app.loading}</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (!canOpen(user.role, section)) return <Navigate to={homePathFor(user.role)} replace />;
  return <Outlet />;
}

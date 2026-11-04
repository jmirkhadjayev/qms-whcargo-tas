import type { ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRoles, RequireSection } from "./auth/guards";
import { SECTION_PATH, homePathFor, type SectionKey } from "./auth/roles";
import { useMe } from "./auth/useAuth";
import { Layout } from "./components/Layout";
import { SectionPlaceholder } from "./components/SectionPlaceholder";
import { HallDisplay } from "./displays/hall/HallDisplay";
import { LedDisplay } from "./displays/led/LedDisplay";
import { CheckpointPage } from "./pages/checkpoint/CheckpointPage";
import { DispatcherPage } from "./pages/dispatcher/DispatcherPage";
import { DockPage } from "./pages/dock/DockPage";
import { LoginPage } from "./pages/login/LoginPage";
import { RegistrationPage } from "./pages/registration/RegistrationPage";
import { TicketPrintPage } from "./pages/ticket/TicketPrintPage";
import { WarehousePage } from "./pages/warehouse/WarehousePage";

const SECTIONS: SectionKey[] = [
  "registration",
  "dispatcher",
  "dock",
  "warehouse",
  "checkpoint",
  "reports",
  "admin",
];

// Sections that already have their real screen; the rest show a placeholder.
const SCREENS: Partial<Record<SectionKey, ReactElement>> = {
  registration: <RegistrationPage />,
  dispatcher: <DispatcherPage />,
  dock: <DockPage />,
  checkpoint: <CheckpointPage />,
  warehouse: <WarehousePage />,
};

function HomeRedirect() {
  const { data: user, isLoading } = useMe();
  if (isLoading) return null;
  return <Navigate to={user ? homePathFor(user.role) : "/login"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Kiosk screens: no login (allowed network or screen token, checked by the server). */}
      <Route path="/display/hall" element={<HallDisplay />} />
      <Route path="/display/led/:code" element={<LedDisplay />} />
      <Route element={<RequireAuth />}>
        {/* Standalone page (no top bar): printed on the 80 mm ticket printer. */}
        <Route element={<RequireRoles roles={["REG_AGENT", "SUPERVISOR"]} />}>
          <Route path="/print/ticket/:id" element={<TicketPrintPage />} />
        </Route>
        <Route element={<Layout />}>
          {SECTIONS.map((section) => (
            <Route key={section} element={<RequireSection section={section} />}>
              <Route
                path={SECTION_PATH[section]}
                element={SCREENS[section] ?? <SectionPlaceholder section={section} />}
              />
            </Route>
          ))}
        </Route>
      </Route>
      <Route path="*" element={<HomeRedirect />} />
    </Routes>
  );
}

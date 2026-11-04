import { useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { uz } from "../../i18n/uz";
import { useScreenData } from "../useScreenData";

type Led = components["schemas"]["Led"];
const t = uz.display;

/**
 * The LED board above one dock (kiosk): ticket number and vehicle plate, big. Nothing else.
 * Calling = yellow (pulses on a repeat call), serving = green, idle = dark, maintenance = grey.
 */
export function LedDisplay() {
  const code = (useParams().code ?? "").toUpperCase();
  const { data, forbidden, offline } = useScreenData<Led>(
    ["led", code],
    `/ws/display/led/${code}/`,
    (token) =>
      api.GET("/api/display/led/{code}/", { params: { path: { code }, query: { token } } }),
  );

  if (forbidden) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#0B1118] text-[5vw] text-white">
        {t.forbidden}
      </div>
    );
  }

  const current = data?.current ?? null;
  const maintenance = data?.state === "MAINTENANCE";
  const tone = maintenance
    ? "bg-slate-700 text-slate-300"
    : current?.phase === "CALLING"
      ? `bg-[#F2A900] text-[#0B1118] ${current.recall ? "animate-pulse" : ""}`
      : current?.phase === "SERVING"
        ? "bg-green-600 text-white"
        : "bg-[#0B1118] text-slate-400";

  const label = maintenance
    ? t.ledMaintenance
    : current?.phase === "CALLING"
      ? t.ledCalling
      : current?.phase === "SERVING"
        ? t.ledServing
        : t.ledIdle;

  return (
    <div className={`flex min-h-screen flex-col justify-between p-[3vw] ${tone}`} data-testid="led">
      <div className="flex items-start justify-between">
        <span className="num text-[9vw] font-semibold leading-none" data-testid="led-dock">
          {code}
        </span>
        <span className="text-[3.5vw] font-semibold uppercase">{offline ? t.offline : label}</span>
      </div>
      {current && !maintenance ? (
        <div className="text-center">
          <div className="num text-[26vw] font-semibold leading-none" data-testid="led-number">
            {current.queue_number}
          </div>
          <div className="num mt-[2vw] text-[8vw] leading-none" data-testid="led-plate">
            {current.vehicle_plate || "—"}
          </div>
        </div>
      ) : (
        <div className="text-center text-[8vw] font-semibold">{label}</div>
      )}
      <div className="text-center text-[2vw] opacity-70">{uz.app.airport}</div>
    </div>
  );
}

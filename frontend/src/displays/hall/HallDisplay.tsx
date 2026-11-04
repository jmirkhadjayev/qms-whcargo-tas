import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { uz } from "../../i18n/uz";
import { useScreenData } from "../useScreenData";

type Hall = components["schemas"]["Hall"];
const t = uz.display;

const timeFmt = new Intl.DateTimeFormat("uz-Latn", {
  timeZone: "Asia/Tashkent",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 10_000);
    return () => clearInterval(id);
  }, []);
  return <span className="num">{timeFmt.format(now)}</span>;
}

/**
 * The waiting-hall board (1920×1080, kiosk). Shows ticket number, dock and plate only — never a
 * name or phone number (TZ 3.4). Sizes are relative to the screen width so it fits any TV.
 */
export function HallDisplay() {
  const { data, forbidden, offline } = useScreenData<Hall>(["hall"], "/ws/display/hall/", (token) =>
    api.GET("/api/display/hall/", { params: { query: { token } } }),
  );

  if (forbidden) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#0B1118] text-[3vw] text-white">
        {t.forbidden}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#0B1118] p-[2vw] text-white">
      <header className="flex items-center justify-between border-b border-white/15 pb-[1.2vw]">
        <div>
          <div className="text-[2.6vw] font-semibold leading-none">{t.hallTitle}</div>
          <div className="mt-[0.4vw] text-[1.2vw] text-slate-400">{uz.app.airport}</div>
        </div>
        <div className="flex items-center gap-[1.5vw] text-[3vw] font-semibold">
          {offline && <span className="text-[1.2vw] font-normal text-red-400">{t.offline}</span>}
          <Clock />
        </div>
      </header>

      <div className="mt-[1.5vw] grid flex-1 grid-cols-[2fr_1fr] gap-[2vw]">
        <section aria-label={t.called}>
          <h2 className="mb-[1vw] text-[1.8vw] font-semibold uppercase tracking-wide text-[#F2A900]">
            {t.called}
          </h2>
          <div className="mb-[0.5vw] grid grid-cols-[1fr_1fr_2fr] gap-[1vw] px-[1.5vw] text-[1.3vw] uppercase text-slate-400">
            <span>{t.ticket}</span>
            <span>{t.dock}</span>
            <span>{t.plate}</span>
          </div>
          {data && data.called.length === 0 ? (
            <p className="mt-[4vw] text-center text-[2.4vw] text-slate-500">{t.nobody}</p>
          ) : (
            <ul className="space-y-[0.7vw]">
              {data?.called.map((row) => (
                <li
                  key={`${row.queue_number}-${row.dock}`}
                  data-testid="called-row"
                  className={`grid grid-cols-[1fr_1fr_2fr] items-center gap-[1vw] rounded-[0.8vw] px-[1.5vw] py-[0.9vw] ${
                    row.recall ? "animate-pulse bg-[#F2A900] text-[#0B1118]" : "bg-white/10"
                  }`}
                >
                  <span className="num text-[4.4vw] font-semibold leading-none">
                    {row.queue_number}
                  </span>
                  <span className="num text-[4.4vw] font-semibold leading-none">{row.dock}</span>
                  <span className="num flex items-center gap-[1vw] text-[3.2vw] leading-none">
                    {row.vehicle_plate || "—"}
                    {row.recall && (
                      <span className="rounded bg-[#0B1118] px-[0.8vw] py-[0.3vw] text-[1.2vw] uppercase text-[#F2A900]">
                        {t.recall}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label={t.preparing} className="border-l border-white/15 pl-[2vw]">
          <h2 className="mb-[1vw] text-[1.8vw] font-semibold uppercase tracking-wide text-slate-300">
            {t.preparing}
          </h2>
          <ul className="grid grid-cols-3 gap-[0.7vw]">
            {data?.preparing.map((row) => (
              <li
                key={row.queue_number}
                data-testid="preparing-row"
                className="num rounded-[0.6vw] bg-white/5 py-[0.6vw] text-center text-[2.4vw] text-slate-200"
              >
                {row.queue_number}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

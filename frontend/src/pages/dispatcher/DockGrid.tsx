import { uz, type StatusCode } from "../../i18n/uz";
import type { DockCard } from "./api";

const d = uz.dispatcher;

const STATE_STYLE: Record<string, string> = {
  FREE: "bg-green-100 text-green-800",
  BUSY: "bg-amber-100 text-amber-900",
  MAINTENANCE: "bg-slate-200 text-slate-600",
};

export function DockGrid({
  docks,
  busy,
  onToggleMaintenance,
}: {
  docks: DockCard[];
  busy: boolean;
  onToggleMaintenance: (code: string, maintenance: boolean) => void;
}) {
  return (
    <section aria-label={d.docks}>
      <h2 className="mb-2 font-semibold text-ink">{d.docks}</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {docks.map((dock) => (
          <article
            key={dock.code}
            data-testid={`dock-${dock.code}`}
            className={`rounded-lg border bg-white p-3 ${
              dock.state === "MAINTENANCE" ? "border-slate-300 opacity-80" : "border-slate-200"
            }`}
          >
            <header className="flex items-center justify-between">
              <span className="num text-xl font-semibold text-ink">{dock.code}</span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${STATE_STYLE[dock.state]}`}
              >
                {d.dockState[dock.state as keyof typeof d.dockState]}
              </span>
            </header>
            <div className="mt-2 min-h-10 text-sm">
              {dock.request ? (
                <>
                  <div className="num font-medium">
                    № {dock.request.queue_number}
                    {dock.request.vehicle_plate && (
                      <span className="ml-2 text-slate-600">{dock.request.vehicle_plate}</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500">
                    {uz.statuses[dock.request.status as StatusCode]}
                  </div>
                </>
              ) : (
                <span className="text-slate-400">{uz.common.none}</span>
              )}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {dock.agent ? (
                <>
                  <span
                    className={`mr-1 inline-block h-2 w-2 rounded-full ${
                      dock.agent_ready ? "bg-green-500" : "bg-amber-400"
                    }`}
                  />
                  {dock.agent}
                </>
              ) : (
                d.noAgent
              )}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {dock.categories.map((code) => (
                <span
                  key={code}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600"
                >
                  {code}
                </span>
              ))}
            </div>
            <button
              type="button"
              disabled={busy || dock.state === "BUSY"}
              onClick={() => onToggleMaintenance(dock.code, dock.state !== "MAINTENANCE")}
              className="mt-2 text-xs text-slate-600 underline disabled:no-underline disabled:opacity-40"
            >
              {dock.state === "MAINTENANCE" ? d.fromMaintenance : d.toMaintenance}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

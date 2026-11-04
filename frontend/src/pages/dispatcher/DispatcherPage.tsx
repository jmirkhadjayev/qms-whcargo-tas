import { useState } from "react";

import { LiveBadge } from "../../components/LiveBadge";
import { uz } from "../../i18n/uz";
import { useLiveRefresh } from "../../lib/live";
import {
  DISPATCHER_KEY,
  useAssignDock,
  useCallRequest,
  useDecideRemainder,
  useExceptions,
  useOverview,
  useQueue,
  useRecallRequest,
  useResolveException,
  useResumeRequest,
  useSetMaintenance,
  useSetPriority,
} from "./api";
import { AttentionPanel } from "./AttentionPanel";
import { DockGrid } from "./DockGrid";
import { QueueTable } from "./QueueTable";

const d = uz.dispatcher;
const KPI_ORDER = [
  "registered_today",
  "in_preparation",
  "waiting_dock",
  "at_dock",
  "completed_today",
  "open_exceptions",
  "avg_wait_minutes",
] as const;

export function DispatcherPage() {
  const live = useLiveRefresh("/ws/dispatcher/", [DISPATCHER_KEY]);
  const overview = useOverview();
  const queue = useQueue();
  const assign = useAssignDock();
  const callRequest = useCallRequest();
  const recallRequest = useRecallRequest();
  const exceptions = useExceptions();
  const resolve = useResolveException();
  const resume = useResumeRequest();
  const decide = useDecideRemainder();
  const priority = useSetPriority();
  const maintenance = useSetMaintenance();
  const [error, setError] = useState<string | null>(null);
  const busy =
    assign.isPending ||
    priority.isPending ||
    maintenance.isPending ||
    callRequest.isPending ||
    recallRequest.isPending ||
    resolve.isPending ||
    resume.isPending ||
    decide.isPending;

  const handlers = {
    onError: (e: Error) => setError(e.message),
    onSuccess: () => setError(null),
  };

  const kpi = overview.data?.kpi;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-ink">{d.title}</h1>
        <LiveBadge status={live} />
      </div>

      {error && (
        <p role="alert" className="rounded border border-red-300 bg-red-50 px-4 py-3 text-red-900">
          {error}
        </p>
      )}

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7" aria-label="KPI">
        {KPI_ORDER.map((key) => (
          <div key={key} className="rounded-lg border border-slate-200 bg-white p-3">
            <div className="text-xs text-slate-500">{d.kpi[key]}</div>
            <div className="num mt-1 text-3xl font-semibold text-ink" data-testid={`kpi-${key}`}>
              {kpi ? (kpi[key] ?? uz.common.none) : uz.common.none}
              {key === "avg_wait_minutes" && kpi?.avg_wait_minutes != null && (
                <span className="ml-1 text-sm font-normal text-slate-500">{uz.common.minutes}</span>
              )}
            </div>
          </div>
        ))}
      </section>

      <DockGrid
        docks={overview.data?.docks ?? []}
        busy={busy}
        onToggleMaintenance={(code, on) => maintenance.mutate({ code, maintenance: on }, handlers)}
      />

      <AttentionPanel
        exceptions={exceptions.data ?? []}
        queue={queue.data ?? []}
        busy={busy}
        onResolve={(id, resolution) => resolve.mutate({ id, resolution }, handlers)}
        onResume={(id, reason) => resume.mutate({ id, reason }, handlers)}
        onReprep={(id) => decide.mutate({ id, to: "AWAITING_PREP" }, handlers)}
        onClose={(id, reason) => decide.mutate({ id, to: "CLOSED", reason }, handlers)}
      />

      <QueueTable
        rows={queue.data ?? []}
        busy={busy}
        onAssign={(id, dock) => assign.mutate({ id, dock }, handlers)}
        onCall={(id) => callRequest.mutate(id, handlers)}
        onRecall={(id) => recallRequest.mutate(id, handlers)}
        onPriority={(id, value) => priority.mutate({ id, priority: value }, handlers)}
      />
    </div>
  );
}

import { useState } from "react";

import { uz, type StatusCode } from "../../i18n/uz";
import type { WarehouseTask } from "./api";

const w = uz.warehouse;

const STATUS_STYLE: Record<string, string> = {
  NEW: "bg-slate-100 text-slate-700",
  IN_PROGRESS: "bg-blue-100 text-blue-800",
  READY: "bg-green-100 text-green-800",
  HANDED_OVER: "bg-slate-100 text-slate-500",
  PROBLEM: "bg-red-100 text-red-800",
};

const btn = "rounded px-4 py-3 text-base font-semibold disabled:opacity-50";

export function TaskCard({
  task,
  highlighted = false,
  busy,
  onStart,
  onReady,
  onProblem,
  onHandOver,
}: {
  task: WarehouseTask;
  highlighted?: boolean;
  busy: boolean;
  onStart: (location: string) => void;
  onReady: () => void;
  onProblem: () => void;
  onHandOver: () => void;
}) {
  const [location, setLocation] = useState(task.storage_location);
  const request = task.request;
  const suspended = request.status === "SUSPENDED";
  const canProblem = ["NEW", "IN_PROGRESS", "READY"].includes(task.status);

  return (
    <article
      data-testid={`task-${task.id}`}
      className={`rounded-lg border bg-white p-4 shadow-sm ${
        highlighted ? "border-accent ring-2 ring-accent" : "border-slate-200"
      }`}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs text-slate-500">{uz.registration.columns.number}</div>
          <div className="num text-5xl font-semibold leading-none text-ink">
            {request.queue_number}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 text-xs">
          <span
            className={`rounded px-2 py-1 font-medium ${STATUS_STYLE[task.status] ?? STATUS_STYLE.NEW}`}
          >
            {w.taskStatus[task.status as keyof typeof w.taskStatus] ?? task.status}
          </span>
          <span
            className={`rounded px-2 py-1 font-medium ${
              request.special_handling ? "bg-accent text-ink" : "bg-slate-100 text-slate-600"
            }`}
            title={request.special_handling ? w.special : undefined}
          >
            {request.category}
            {request.special_handling ? " ⚠" : ""}
          </span>
          {request.priority > 0 && (
            <span className="rounded bg-amber-100 px-2 py-1 font-medium text-amber-800">
              {w.priority} {request.priority}
            </span>
          )}
        </div>
      </header>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-slate-500">{w.fields.awb}</dt>
        <dd className="num text-right">{request.awb_number}</dd>
        <dt className="text-slate-500">{w.fields.pieces}</dt>
        <dd className="num text-right">{request.pieces_total}</dd>
        <dt className="text-slate-500">{w.fields.weight}</dt>
        <dd className="num text-right">{request.weight_kg} kg</dd>
        <dt className="text-slate-500">{w.fields.dock}</dt>
        <dd className="num text-right">{request.dock ?? uz.common.none}</dd>
        {task.status !== "NEW" && (
          <>
            <dt className="text-slate-500">{w.fields.location}</dt>
            <dd className="text-right">{task.storage_location || uz.common.none}</dd>
          </>
        )}
        {request.notes && (
          <>
            <dt className="text-slate-500">{w.fields.notes}</dt>
            <dd className="text-right">{request.notes}</dd>
          </>
        )}
      </dl>

      <p className="mt-2 text-xs text-slate-500">
        {uz.statuses[request.status as StatusCode] ?? request.status}
      </p>

      {suspended && (
        <p role="alert" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {w.suspended}
        </p>
      )}

      {task.status === "NEW" && !suspended && (
        <div className="mt-4 space-y-3">
          <input
            aria-label={w.fields.location}
            placeholder={w.locationPlaceholder}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => onStart(location)}
            className={`${btn} w-full bg-ink text-white`}
          >
            {w.start}
          </button>
        </div>
      )}

      {task.status === "IN_PROGRESS" && !suspended && (
        <button
          type="button"
          disabled={busy}
          onClick={onReady}
          className={`${btn} mt-4 w-full bg-green-600 text-white`}
        >
          {w.ready}
        </button>
      )}

      {task.status === "READY" && (
        <div className="mt-4">
          <button
            type="button"
            disabled={busy || !request.dock}
            onClick={onHandOver}
            className={`${btn} w-full bg-ink text-white`}
          >
            {w.handOver}
          </button>
          {!request.dock && <p className="mt-1 text-xs text-slate-500">{w.needsDock}</p>}
        </div>
      )}

      {task.status === "PROBLEM" && (
        <p className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{w.problemHeld}</p>
      )}

      {canProblem && (
        <button
          type="button"
          disabled={busy}
          onClick={onProblem}
          className={`${btn} mt-3 w-full border border-red-300 bg-white text-red-700`}
        >
          {w.problem}
        </button>
      )}
    </article>
  );
}

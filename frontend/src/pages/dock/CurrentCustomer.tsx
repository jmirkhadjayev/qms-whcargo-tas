import { uz, type StatusCode } from "../../i18n/uz";
import { formatCountdown, useSecondsLeft } from "../../lib/countdown";
import { formatTime } from "../../lib/dates";
import type { AgentCurrent } from "./api";
import { ReleasePanel } from "./ReleasePanel";

const d = uz.dock;

export function CurrentCustomer({
  current,
  busy,
  onArrive,
  onRecall,
  onStartRelease,
  onProgress,
  onFinish,
  onPartial,
  onProblem,
}: {
  current: AgentCurrent;
  busy: boolean;
  onArrive: () => void;
  onRecall: () => void;
  onStartRelease: () => void;
  onProgress: (pieces: number) => void;
  onFinish: () => void;
  onPartial: () => void;
  onProblem: () => void;
}) {
  const secondsLeft = useSecondsLeft(current.timeout_at);
  const called = current.status === "CALLED";
  const waiting = current.status === "DOCK_ASSIGNED";

  const headline = waiting
    ? d.waitingTitle
    : called
      ? d.called
      : current.status === "ARRIVED"
        ? d.arrived
        : d.serving;

  return (
    <section
      aria-label={headline}
      className={`rounded-lg border-2 bg-white p-5 ${
        called ? "border-accent" : "border-slate-200"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm text-slate-500">{headline}</div>
          <div
            className="num text-7xl font-semibold leading-none text-ink"
            data-testid="current-number"
          >
            {current.queue_number}
          </div>
          {current.vehicle_plate && (
            <div className="num mt-2 inline-block rounded bg-slate-100 px-3 py-1 text-xl">
              {current.vehicle_plate}
            </div>
          )}
        </div>
        {called && secondsLeft !== null && (
          <div className="text-right">
            <div className="text-xs text-slate-500">{d.timeLeft}</div>
            <div
              data-testid="countdown"
              className={`num text-4xl font-semibold ${secondsLeft === 0 ? "text-red-600" : "text-ink"}`}
            >
              {secondsLeft === 0 ? d.timeUp : formatCountdown(secondsLeft)}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {d.attempt} {current.attempt_no} · {d.recallsLeft}: {current.recalls_left}
            </div>
          </div>
        )}
      </div>

      {waiting && (
        <div className="mt-4 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {current.blockers.length === 0 ? (
            d.waitingText
          ) : (
            <>
              {d.waitingForReady}
              <ul className="mt-1 list-disc pl-5">
                {current.blockers.map((code) => (
                  <li key={code}>
                    {uz.callBlockers[code as keyof typeof uz.callBlockers] ?? code}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <dt className="text-slate-500">{d.consignee}</dt>
        <dd className="text-right">{current.consignee_name}</dd>
        {current.representative_name && (
          <>
            <dt className="text-slate-500">{d.representative}</dt>
            <dd className="text-right">{current.representative_name}</dd>
          </>
        )}
        <dt className="text-slate-500">AWB</dt>
        <dd className="num text-right">{current.awb_number}</dd>
        <dt className="text-slate-500">{d.pieces}</dt>
        <dd className="num text-right">{current.pieces_total}</dd>
        <dt className="text-slate-500">{d.weight}</dt>
        <dd className="num text-right">{current.weight_kg} kg</dd>
        <dt className="text-slate-500">{uz.warehouse.fields.category}</dt>
        <dd className="text-right">
          <span
            className={`rounded px-2 py-0.5 text-xs ${
              current.special_handling ? "bg-accent text-ink" : "bg-slate-100 text-slate-600"
            }`}
            title={current.special_handling ? d.special : undefined}
          >
            {current.category}
            {current.special_handling ? " ⚠" : ""}
          </span>
        </dd>
        {current.notes && (
          <>
            <dt className="text-slate-500">{d.notes}</dt>
            <dd className="text-right">{current.notes}</dd>
          </>
        )}
      </dl>

      {called && (
        <div className="mt-5 flex gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={onArrive}
            className="flex-1 rounded bg-green-600 px-4 py-3 text-lg font-semibold text-white disabled:opacity-50"
          >
            {d.arrive}
          </button>
          <button
            type="button"
            disabled={busy || current.recalls_left === 0}
            onClick={onRecall}
            className="rounded border border-slate-300 px-4 py-3 font-medium disabled:opacity-40"
          >
            {d.recall}
          </button>
        </div>
      )}

      {current.status === "ARRIVED" && (
        <button
          type="button"
          disabled={busy}
          onClick={onStartRelease}
          className="mt-5 w-full rounded bg-ink px-4 py-3 text-lg font-semibold text-white disabled:opacity-50"
        >
          {d.release.start}
        </button>
      )}

      {current.status === "RELEASE_STARTED" && (
        <ReleasePanel
          current={current}
          busy={busy}
          onProgress={onProgress}
          onFinish={onFinish}
          onPartial={onPartial}
        />
      )}

      {!waiting && (
        <button
          type="button"
          disabled={busy}
          onClick={onProblem}
          className="mt-3 w-full rounded border border-red-300 bg-white px-4 py-2 font-medium text-red-700 disabled:opacity-50"
        >
          {d.problem}
        </button>
      )}

      <div className="mt-5">
        <h3 className="mb-1 text-sm font-semibold text-ink">{d.history}</h3>
        <ol className="space-y-0.5 text-xs text-slate-600">
          {current.history.map((entry, index) => (
            <li key={index} className="flex justify-between gap-3">
              <span>{uz.statuses[entry.to_status as StatusCode] ?? entry.to_status}</span>
              <span className="num text-slate-400">{formatTime(entry.changed_at)}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

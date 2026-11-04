import { useState } from "react";

import { uz, type StatusCode } from "../../i18n/uz";
import type { CheckSummary } from "./api";

const c = uz.checkpoint;
const CHECKS = ["ticket", "plate", "pieces", "docs"] as const;
type Check = (typeof CHECKS)[number];

/** The checklist the officer goes through before letting a vehicle out (screen 9). */
export function CheckCard({
  summary,
  busy,
  onConfirm,
  onHold,
}: {
  summary: CheckSummary;
  busy: boolean;
  onConfirm: (plate: string) => void;
  onHold: (plate: string) => void;
}) {
  const [ticked, setTicked] = useState<Record<Check, boolean>>({
    ticket: false,
    plate: false,
    pieces: false,
    docs: false,
  });
  const [plate, setPlate] = useState("");
  const allTicked = CHECKS.every((key) => ticked[key]);
  const partial = summary.pieces_remaining > 0;

  return (
    <section
      aria-label={`№ ${summary.queue_number}`}
      className="rounded-lg border-2 border-ink bg-white p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div
            className="num text-7xl font-semibold leading-none text-ink"
            data-testid="check-number"
          >
            {summary.queue_number}
          </div>
          <div className="num mt-2 text-sm text-slate-500">{summary.awb_number}</div>
        </div>
        <div className="text-right text-sm">
          <div className="font-medium">{summary.consignee_name}</div>
          <span
            className={`mt-1 inline-block rounded px-2 py-0.5 text-xs ${
              summary.special_handling ? "bg-accent text-ink" : "bg-slate-100 text-slate-600"
            }`}
          >
            {summary.category}
            {summary.special_handling ? " ⚠" : ""}
          </span>
          <div className="mt-1 text-xs text-slate-500">
            {uz.statuses[summary.status as StatusCode]}
          </div>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-base">
        <dt className="text-slate-500">{c.registeredPlate}</dt>
        <dd className="num text-right text-2xl font-semibold" data-testid="registered-plate">
          {summary.vehicle_plate || uz.common.none}
        </dd>
        <dt className="text-slate-500">{c.pieces}</dt>
        <dd className="num text-right text-2xl font-semibold" data-testid="pieces">
          {summary.pieces_released} / {summary.pieces_total}
        </dd>
        {partial && (
          <>
            <dt className="text-amber-800">{c.remainder}</dt>
            <dd className="num text-right font-semibold text-amber-800">
              {summary.pieces_remaining}
            </dd>
          </>
        )}
      </dl>

      {summary.open_problems.length > 0 && (
        <div className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <div className="font-medium">{c.openProblems}</div>
          <ul className="list-disc pl-5">
            {summary.open_problems.map((problem, index) => (
              <li key={index}>{problem.description || problem.kind}</li>
            ))}
          </ul>
        </div>
      )}

      {!summary.can_confirm ? (
        <p role="alert" className="mt-4 rounded bg-red-50 px-3 py-3 text-red-800">
          {summary.blocked_reason}
        </p>
      ) : (
        <>
          <fieldset className="mt-4">
            <legend className="mb-1 text-sm font-semibold text-ink">{c.checklist}</legend>
            <div className="space-y-2">
              {CHECKS.map((key) => (
                <label
                  key={key}
                  className="flex cursor-pointer items-center gap-3 rounded border border-slate-200 px-3 py-3 text-lg"
                >
                  <input
                    type="checkbox"
                    className="h-6 w-6"
                    checked={ticked[key]}
                    onChange={(e) => setTicked((prev) => ({ ...prev, [key]: e.target.checked }))}
                  />
                  {c.checks[key]}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="mt-3">
            <label htmlFor="plate-observed" className="mb-1 block text-sm font-medium">
              {c.plateObserved}
            </label>
            <input
              id="plate-observed"
              value={plate}
              onChange={(e) => setPlate(e.target.value)}
              className="num w-full rounded border border-slate-300 px-3 py-3 text-xl uppercase focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
          </div>

          <div className="mt-4 grid grid-cols-[2fr_1fr] gap-3">
            <button
              type="button"
              disabled={busy || !allTicked}
              onClick={() => onConfirm(plate)}
              className="rounded bg-green-600 px-4 py-4 text-xl font-semibold text-white disabled:opacity-40"
            >
              {c.confirm}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => onHold(plate)}
              className="rounded border-2 border-red-400 bg-white px-4 py-4 text-xl font-semibold text-red-700 disabled:opacity-40"
            >
              {c.hold}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

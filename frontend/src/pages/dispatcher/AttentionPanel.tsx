import { useState } from "react";

import { uz, type StatusCode } from "../../i18n/uz";
import type { ExceptionRow, QueueRow } from "./api";

const a = uz.dispatcher.attention;

function ReasonForm({
  label,
  submit,
  busy,
  onSubmit,
  tone = "ink",
}: {
  label: string;
  submit: string;
  busy: boolean;
  onSubmit: (text: string) => void;
  tone?: "ink" | "green";
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState(false);
  return (
    <form
      noValidate
      className="mt-2 flex flex-wrap items-start gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!text.trim()) {
          setError(true);
          return;
        }
        onSubmit(text.trim());
        setText("");
      }}
    >
      <div className="min-w-48 flex-1">
        <input
          aria-label={label}
          placeholder={label}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError(false);
          }}
          className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
        {error && (
          <p role="alert" className="mt-0.5 text-xs text-red-600">
            {a.reasonRequired}
          </p>
        )}
      </div>
      <button
        type="submit"
        disabled={busy}
        className={`rounded px-3 py-1 text-sm font-medium text-white disabled:opacity-50 ${
          tone === "green" ? "bg-green-600" : "bg-ink"
        }`}
      >
        {submit}
      </button>
    </form>
  );
}

/** What waits for the supervisor's decision: open problems, suspended requests, remainders. */
export function AttentionPanel({
  exceptions,
  queue,
  busy,
  onResolve,
  onResume,
  onReprep,
  onClose,
}: {
  exceptions: ExceptionRow[];
  queue: QueueRow[];
  busy: boolean;
  onResolve: (id: number, resolution: string) => void;
  onResume: (id: number, reason: string) => void;
  onReprep: (id: number) => void;
  onClose: (id: number, reason: string) => void;
}) {
  const suspended = queue.filter((row) => row.status === "SUSPENDED");
  const decisions = queue.filter(
    (row) => row.status === "EXIT_CONFIRMED" && row.remaining_pieces > 0,
  );
  const nothing = exceptions.length + suspended.length + decisions.length === 0;

  return (
    <section aria-label={a.title} className="rounded-lg border border-slate-200 bg-white">
      <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">
        {a.title}
        <span className="num ml-2 text-slate-500">
          {exceptions.length + suspended.length + decisions.length}
        </span>
      </h2>
      {nothing && <p className="p-4 text-slate-500">{a.none}</p>}

      {exceptions.length > 0 && (
        <div className="border-b border-slate-100 p-4">
          <h3 className="mb-2 text-sm font-semibold text-red-800">{a.problems}</h3>
          <ul className="space-y-3">
            {exceptions.map((item) => (
              <li key={item.id} data-testid={`exception-${item.id}`} className="text-sm">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="num text-lg font-semibold">№ {item.queue_number}</span>
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">
                    {a.kinds[item.kind as keyof typeof a.kinds] ?? item.kind}
                  </span>
                  <span className="text-xs text-slate-500">
                    {uz.statuses[item.request_status as StatusCode]}
                  </span>
                  {item.reported_by && (
                    <span className="text-xs text-slate-500">
                      {a.by}: {item.reported_by}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-slate-700">{item.description}</p>
                <ReasonForm
                  label={a.resolution}
                  submit={a.resolve}
                  busy={busy}
                  onSubmit={(text) => onResolve(item.id, text)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {suspended.length > 0 && (
        <div className="border-b border-slate-100 p-4">
          <h3 className="mb-2 text-sm font-semibold text-amber-800">{a.suspended}</h3>
          <ul className="space-y-3">
            {suspended.map((row) => (
              <li key={row.id} data-testid={`suspended-${row.queue_number}`} className="text-sm">
                <span className="num text-lg font-semibold">№ {row.queue_number}</span>
                {row.suspended_from && (
                  <span className="ml-3 text-xs text-slate-500">
                    {uz.statuses[row.suspended_from as StatusCode]}
                  </span>
                )}
                <ReasonForm
                  label={a.resumeReason}
                  submit={a.resume}
                  busy={busy}
                  onSubmit={(text) => onResume(row.id, text)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}

      {decisions.length > 0 && (
        <div className="p-4">
          <h3 className="mb-2 text-sm font-semibold text-ink">{a.decisions}</h3>
          <ul className="space-y-3">
            {decisions.map((row) => (
              <li key={row.id} data-testid={`decision-${row.queue_number}`} className="text-sm">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="num text-lg font-semibold">№ {row.queue_number}</span>
                  <span className="text-slate-600">
                    {a.remainder}: <span className="num font-semibold">{row.remaining_pieces}</span>
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => onReprep(row.id)}
                    className="rounded bg-green-600 px-3 py-1 font-medium text-white disabled:opacity-50"
                  >
                    {a.reprep}
                  </button>
                </div>
                <ReasonForm
                  label={a.closeReason}
                  submit={a.close}
                  busy={busy}
                  onSubmit={(text) => onClose(row.id, text)}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

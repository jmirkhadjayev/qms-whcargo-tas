import { useState, type FormEvent } from "react";

import { uz } from "../../i18n/uz";
import type { PartialReason } from "./api";

const d = uz.dock.release.partialDialog;
const REASONS: PartialReason[] = ["MISSING", "DAMAGE", "SHORTAGE", "CUSTOMER", "OTHER"];

/** Partial release: the reason and a comment are mandatory (TZ 5.2). */
export function PartialDialog({
  queueNumber,
  given,
  total,
  submitting,
  onCancel,
  onSubmit,
}: {
  queueNumber: number;
  given: number;
  total: number;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (value: { reason: PartialReason; comment: string }) => void;
}) {
  const [reason, setReason] = useState<PartialReason>("DAMAGE");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!comment.trim()) {
      setError(d.commentRequired);
      return;
    }
    onSubmit({ reason, comment: comment.trim() });
  }

  const input =
    "w-full rounded border border-slate-300 bg-white px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/50 p-4">
      <form
        role="dialog"
        aria-modal="true"
        aria-label={d.title}
        onSubmit={submit}
        noValidate
        className="w-full max-w-md space-y-4 rounded-xl bg-white p-5 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-ink">
          {d.title} <span className="num text-slate-500">№ {queueNumber}</span>
        </h2>
        <dl className="num grid grid-cols-2 gap-1 rounded bg-slate-50 p-3 text-sm">
          <dt className="text-slate-500">{d.given}</dt>
          <dd className="text-right font-semibold">
            {given} / {total}
          </dd>
          <dt className="text-slate-500">{d.notGiven}</dt>
          <dd className="text-right font-semibold text-amber-800">{total - given}</dd>
        </dl>
        <div>
          <label htmlFor="partial-reason" className="mb-1 block text-sm font-medium">
            {d.reason}
          </label>
          <select
            id="partial-reason"
            className={input}
            value={reason}
            onChange={(e) => setReason(e.target.value as PartialReason)}
          >
            {REASONS.map((value) => (
              <option key={value} value={value}>
                {d.reasons[value]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="partial-comment" className="mb-1 block text-sm font-medium">
            {d.comment}
          </label>
          <textarea
            id="partial-comment"
            rows={3}
            className={input}
            value={comment}
            onChange={(e) => {
              setComment(e.target.value);
              setError(null);
            }}
          />
          {error && (
            <p role="alert" className="mt-1 text-sm text-red-600">
              {error}
            </p>
          )}
        </div>
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="flex-1 rounded bg-amber-500 px-4 py-3 font-semibold text-ink disabled:opacity-60"
          >
            {d.submit}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-4 py-3"
          >
            {uz.common.cancel}
          </button>
        </div>
      </form>
    </div>
  );
}

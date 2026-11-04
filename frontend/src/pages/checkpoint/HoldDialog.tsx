import { useState, type FormEvent } from "react";

import { uz } from "../../i18n/uz";

const c = uz.checkpoint;

/** A discrepancy: stop the exit and describe what is wrong (TZ 5.4 items 1-2). */
export function HoldDialog({
  queueNumber,
  submitting,
  onCancel,
  onSubmit,
}: {
  queueNumber: number;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (description: string) => void;
}) {
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!description.trim()) {
      setError(c.holdRequired);
      return;
    }
    onSubmit(description.trim());
  }

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/50 p-4">
      <form
        role="dialog"
        aria-modal="true"
        aria-label={c.holdTitle}
        onSubmit={submit}
        noValidate
        className="w-full max-w-lg space-y-4 rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 className="text-xl font-semibold text-red-700">
          {c.holdTitle} <span className="num text-slate-500">№ {queueNumber}</span>
        </h2>
        <div>
          <label htmlFor="hold-description" className="mb-1 block font-medium">
            {c.holdDescription}
          </label>
          <textarea
            id="hold-description"
            rows={4}
            autoFocus
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setError(null);
            }}
            className="w-full rounded border border-slate-300 px-3 py-2 text-lg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          {error && (
            <p role="alert" className="mt-1 text-red-600">
              {error}
            </p>
          )}
        </div>
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="flex-1 rounded bg-red-600 px-4 py-4 text-lg font-semibold text-white disabled:opacity-60"
          >
            {c.holdSubmit}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-5 py-4 text-lg"
          >
            {uz.common.cancel}
          </button>
        </div>
      </form>
    </div>
  );
}

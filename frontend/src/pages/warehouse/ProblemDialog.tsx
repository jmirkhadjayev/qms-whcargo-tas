import { useState, type FormEvent } from "react";

import { uz } from "../../i18n/uz";
import type { ProblemKind } from "./api";

const d = uz.warehouse.problemDialog;
const KINDS: ProblemKind[] = ["MISSING", "DAMAGE", "SHORTAGE", "MISMATCH"];

export function ProblemDialog({
  queueNumber,
  submitting,
  onCancel,
  onSubmit,
}: {
  queueNumber: number;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (value: { kind: ProblemKind; description: string; piecesAffected: number }) => void;
}) {
  const [kind, setKind] = useState<ProblemKind>("DAMAGE");
  const [pieces, setPieces] = useState("0");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!description.trim()) {
      setError(d.descriptionRequired);
      return;
    }
    onSubmit({
      kind,
      description: description.trim(),
      piecesAffected: Math.max(0, Number.parseInt(pieces, 10) || 0),
    });
  }

  const input =
    "w-full rounded border border-slate-300 bg-white px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

  return (
    <div className="fixed inset-0 z-20 grid place-items-end bg-black/50 sm:place-items-center">
      <form
        role="dialog"
        aria-modal="true"
        aria-label={d.title}
        onSubmit={submit}
        noValidate
        className="w-full max-w-md space-y-4 rounded-t-xl bg-white p-5 shadow-xl sm:rounded-xl"
      >
        <h2 className="text-lg font-semibold text-ink">
          {d.title} <span className="num text-slate-500">№ {queueNumber}</span>
        </h2>
        <div>
          <label htmlFor="problem-kind" className="mb-1 block text-sm font-medium">
            {d.kind}
          </label>
          <select
            id="problem-kind"
            className={input}
            value={kind}
            onChange={(e) => setKind(e.target.value as ProblemKind)}
          >
            {KINDS.map((value) => (
              <option key={value} value={value}>
                {d.kinds[value]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="problem-pieces" className="mb-1 block text-sm font-medium">
            {d.pieces}
          </label>
          <input
            id="problem-pieces"
            inputMode="numeric"
            className={`${input} num`}
            value={pieces}
            onChange={(e) => setPieces(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="problem-description" className="mb-1 block text-sm font-medium">
            {d.description}
          </label>
          <textarea
            id="problem-description"
            rows={3}
            className={input}
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
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
            className="flex-1 rounded bg-red-600 px-4 py-3 font-semibold text-white disabled:opacity-60"
          >
            {uz.common.send}
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

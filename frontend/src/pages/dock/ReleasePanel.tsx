import { useState } from "react";

import { uz } from "../../i18n/uz";
import type { AgentCurrent } from "./api";

const r = uz.dock.release;

/**
 * The release counter (TZ 5.2). The agent counts the pieces handed over; "finish" needs all of
 * them, "partial" is for when part of the cargo cannot be handed over.
 */
export function ReleasePanel({
  current,
  busy,
  onProgress,
  onFinish,
  onPartial,
}: {
  current: AgentCurrent;
  busy: boolean;
  onProgress: (pieces: number) => void;
  onFinish: () => void;
  onPartial: () => void;
}) {
  const [typed, setTyped] = useState<string | null>(null);
  const earlier = current.pieces_released - current.operation_pieces;
  const limit = current.pieces_total - earlier; // the most this round can hand over
  const finishable = current.pieces_remaining === 0;

  function set(value: number) {
    setTyped(null);
    onProgress(Math.min(limit, Math.max(0, value)));
  }

  return (
    <section aria-label={r.title} className="mt-5 rounded-lg bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-ink">{r.title}</h3>
      <div className="mt-2 flex items-center justify-center gap-4">
        <button
          type="button"
          aria-label={r.minus}
          disabled={busy || current.operation_pieces <= 0}
          onClick={() => set(current.operation_pieces - 1)}
          className="h-14 w-14 rounded-full border border-slate-300 bg-white text-3xl disabled:opacity-30"
        >
          −
        </button>
        <div className="text-center">
          <input
            aria-label={r.thisRound}
            inputMode="numeric"
            value={typed ?? String(current.operation_pieces)}
            onChange={(e) => setTyped(e.target.value.replace(/\D/g, ""))}
            onBlur={() => typed !== null && set(Number(typed || "0"))}
            onKeyDown={(e) => e.key === "Enter" && typed !== null && set(Number(typed || "0"))}
            className="num w-28 rounded border border-slate-300 bg-white py-1 text-center text-5xl font-semibold"
          />
          <div className="mt-1 text-xs text-slate-500">{r.thisRound}</div>
        </div>
        <button
          type="button"
          aria-label={r.plus}
          disabled={busy || current.operation_pieces >= limit}
          onClick={() => set(current.operation_pieces + 1)}
          className="h-14 w-14 rounded-full border border-slate-300 bg-white text-3xl disabled:opacity-30"
        >
          +
        </button>
      </div>
      <div className="num mt-2 text-center text-sm text-slate-600" data-testid="release-totals">
        {r.total}: {current.pieces_released} / {current.pieces_total} · {r.remaining}:{" "}
        {current.pieces_remaining}
      </div>
      <button
        type="button"
        disabled={busy || current.operation_pieces >= limit}
        onClick={() => set(limit)}
        className="mx-auto mt-2 block text-sm text-slate-600 underline disabled:opacity-40"
      >
        {r.all}
      </button>

      <div className="mt-4 flex gap-3">
        <button
          type="button"
          disabled={busy || !finishable}
          onClick={onFinish}
          className="flex-1 rounded bg-green-600 px-4 py-3 text-lg font-semibold text-white disabled:opacity-40"
        >
          {r.finish}
        </button>
        <button
          type="button"
          disabled={busy || finishable}
          onClick={onPartial}
          className="flex-1 rounded border border-amber-400 bg-amber-50 px-4 py-3 text-lg font-semibold text-amber-900 disabled:opacity-40"
        >
          {r.partial}
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-500">{finishable ? r.partialHint : r.finishHint}</p>
    </section>
  );
}

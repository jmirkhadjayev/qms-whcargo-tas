import { useState, type FormEvent } from "react";

import { LiveBadge } from "../../components/LiveBadge";
import { uz } from "../../i18n/uz";
import { formatTime } from "../../lib/dates";
import { useLiveRefresh } from "../../lib/live";
import {
  CHECKPOINT_KEY,
  useConfirm,
  useHold,
  useOverview,
  useScan,
  type CheckSummary,
} from "./api";
import { CheckCard } from "./CheckCard";
import { HoldDialog } from "./HoldDialog";

const c = uz.checkpoint;

/** Checkpoint tablet (screen 9): scan the ticket, tick the checklist, confirm or hold. */
export function CheckpointPage() {
  const live = useLiveRefresh("/ws/checkpoint/", [CHECKPOINT_KEY]);
  const overview = useOverview();
  const scan = useScan();
  const confirm = useConfirm();
  const hold = useHold();

  const [code, setCode] = useState("");
  const [summary, setSummary] = useState<CheckSummary | null>(null);
  const [holdPlate, setHoldPlate] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  const busy = scan.isPending || confirm.isPending || hold.isPending;

  function open(value: string) {
    if (!value.trim()) return;
    setNotice(null);
    scan.mutate(value.trim(), {
      onSuccess: (found) => {
        setSummary(found);
        setCode("");
      },
      onError: (e) => {
        setSummary(null);
        setNotice({ text: e.message, ok: false });
      },
    });
  }

  function onScan(event: FormEvent) {
    event.preventDefault();
    open(code);
  }

  function onConfirm(plate: string) {
    if (!summary) return;
    setNotice(null);
    confirm.mutate(
      { id: summary.id, plate },
      {
        onSuccess: () => {
          setSummary(null);
          setNotice({ text: c.confirmed, ok: true });
        },
        // e.g. a plate that differs from the request: the officer must record a discrepancy
        onError: (e) => setNotice({ text: e.message, ok: false }),
      },
    );
  }

  const data = overview.data;

  return (
    <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-ink">{c.title}</h1>
          <LiveBadge status={live} />
        </div>

        <form onSubmit={onScan} className="flex gap-2">
          <input
            aria-label={c.scanLabel}
            autoFocus
            autoComplete="off"
            placeholder={c.scanPlaceholder}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="num min-w-0 flex-1 rounded border border-slate-300 px-4 py-4 text-xl focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-ink px-6 py-4 text-lg font-semibold text-white disabled:opacity-60"
          >
            {c.scanSubmit}
          </button>
        </form>

        {notice && (
          <p
            role={notice.ok ? "status" : "alert"}
            className={`rounded px-4 py-3 text-lg ${
              notice.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
            }`}
          >
            {notice.text}
          </p>
        )}

        {summary && (
          <CheckCard
            key={summary.id}
            summary={summary}
            busy={busy}
            onConfirm={onConfirm}
            onHold={(plate) => setHoldPlate(plate)}
          />
        )}
      </div>

      <div className="space-y-4">
        <section className="rounded-lg border border-slate-200 bg-white">
          <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">
            {c.waiting} <span className="num ml-2 text-slate-500">{data?.waiting.length ?? 0}</span>
          </h2>
          {data && data.waiting.length === 0 ? (
            <p className="p-4 text-slate-500">{c.waitingEmpty}</p>
          ) : (
            <ul>
              {data?.waiting.map((row) => (
                <li key={row.id} className="border-t border-slate-100 first:border-t-0">
                  <button
                    type="button"
                    onClick={() => open(String(row.queue_number))}
                    className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
                  >
                    <span className="num text-2xl font-semibold">{row.queue_number}</span>
                    <span className="num text-slate-600">
                      {row.vehicle_plate || uz.common.none}
                    </span>
                    {row.is_partial && (
                      <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                        {c.partial} {row.pieces_released}/{row.pieces_total}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white">
          <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">{c.recent}</h2>
          {data && data.recent.length === 0 ? (
            <p className="p-4 text-slate-500">{c.recentEmpty}</p>
          ) : (
            <ul className="text-sm">
              {data?.recent.map((row, index) => (
                <li
                  key={index}
                  className="flex items-center justify-between border-t border-slate-100 px-4 py-2 first:border-t-0"
                >
                  <span className="num text-lg font-semibold">{row.queue_number}</span>
                  <span
                    className={
                      row.result === "HELD" ? "font-medium text-red-700" : "text-green-700"
                    }
                  >
                    {c.result[row.result]}
                  </span>
                  <span className="num text-slate-500">{formatTime(row.scanned_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {holdPlate !== null && summary && (
        <HoldDialog
          queueNumber={summary.queue_number}
          submitting={hold.isPending}
          onCancel={() => setHoldPlate(null)}
          onSubmit={(description) =>
            hold.mutate(
              { id: summary.id, description, plate: holdPlate },
              {
                onSuccess: () => {
                  setHoldPlate(null);
                  setSummary(null);
                  setNotice({ text: c.held, ok: true });
                },
                onError: (e) => {
                  setHoldPlate(null);
                  setNotice({ text: e.message, ok: false });
                },
              },
            )
          }
        />
      )}
    </div>
  );
}

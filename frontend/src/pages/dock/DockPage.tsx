import { useState, type FormEvent } from "react";

import { LiveBadge } from "../../components/LiveBadge";
import { uz } from "../../i18n/uz";
import { formatTime } from "../../lib/dates";
import { useLiveRefresh } from "../../lib/live";
import {
  DOCK_KEY,
  useAgentScreen,
  useArrive,
  useCheckIn,
  useCheckOut,
  useDockProblem,
  useFinishRelease,
  usePartialRelease,
  useRecall,
  useScanTicket,
  useSetProgress,
  useStartRelease,
} from "./api";
import { ProblemDialog } from "../warehouse/ProblemDialog";
import { CurrentCustomer } from "./CurrentCustomer";
import { PartialDialog } from "./PartialDialog";

const d = uz.dock;

export function DockPage() {
  const screen = useAgentScreen();
  const dockCode = screen.data?.dock?.code ?? null;
  // The dock's own channel only exists once the agent has signed in to a dock.
  const live = useLiveRefresh(dockCode ? `/ws/dock/${dockCode}/` : null, [DOCK_KEY]);
  const checkIn = useCheckIn();
  const checkOut = useCheckOut();
  const arrive = useArrive();
  const recall = useRecall();
  const scan = useScanTicket();
  const startRelease = useStartRelease();
  const setProgress = useSetProgress();
  const finishRelease = useFinishRelease();
  const partialRelease = usePartialRelease();
  const dockProblem = useDockProblem();
  const [dialog, setDialog] = useState<"partial" | "problem" | null>(null);

  const [code, setCode] = useState("");
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy =
    checkIn.isPending ||
    checkOut.isPending ||
    arrive.isPending ||
    recall.isPending ||
    scan.isPending ||
    startRelease.isPending ||
    setProgress.isPending ||
    finishRelease.isPending ||
    partialRelease.isPending ||
    dockProblem.isPending;

  const callbacks = {
    onSuccess: () => setError(null),
    onError: (e: Error) => setError(e.message),
  };

  function onScan(event: FormEvent) {
    event.preventDefault();
    if (!code.trim()) return;
    setMessage(null);
    scan.mutate(code.trim(), {
      onSuccess: (found) => {
        setCode("");
        if (found.status !== "CALLED") {
          setMessage({ text: d.scanNotCalled, ok: false });
          return;
        }
        // Scanning the ticket identifies the customer: that is the arrival at the dock.
        arrive.mutate(found.id, {
          onSuccess: () => setMessage({ text: d.scanAccepted, ok: true }),
          onError: (e) => setMessage({ text: e.message, ok: false }),
        });
      },
      onError: (e) => setMessage({ text: e.message, ok: false }),
    });
  }

  if (screen.isLoading || !screen.data) return <p className="text-slate-500">{uz.app.loading}</p>;
  const data = screen.data;

  // --- not signed in to a dock yet ---------------------------------------------------------------
  if (!data.dock) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <h1 className="text-2xl font-semibold text-ink">{d.pickTitle}</h1>
        <p className="text-slate-600">{d.pickHint}</p>
        {error && (
          <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}
        {data.available_docks.length === 0 ? (
          <p className="rounded bg-amber-50 px-4 py-3 text-amber-900">{d.noFreeDocks}</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {data.available_docks.map((dock) => (
              <button
                key={dock.code}
                type="button"
                disabled={busy}
                onClick={() => checkIn.mutate(dock.code, callbacks)}
                className="rounded-lg border border-slate-200 bg-white p-4 text-left hover:border-accent disabled:opacity-50"
              >
                <div className="num text-2xl font-semibold text-ink">{dock.code}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {dock.categories.map((c) => (
                    <span key={c} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px]">
                      {c}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // --- signed in --------------------------------------------------------------------------------------
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold text-ink">
            {d.title} <span className="num">{data.dock.code}</span>
            <span className="ml-3 rounded bg-green-100 px-2 py-0.5 text-sm font-medium text-green-800">
              {d.ready}
              {data.dock.ready_since && (
                <span className="num ml-1 text-green-700">{formatTime(data.dock.ready_since)}</span>
              )}
            </span>
          </h1>
          <div className="flex items-center gap-4">
            <LiveBadge status={live} />
            <button
              type="button"
              disabled={busy}
              onClick={() => checkOut.mutate(undefined, callbacks)}
              className="text-sm text-slate-600 underline disabled:opacity-50"
            >
              {d.checkOut}
            </button>
          </div>
        </div>

        {error && (
          <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}

        <form onSubmit={onScan} className="flex gap-2">
          <input
            aria-label={d.scanLabel}
            autoFocus
            autoComplete="off"
            placeholder={d.scanPlaceholder}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="num min-w-0 flex-1 rounded border border-slate-300 px-3 py-3 text-lg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-ink px-4 py-3 font-semibold text-white disabled:opacity-60"
          >
            {d.scanSubmit}
          </button>
        </form>
        {message && (
          <p
            role={message.ok ? "status" : "alert"}
            className={`rounded px-3 py-2 text-sm ${
              message.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
            }`}
          >
            {message.text}
          </p>
        )}

        {data.current ? (
          <CurrentCustomer
            current={data.current}
            busy={busy}
            onArrive={() => arrive.mutate(data.current!.id, callbacks)}
            onRecall={() => recall.mutate(data.current!.id, callbacks)}
            onStartRelease={() => startRelease.mutate(data.current!.id, callbacks)}
            onProgress={(pieces) => setProgress.mutate({ id: data.current!.id, pieces }, callbacks)}
            onFinish={() =>
              finishRelease.mutate(data.current!.id, {
                onSuccess: () => setMessage({ text: d.release.done, ok: true }),
                onError: callbacks.onError,
              })
            }
            onPartial={() => setDialog("partial")}
            onProblem={() => setDialog("problem")}
          />
        ) : (
          <section className="rounded-lg border border-slate-200 bg-white p-8 text-center">
            <h2 className="text-xl font-semibold text-ink">{d.waitingTitle}</h2>
            <p className="mt-1 text-slate-500">{d.waitingText}</p>
          </section>
        )}
      </div>

      <section className="h-fit rounded-lg border border-slate-200 bg-white">
        <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">{d.next}</h2>
        {data.next.length === 0 ? (
          <p className="p-4 text-slate-500">{d.nextEmpty}</p>
        ) : (
          <ul>
            {data.next.map((row) => (
              <li
                key={row.queue_number}
                className="flex items-center justify-between border-t border-slate-100 px-4 py-2 first:border-t-0"
              >
                <span className="num text-xl font-semibold">{row.queue_number}</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{row.category}</span>
                <span className="num text-sm text-slate-500">
                  {row.wait_minutes} {uz.common.minutes}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {dialog === "partial" && data.current && (
        <PartialDialog
          queueNumber={data.current.queue_number}
          given={data.current.pieces_released}
          total={data.current.pieces_total}
          submitting={partialRelease.isPending}
          onCancel={() => setDialog(null)}
          onSubmit={(value) =>
            partialRelease.mutate(
              { id: data.current!.id, ...value },
              {
                onSuccess: () => {
                  setDialog(null);
                  setMessage({ text: d.release.partialDone, ok: true });
                },
                onError: (e) => {
                  setDialog(null);
                  setError(e.message);
                },
              },
            )
          }
        />
      )}

      {dialog === "problem" && data.current && (
        <ProblemDialog
          queueNumber={data.current.queue_number}
          submitting={dockProblem.isPending}
          onCancel={() => setDialog(null)}
          onSubmit={(value) =>
            dockProblem.mutate(
              { id: data.current!.id, ...value },
              {
                onSuccess: () => setDialog(null),
                onError: (e) => {
                  setDialog(null);
                  setError(e.message);
                },
              },
            )
          }
        />
      )}
    </div>
  );
}

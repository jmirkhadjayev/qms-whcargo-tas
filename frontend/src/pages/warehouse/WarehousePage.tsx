import { useState, type FormEvent } from "react";

import { ApiProblem } from "../../api/call";
import { LiveBadge } from "../../components/LiveBadge";
import { uz } from "../../i18n/uz";
import { useLiveRefresh } from "../../lib/live";
import {
  WAREHOUSE_KEY,
  useHandOverTask,
  useReadyTask,
  useReportProblem,
  useScan,
  useStartTask,
  useTasks,
  type WarehouseTask,
} from "./api";
import { ProblemDialog } from "./ProblemDialog";
import { TaskCard } from "./TaskCard";

const w = uz.warehouse;
const TABS = ["NEW", "IN_PROGRESS", "READY", "PROBLEM"] as const;
type Tab = (typeof TABS)[number];

export function WarehousePage() {
  const live = useLiveRefresh("/ws/warehouse/", [WAREHOUSE_KEY]);
  const tasks = useTasks();
  const scan = useScan();
  const start = useStartTask();
  const ready = useReadyTask();
  const handOver = useHandOverTask();
  const problem = useReportProblem();

  const [tab, setTab] = useState<Tab>("NEW");
  const [code, setCode] = useState("");
  const [scanned, setScanned] = useState<WarehouseTask | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [problemFor, setProblemFor] = useState<WarehouseTask | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const all = tasks.data ?? [];
  const counts = Object.fromEntries(
    TABS.map((t) => [t, all.filter((task) => task.status === t).length]),
  );
  const visible = all.filter((task) => task.status === tab);
  const busy = start.isPending || ready.isPending || handOver.isPending || problem.isPending;

  function onScan(event: FormEvent) {
    event.preventDefault();
    if (!code.trim()) return;
    setScanMessage(null);
    scan.mutate(code.trim(), {
      onSuccess: (task) => {
        setScanned(task);
        setCode("");
      },
      onError: (error) => {
        setScanned(null);
        setScanMessage(error instanceof ApiProblem ? error.message : w.scanNotFound);
      },
    });
  }

  // After any action the server's answer replaces the scanned card, so it never goes stale.
  function callbacks() {
    setActionError(null);
    return {
      onSuccess: (task: WarehouseTask) =>
        setScanned((current) => (current && current.id === task.id ? task : current)),
      onError: (error: Error) => setActionError(error.message),
    };
  }

  function renderCard(task: WarehouseTask, highlighted = false) {
    return (
      <TaskCard
        key={task.id}
        task={task}
        highlighted={highlighted}
        busy={busy}
        onStart={(storageLocation) => start.mutate({ id: task.id, storageLocation }, callbacks())}
        onReady={() => ready.mutate(task.id, callbacks())}
        onHandOver={() => handOver.mutate(task.id, callbacks())}
        onProblem={() => setProblemFor(task)}
      />
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-ink">{w.title}</h1>
        <LiveBadge status={live} />
      </div>

      <form onSubmit={onScan} className="flex gap-2">
        <input
          aria-label={w.scanLabel}
          autoFocus
          autoComplete="off"
          inputMode="text"
          placeholder={w.scanPlaceholder}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="num min-w-0 flex-1 rounded border border-slate-300 px-3 py-3 text-lg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <button
          type="submit"
          disabled={scan.isPending}
          className="rounded bg-ink px-4 py-3 font-semibold text-white disabled:opacity-60"
        >
          {w.scanSubmit}
        </button>
      </form>
      {scanMessage && (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {scanMessage}
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {actionError}
        </p>
      )}

      {scanned && (
        <section aria-label={w.scanned} className="space-y-2">
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span>{w.scanned}</span>
            <button type="button" className="underline" onClick={() => setScanned(null)}>
              {uz.common.close}
            </button>
          </div>
          {renderCard(scanned, true)}
        </section>
      )}

      <nav
        className="grid grid-cols-4 gap-1 rounded-lg bg-white p-1 shadow-sm"
        aria-label={w.tabsLabel}
      >
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={tab === t}
            onClick={() => setTab(t)}
            className={`rounded px-1 py-2 text-sm ${
              tab === t ? "bg-ink font-semibold text-white" : "text-slate-600"
            }`}
          >
            {w.tabs[t]} <span className="num">({counts[t]})</span>
          </button>
        ))}
      </nav>

      {tasks.isLoading ? (
        <p className="text-slate-500">{uz.app.loading}</p>
      ) : visible.length === 0 ? (
        <p className="py-6 text-center text-slate-500">{w.empty}</p>
      ) : (
        <div className="space-y-3">{visible.map((task) => renderCard(task))}</div>
      )}

      {problemFor && (
        <ProblemDialog
          queueNumber={problemFor.request.queue_number}
          submitting={problem.isPending}
          onCancel={() => setProblemFor(null)}
          onSubmit={(value) => {
            setActionError(null);
            problem.mutate(
              { id: problemFor.id, ...value },
              {
                onSuccess: () => {
                  setProblemFor(null);
                  setScanned((current) => (current?.id === problemFor.id ? null : current));
                },
                onError: (error) => {
                  setProblemFor(null);
                  setActionError(error.message);
                },
              },
            );
          }}
        />
      )}
    </div>
  );
}

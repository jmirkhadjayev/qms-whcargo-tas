import { useState } from "react";

import { uz, type StatusCode } from "../../i18n/uz";
import type { QueueRow } from "./api";

const d = uz.dispatcher;
const c = d.columns;
const MAX_PRIORITY = 9;

function CalledCell({
  row,
  busy,
  onCall,
  onRecall,
}: {
  row: QueueRow;
  busy: boolean;
  onCall: (id: number) => void;
  onRecall: (id: number) => void;
}) {
  return (
    <div className="space-y-1">
      <span className="num font-medium">{row.dock}</span>
      {row.status === "DOCK_ASSIGNED" && (
        <div className="text-xs">
          {row.call_blockers.length > 0 && (
            <div className="text-amber-700">
              {row.call_blockers
                .map((code) => uz.callBlockers[code as keyof typeof uz.callBlockers] ?? code)
                .join(", ")}
            </div>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => onCall(row.id)}
            className="rounded bg-ink px-2 py-1 font-medium text-white disabled:opacity-40"
          >
            {d.call}
          </button>
        </div>
      )}
      {row.status === "CALLED" && (
        <div className="text-xs">
          <div className="text-slate-500">
            {d.callAttempt} {row.attempts}
          </div>
          <button
            type="button"
            disabled={busy || row.recalls_left === 0}
            onClick={() => onRecall(row.id)}
            className="rounded border border-slate-300 px-2 py-1 font-medium disabled:opacity-40"
          >
            {d.recall}
          </button>
        </div>
      )}
    </div>
  );
}

function AssignCell({
  row,
  busy,
  onAssign,
  onCall,
  onRecall,
}: {
  row: QueueRow;
  busy: boolean;
  onAssign: (id: number, dock: string) => void;
  onCall: (id: number) => void;
  onRecall: (id: number) => void;
}) {
  const [dock, setDock] = useState("");
  if (row.dock) {
    return <CalledCell row={row} busy={busy} onCall={onCall} onRecall={onRecall} />;
  }
  if (row.status !== "AWAITING_DOCK")
    return <span className="text-slate-400">{uz.common.none}</span>;
  if (row.free_docks.length === 0) {
    return <span className="text-xs text-amber-700">{d.noFreeDock}</span>;
  }
  return (
    <div className="flex items-center gap-1">
      <select
        aria-label={`${d.chooseDock} № ${row.queue_number}`}
        value={dock}
        onChange={(e) => setDock(e.target.value)}
        className="rounded border border-slate-300 px-1 py-1 text-sm"
      >
        <option value="">{d.chooseDock}</option>
        {row.free_docks.map((code) => (
          <option key={code} value={code}>
            {code}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={busy || !dock}
        onClick={() => onAssign(row.id, dock)}
        className="rounded bg-ink px-2 py-1 text-xs font-medium text-white disabled:opacity-40"
      >
        {d.assign}
      </button>
    </div>
  );
}

export function QueueTable({
  rows,
  busy,
  onAssign,
  onCall,
  onRecall,
  onPriority,
}: {
  rows: QueueRow[];
  busy: boolean;
  onAssign: (id: number, dock: string) => void;
  onCall: (id: number) => void;
  onRecall: (id: number) => void;
  onPriority: (id: number, priority: number) => void;
}) {
  return (
    <section aria-label={d.queue} className="rounded-lg border border-slate-200 bg-white">
      <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">
        {d.queue} <span className="num ml-2 text-slate-500">{rows.length}</span>
      </h2>
      {rows.length === 0 ? (
        <p className="p-4 text-slate-500">{d.queueEmpty}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">{c.number}</th>
                <th className="px-2 py-2">{c.awb}</th>
                <th className="px-2 py-2">{c.consignee}</th>
                <th className="px-2 py-2">{c.category}</th>
                <th className="px-2 py-2">{c.status}</th>
                <th className="px-2 py-2">{c.wait}</th>
                <th className="px-2 py-2">{c.priority}</th>
                <th className="px-2 py-2">{c.dock}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  data-testid={`row-${row.queue_number}`}
                  className="border-t border-slate-100"
                >
                  <td className="num px-4 py-2 font-semibold">{row.queue_number}</td>
                  <td className="num px-2 py-2">{row.awb_number}</td>
                  <td className="px-2 py-2">{row.consignee_name}</td>
                  <td className="px-2 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        row.special_handling ? "bg-accent text-ink" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {row.category}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <div>{uz.statuses[row.status as StatusCode]}</div>
                    {row.task_status && row.task_status !== "HANDED_OVER" && (
                      <div className="text-xs text-slate-500">
                        {d.taskStatus}:{" "}
                        {
                          uz.warehouse.taskStatus[
                            row.task_status as keyof typeof uz.warehouse.taskStatus
                          ]
                        }
                      </div>
                    )}
                  </td>
                  <td className="num px-2 py-2">
                    {row.wait_minutes} {uz.common.minutes}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        aria-label={`${d.priorityDown} № ${row.queue_number}`}
                        disabled={busy || row.priority <= 0}
                        onClick={() => onPriority(row.id, row.priority - 1)}
                        className="h-6 w-6 rounded border border-slate-300 disabled:opacity-30"
                      >
                        −
                      </button>
                      <span className="num w-5 text-center font-medium">{row.priority}</span>
                      <button
                        type="button"
                        aria-label={`${d.priorityUp} № ${row.queue_number}`}
                        disabled={busy || row.priority >= MAX_PRIORITY}
                        onClick={() => onPriority(row.id, row.priority + 1)}
                        className="h-6 w-6 rounded border border-slate-300 disabled:opacity-30"
                      >
                        +
                      </button>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <AssignCell
                      row={row}
                      busy={busy}
                      onAssign={onAssign}
                      onCall={onCall}
                      onRecall={onRecall}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

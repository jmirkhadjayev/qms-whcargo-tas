import { uz, type StatusCode } from "../../i18n/uz";
import { formatTime } from "../../lib/dates";
import { useReprint, useTodayRequests } from "./api";
import { openTicketWindow } from "./printTicket";

const c = uz.registration.columns;

export function TodayList() {
  const { data, isLoading } = useTodayRequests();
  const reprint = useReprint();
  const rows = data?.results ?? [];

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <h2 className="border-b border-slate-200 px-4 py-3 font-semibold text-ink">
        {uz.registration.today}
        <span className="num ml-2 text-slate-500">{data?.count ?? 0}</span>
      </h2>
      {isLoading ? (
        <p className="p-4 text-slate-500">{uz.app.loading}</p>
      ) : rows.length === 0 ? (
        <p className="p-4 text-slate-500">{uz.registration.todayEmpty}</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{c.number}</th>
              <th className="px-2 py-2">{c.awb}</th>
              <th className="px-2 py-2">{c.consignee}</th>
              <th className="px-2 py-2">{c.status}</th>
              <th className="px-2 py-2">{c.time}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-slate-100">
                <td className="num px-4 py-2 font-medium">{row.queue_number}</td>
                <td className="num px-2 py-2">{row.awb_number}</td>
                <td className="px-2 py-2">{row.consignee_name}</td>
                <td className="px-2 py-2">{uz.statuses[row.status as StatusCode]}</td>
                <td className="num px-2 py-2">{formatTime(row.registered_at)}</td>
                <td className="px-2 py-2 text-right">
                  <button
                    type="button"
                    className="text-xs text-slate-600 underline hover:text-ink"
                    disabled={reprint.isPending}
                    onClick={() =>
                      reprint.mutate(row.id, { onSuccess: () => openTicketWindow(row.id) })
                    }
                  >
                    {uz.registration.reprint}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

import { uz } from "../../i18n/uz";
import { formatDateTime } from "../../lib/dates";
import type { RegistrationResponse } from "./api";
import { openTicketWindow } from "./printTicket";

const t = uz.registration.ticket;

export function TicketModal({
  created,
  onClose,
}: {
  created: RegistrationResponse;
  onClose: () => void;
}) {
  const ticket = created.ticket;
  return (
    <div className="fixed inset-0 z-10 grid place-items-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t.title}
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-ink">✓ {t.title}</h2>
        <div className="my-5 text-center">
          <div className="text-sm text-slate-500">{t.queueNumber}</div>
          <div className="num text-7xl font-semibold text-ink" data-testid="queue-number">
            {ticket.queue_number}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">{t.awb}</dt>
          <dd className="num text-right">{ticket.awb_number}</dd>
          <dt className="text-slate-500">{t.pieces}</dt>
          <dd className="num text-right">{ticket.pieces_total}</dd>
          <dt className="text-slate-500">{t.weight}</dt>
          <dd className="num text-right">{ticket.weight_kg} kg</dd>
          {ticket.vehicle_plate && (
            <>
              <dt className="text-slate-500">{t.plate}</dt>
              <dd className="num text-right">{ticket.vehicle_plate}</dd>
            </>
          )}
          <dt className="text-slate-500">{t.registered}</dt>
          <dd className="num text-right">{formatDateTime(ticket.registered_at)}</dd>
        </dl>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={() => openTicketWindow(created.id)}
            className="flex-1 rounded bg-ink px-4 py-2.5 font-medium text-white hover:bg-ink/90"
          >
            {t.print}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-4 py-2.5 hover:bg-slate-50"
          >
            {t.close}
          </button>
        </div>
      </div>
    </div>
  );
}

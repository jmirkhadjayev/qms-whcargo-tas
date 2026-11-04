import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { QrCode } from "../../components/QrCode";
import { uz } from "../../i18n/uz";
import { formatDateTime } from "../../lib/dates";
import { useTicket } from "../registration/api";

const t = uz.registration.ticket;

// 80 mm thermal printer: continuous roll, no margins (TZ 3.1 ticket requirements).
const PRINT_CSS = `
  @page { size: 80mm auto; margin: 0; }
  @media print { body { background: #fff !important; } .no-print { display: none !important; } }
`;

export function TicketPrintPage() {
  const id = Number(useParams().id);
  const [params] = useSearchParams();
  const auto = params.get("auto") === "1";
  const { data: ticket, isLoading, isError } = useTicket(id);
  const [qrReady, setQrReady] = useState(false);
  const onQrReady = useCallback(() => setQrReady(true), []);

  useEffect(() => {
    if (auto && ticket && qrReady) window.print();
  }, [auto, ticket, qrReady]);

  if (isLoading) return <p className="p-4">{uz.app.loading}</p>;
  if (isError || !ticket) return <p className="p-4 text-red-700">{t.loadError}</p>;

  return (
    <div className="mx-auto bg-white p-3 text-black" style={{ width: "80mm" }}>
      <style>{PRINT_CSS}</style>
      <div className="text-center text-xs font-semibold leading-tight">{ticket.airport}</div>
      <div className="mt-1 text-center text-[10px] uppercase tracking-wide">
        {t.printTitle}
        {ticket.is_reprint ? ` · ${t.reprint}` : ""}
      </div>
      <div className="my-3 text-center">
        <div className="text-[10px]">{t.queueNumber}</div>
        <div className="num text-6xl font-semibold leading-none">{ticket.queue_number}</div>
      </div>
      <table className="w-full text-xs">
        <tbody>
          <Row label={t.awb} value={ticket.awb_number} />
          <Row label={t.pieces} value={String(ticket.pieces_total)} />
          <Row label={t.weight} value={`${ticket.weight_kg} kg`} />
          {ticket.vehicle_plate && <Row label={t.plate} value={ticket.vehicle_plate} />}
          <Row label={t.registered} value={formatDateTime(ticket.registered_at)} />
        </tbody>
      </table>
      <div className="mt-3 flex justify-center">
        <QrCode value={ticket.qr_token} size={170} onReady={onQrReady} />
      </div>
      <div className="mt-1 text-center text-[10px]">{t.scanHint}</div>
      <button
        type="button"
        onClick={() => window.print()}
        className="no-print mt-4 w-full rounded bg-slate-800 py-2 text-sm text-white"
      >
        {t.print}
      </button>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <td className="py-0.5 pr-2 text-gray-600">{label}</td>
      <td className="num py-0.5 text-right font-medium">{value}</td>
    </tr>
  );
}

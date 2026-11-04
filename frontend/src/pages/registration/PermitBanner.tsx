import { uz } from "../../i18n/uz";
import { formatDateTime } from "../../lib/dates";
import type { PermitCheckResult } from "./api";

export function PermitBanner({ result }: { result: PermitCheckResult }) {
  if (result.verified) {
    return (
      <div role="status" className="rounded border border-green-300 bg-green-50 p-4 text-green-900">
        <div className="font-semibold">✓ {uz.registration.permitOk}</div>
        {result.permit && (
          <div className="mt-1 text-sm">
            {uz.registration.permitNumber}:{" "}
            <span className="num">{result.permit.permit_number}</span>
            {result.permit.valid_until && (
              <>
                {" · "}
                {uz.registration.validUntil}:{" "}
                <span className="num">{formatDateTime(result.permit.valid_until)}</span>
              </>
            )}
          </div>
        )}
      </div>
    );
  }
  return (
    <div role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-900">
      <div className="font-semibold">✕ {uz.registration.permitRejected}</div>
      <div className="mt-1 text-sm">{result.reason}</div>
    </div>
  );
}

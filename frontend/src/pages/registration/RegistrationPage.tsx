import { useState, type FormEvent } from "react";

import { uz } from "../../i18n/uz";
import {
  ApiProblem,
  usePermitCheck,
  useRegister,
  type PermitCheckResult,
  type RegistrationResponse,
} from "./api";
import { PermitBanner } from "./PermitBanner";
import { RegistrationForm } from "./RegistrationForm";
import { TicketModal } from "./TicketModal";
import { TodayList } from "./TodayList";
import type { RegistrationValues } from "./validation";

const r = uz.registration;

export function RegistrationPage() {
  const [awb, setAwb] = useState("");
  const [awbError, setAwbError] = useState<string | null>(null);
  const [checked, setChecked] = useState<PermitCheckResult | null>(null);
  const [created, setCreated] = useState<RegistrationResponse | null>(null);
  const [formKey, setFormKey] = useState(0);
  const check = usePermitCheck();
  const register = useRegister();

  function onAwbChange(value: string) {
    setAwb(value);
    setAwbError(null);
    // Any edit invalidates the previous verdict: the permit belongs to one AWB only.
    setChecked(null);
    register.reset();
  }

  function onCheck(event: FormEvent) {
    event.preventDefault();
    if (!awb.trim()) {
      setAwbError(r.awbRequired);
      return;
    }
    check.mutate(awb.trim(), { onSuccess: setChecked });
  }

  function onSubmit(values: RegistrationValues) {
    if (!checked?.verified || !checked.awb_number) return;
    register.mutate(
      {
        awb_number: checked.awb_number,
        consignee_name: values.consigneeName.trim(),
        consignee_tin: values.consigneeTin.trim(),
        representative_name: values.representativeName.trim(),
        sms_phone: values.smsPhone,
        pieces_total: Number(values.piecesTotal),
        weight_kg: values.weightKg.replace(",", ".").trim(),
        vehicle_plate: values.vehiclePlate,
        category: values.category,
        notes: values.notes.trim(),
      },
      {
        onSuccess: (response) => {
          setCreated(response);
          setAwb("");
          setChecked(null);
          setFormKey((key) => key + 1);
        },
      },
    );
  }

  const checkProblem = check.error instanceof ApiProblem ? check.error : null;
  const registerProblem = register.error instanceof ApiProblem ? register.error : null;
  // Field-level messages are shown under the inputs; everything else goes into a banner.
  const registerBanner =
    registerProblem && Object.keys(registerProblem.fields).length === 0 ? registerProblem : null;

  return (
    <div className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-6">
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold text-ink">{r.title}</h1>

        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 font-semibold text-ink">{r.step1}</h2>
          <form onSubmit={onCheck} noValidate className="flex items-start gap-3">
            <div className="flex-1">
              <label htmlFor="awb" className="mb-1 block text-sm font-medium text-slate-700">
                {r.awb}
              </label>
              <input
                id="awb"
                value={awb}
                placeholder={r.awbPlaceholder}
                onChange={(e) => onAwbChange(e.target.value)}
                className="num w-full rounded border border-slate-300 px-3 py-2 text-lg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              {awbError && (
                <p className="mt-1 text-sm text-red-600" role="alert">
                  {awbError}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={check.isPending}
              className="mt-6 rounded bg-ink px-4 py-2.5 font-medium text-white hover:bg-ink/90 disabled:opacity-60"
            >
              {check.isPending ? r.checking : r.check}
            </button>
          </form>
          <div className="mt-4">
            {checked && <PermitBanner result={checked} />}
            {checkProblem && (
              <div
                role="alert"
                className="rounded border border-red-300 bg-red-50 p-4 text-red-900"
              >
                {checkProblem.message}
              </div>
            )}
          </div>
        </section>

        {checked?.verified && (
          <section className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="mb-3 font-semibold text-ink">{r.step2}</h2>
            {registerBanner && (
              <div
                role="alert"
                className="mb-4 rounded border border-red-300 bg-red-50 p-4 text-red-900"
              >
                {registerBanner.message}
              </div>
            )}
            <RegistrationForm
              key={formKey}
              submitting={register.isPending}
              serverProblem={registerProblem}
              onSubmit={onSubmit}
            />
          </section>
        )}
      </div>

      <TodayList />

      {created && <TicketModal created={created} onClose={() => setCreated(null)} />}
    </div>
  );
}

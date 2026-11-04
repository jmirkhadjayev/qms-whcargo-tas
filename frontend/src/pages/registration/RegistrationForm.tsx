import { useState, type FormEvent, type ReactNode } from "react";

import { uz } from "../../i18n/uz";
import { useLookups, type ApiProblem } from "./api";
import {
  emptyValues,
  validateRegistration,
  type RegistrationErrors,
  type RegistrationValues,
} from "./validation";

const f = uz.registration.form;

// Server field names -> form field names, so server messages land under the right input.
const SERVER_FIELDS: Record<string, keyof RegistrationValues> = {
  consignee_name: "consigneeName",
  consignee_tin: "consigneeTin",
  representative_name: "representativeName",
  sms_phone: "smsPhone",
  pieces_total: "piecesTotal",
  weight_kg: "weightKg",
  vehicle_plate: "vehiclePlate",
  category: "category",
  notes: "notes",
};

function Field({
  label,
  htmlFor,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error && (
        <p className="mt-1 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const inputClass =
  "w-full rounded border border-slate-300 bg-white px-3 py-2 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/40";

export function RegistrationForm({
  submitting,
  serverProblem,
  onSubmit,
}: {
  submitting: boolean;
  serverProblem: ApiProblem | null;
  onSubmit: (values: RegistrationValues) => void;
}) {
  const lookups = useLookups();
  const [values, setValues] = useState<RegistrationValues>(emptyValues);
  const [errors, setErrors] = useState<RegistrationErrors>({});

  const serverErrors: RegistrationErrors = {};
  if (serverProblem) {
    for (const [field, messages] of Object.entries(serverProblem.fields)) {
      const key = SERVER_FIELDS[field];
      if (key) serverErrors[key] = messages[0];
    }
  }
  const shown = { ...serverErrors, ...errors };

  function set<K extends keyof RegistrationValues>(key: K, value: RegistrationValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const found = validateRegistration(values);
    setErrors(found);
    if (Object.keys(found).length === 0) onSubmit(values);
  }

  return (
    <form onSubmit={submit} noValidate className="grid grid-cols-2 gap-4">
      <div className="col-span-2">
        <Field label={f.consigneeName} htmlFor="consigneeName" error={shown.consigneeName}>
          <input
            id="consigneeName"
            className={inputClass}
            value={values.consigneeName}
            onChange={(e) => set("consigneeName", e.target.value)}
          />
        </Field>
      </div>
      <Field label={f.tin} htmlFor="consigneeTin" error={shown.consigneeTin}>
        <input
          id="consigneeTin"
          className={`${inputClass} num`}
          value={values.consigneeTin}
          onChange={(e) => set("consigneeTin", e.target.value)}
        />
      </Field>
      <Field label={f.representative} htmlFor="representativeName" error={shown.representativeName}>
        <input
          id="representativeName"
          className={inputClass}
          value={values.representativeName}
          onChange={(e) => set("representativeName", e.target.value)}
        />
      </Field>
      <Field label={f.phone} htmlFor="smsPhone" error={shown.smsPhone}>
        <input
          id="smsPhone"
          inputMode="tel"
          placeholder={f.phoneHint}
          className={`${inputClass} num`}
          value={values.smsPhone}
          onChange={(e) => set("smsPhone", e.target.value)}
        />
      </Field>
      <Field label={f.plate} htmlFor="vehiclePlate" error={shown.vehiclePlate}>
        <input
          id="vehiclePlate"
          placeholder={f.plateHint}
          className={`${inputClass} num uppercase`}
          value={values.vehiclePlate}
          onChange={(e) => set("vehiclePlate", e.target.value)}
        />
      </Field>
      <Field label={f.pieces} htmlFor="piecesTotal" error={shown.piecesTotal}>
        <input
          id="piecesTotal"
          inputMode="numeric"
          className={`${inputClass} num`}
          value={values.piecesTotal}
          onChange={(e) => set("piecesTotal", e.target.value)}
        />
      </Field>
      <Field label={f.weight} htmlFor="weightKg" error={shown.weightKg}>
        <input
          id="weightKg"
          inputMode="decimal"
          className={`${inputClass} num`}
          value={values.weightKg}
          onChange={(e) => set("weightKg", e.target.value)}
        />
      </Field>
      <div className="col-span-2">
        <Field label={f.category} htmlFor="category" error={shown.category}>
          <select
            id="category"
            className={inputClass}
            value={values.category}
            onChange={(e) => set("category", e.target.value)}
          >
            <option value="">{f.categoryPlaceholder}</option>
            {lookups.data?.categories.map((category) => (
              <option key={category.id} value={category.code}>
                {category.code} — {category.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="col-span-2">
        <Field label={f.notes} htmlFor="notes" error={shown.notes}>
          <textarea
            id="notes"
            rows={2}
            className={inputClass}
            value={values.notes}
            onChange={(e) => set("notes", e.target.value)}
          />
        </Field>
      </div>
      <div className="col-span-2">
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-accent px-4 py-3 text-lg font-semibold text-ink hover:brightness-95 disabled:opacity-60"
        >
          {submitting ? f.submitting : f.submit}
        </button>
      </div>
    </form>
  );
}

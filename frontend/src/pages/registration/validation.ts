import { uz } from "../../i18n/uz";

export interface RegistrationValues {
  consigneeName: string;
  consigneeTin: string;
  representativeName: string;
  smsPhone: string;
  piecesTotal: string;
  weightKg: string;
  vehiclePlate: string;
  category: string;
  notes: string;
}

export type RegistrationErrors = Partial<Record<keyof RegistrationValues, string>>;

export const emptyValues: RegistrationValues = {
  consigneeName: "",
  consigneeTin: "",
  representativeName: "",
  smsPhone: "+998",
  piecesTotal: "",
  weightKg: "",
  vehiclePlate: "",
  category: "",
  notes: "",
};

const v = uz.registration.validation;

/** Same rules as the server (cargo_queue/serializers.py); the server stays the authority. */
export function validateRegistration(values: RegistrationValues): RegistrationErrors {
  const errors: RegistrationErrors = {};
  if (!values.consigneeName.trim()) errors.consigneeName = v.required;
  if (!/^\+998\d{9}$/.test(values.smsPhone.replace(/[\s\-()]/g, ""))) errors.smsPhone = v.phone;
  if (!/^\d+$/.test(values.piecesTotal) || Number(values.piecesTotal) < 1) {
    errors.piecesTotal = v.pieces;
  }
  const weight = Number(values.weightKg.replace(",", "."));
  if (!values.weightKg.trim() || !Number.isFinite(weight) || weight <= 0) {
    errors.weightKg = v.weight;
  }
  if (!values.category) errors.category = v.required;
  const plate = values.vehiclePlate.replace(/[\s-]/g, "").toUpperCase();
  if (plate && !/^[A-Z0-9]{5,10}$/.test(plate)) errors.vehiclePlate = v.plate;
  return errors;
}

import { uz } from "../../i18n/uz";
import { emptyValues, validateRegistration, type RegistrationValues } from "./validation";

const valid: RegistrationValues = {
  ...emptyValues,
  consigneeName: "Toshkent Savdo MChJ",
  smsPhone: "+998 90 123-45-67",
  piecesTotal: "12",
  weightKg: "345,5",
  category: "GEN",
  vehiclePlate: "01 A 123 BC",
};

describe("validateRegistration", () => {
  it("accepts a complete form (spaces, dashes and a decimal comma are fine)", () => {
    expect(validateRegistration(valid)).toEqual({});
  });

  it("does not require the optional fields", () => {
    expect(validateRegistration({ ...valid, vehiclePlate: "", consigneeTin: "" })).toEqual({});
  });

  it("reports every missing required field in Uzbek", () => {
    const errors = validateRegistration(emptyValues);
    expect(Object.keys(errors).sort()).toEqual(
      ["category", "consigneeName", "piecesTotal", "smsPhone", "weightKg"].sort(),
    );
    expect(errors.consigneeName).toBe(uz.registration.validation.required);
  });

  it.each(["123", "+99890123456", "998901234567", "+998abcdefghi"])("rejects phone %s", (phone) => {
    expect(validateRegistration({ ...valid, smsPhone: phone }).smsPhone).toBe(
      uz.registration.validation.phone,
    );
  });

  it.each(["0", "-3", "1.5", "abc", ""])("rejects pieces %j", (pieces) => {
    expect(validateRegistration({ ...valid, piecesTotal: pieces }).piecesTotal).toBe(
      uz.registration.validation.pieces,
    );
  });

  it.each(["0", "-1", "abc", ""])("rejects weight %j", (weight) => {
    expect(validateRegistration({ ...valid, weightKg: weight }).weightKg).toBe(
      uz.registration.validation.weight,
    );
  });

  it("rejects a malformed plate", () => {
    expect(validateRegistration({ ...valid, vehiclePlate: "!!" }).vehiclePlate).toBe(
      uz.registration.validation.plate,
    );
  });
});

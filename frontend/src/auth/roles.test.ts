import { ROLE_SECTIONS, canOpen, homePathFor, type RoleCode } from "./roles";

const ROLES: RoleCode[] = [
  "REG_AGENT",
  "WAREHOUSE",
  "DOCK_AGENT",
  "SUPERVISOR",
  "CHECKPOINT",
  "MANAGER",
  "ADMIN",
];

describe("role routing", () => {
  it.each([
    ["REG_AGENT", "/registration"],
    ["WAREHOUSE", "/warehouse"],
    ["DOCK_AGENT", "/dock"],
    ["SUPERVISOR", "/dispatcher"],
    ["CHECKPOINT", "/checkpoint"],
    ["MANAGER", "/reports"],
    ["ADMIN", "/admin"],
  ] as const)("%s lands on %s", (role, path) => {
    expect(homePathFor(role)).toBe(path);
  });

  it("every role has its home section allowed", () => {
    for (const role of ROLES) {
      expect(canOpen(role, ROLE_SECTIONS[role][0])).toBe(true);
    }
  });

  it("registration is only for REG_AGENT; admin section only for ADMIN", () => {
    for (const role of ROLES) {
      expect(canOpen(role, "registration")).toBe(role === "REG_AGENT");
      expect(canOpen(role, "admin")).toBe(role === "ADMIN");
    }
  });
});

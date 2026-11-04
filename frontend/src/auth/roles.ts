export type RoleCode =
  "REG_AGENT" | "WAREHOUSE" | "DOCK_AGENT" | "SUPERVISOR" | "CHECKPOINT" | "MANAGER" | "ADMIN";

export type SectionKey =
  "registration" | "dispatcher" | "dock" | "warehouse" | "checkpoint" | "reports" | "admin";

export const SECTION_PATH: Record<SectionKey, string> = {
  registration: "/registration",
  dispatcher: "/dispatcher",
  dock: "/dock",
  warehouse: "/warehouse",
  checkpoint: "/checkpoint",
  reports: "/reports",
  admin: "/admin",
};

// Sections each role may open; the first one is the role's home page.
export const ROLE_SECTIONS: Record<RoleCode, SectionKey[]> = {
  REG_AGENT: ["registration"],
  WAREHOUSE: ["warehouse"],
  DOCK_AGENT: ["dock"],
  SUPERVISOR: ["dispatcher", "reports"],
  CHECKPOINT: ["checkpoint"],
  MANAGER: ["reports"],
  ADMIN: ["admin", "reports"],
};

export function homePathFor(role: RoleCode): string {
  return SECTION_PATH[ROLE_SECTIONS[role][0]];
}

export function canOpen(role: RoleCode, section: SectionKey): boolean {
  return ROLE_SECTIONS[role].includes(section);
}

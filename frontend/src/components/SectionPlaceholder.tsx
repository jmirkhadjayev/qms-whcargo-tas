import { uz } from "../i18n/uz";

import type { SectionKey } from "../auth/roles";

/** Empty section page; replaced by the real screen in later stages. */
export function SectionPlaceholder({ section }: { section: SectionKey }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-8">
      <h1 className="text-2xl font-semibold text-ink">{uz.sections[section]}</h1>
      <p className="mt-2 text-slate-500">{uz.placeholder.comingSoon}</p>
    </div>
  );
}

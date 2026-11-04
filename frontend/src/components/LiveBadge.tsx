import { uz } from "../i18n/uz";
import type { LiveStatus } from "../lib/live";

const DOT: Record<LiveStatus, string> = {
  open: "bg-green-500",
  connecting: "bg-amber-400",
  closed: "bg-red-500",
};

export function LiveBadge({ status }: { status: LiveStatus }) {
  return (
    <span
      className="inline-flex items-center gap-2 text-xs text-slate-500"
      title={status === "closed" ? uz.live.closed : undefined}
    >
      <span className={`h-2 w-2 rounded-full ${DOT[status]}`} />
      {status === "open"
        ? uz.live.open
        : status === "connecting"
          ? uz.live.connecting
          : uz.live.closed}
    </span>
  );
}

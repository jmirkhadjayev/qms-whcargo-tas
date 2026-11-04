import { useQuery } from "@tanstack/react-query";

import { ApiProblem } from "../api/call";
import { uz } from "../i18n/uz";
import { useLiveRefresh, type LiveStatus } from "../lib/live";

/** The screen's own secret (?token=...), needed outside the allowed networks. */
export function screenToken(search: string = window.location.search): string | null {
  return new URLSearchParams(search).get("token");
}

export class ScreenForbidden extends Error {}

type Fetcher<T> = (token: string | undefined) => Promise<{
  data?: T;
  response: Response;
}>;

/**
 * Data for a public screen: fetched when the server says something changed (WebSocket), and
 * every 10 seconds as a fallback. No login: the request carries only the screen token.
 */
export function useScreenData<T>(
  key: string[],
  socketPath: string,
  fetcher: Fetcher<T>,
): { data: T | undefined; forbidden: boolean; offline: boolean; live: LiveStatus } {
  const token = screenToken();
  const query = useQuery({
    queryKey: ["display", ...key],
    queryFn: async () => {
      const { data, response } = await fetcher(token ?? undefined);
      if (response.status === 403) throw new ScreenForbidden(uz.display.forbidden);
      if (!response.ok || data === undefined) throw new ApiProblem(uz.app.networkError);
      return data;
    },
    refetchInterval: 10_000,
    retry: false,
  });
  const live = useLiveRefresh(
    token ? `${socketPath}?token=${encodeURIComponent(token)}` : socketPath,
    [["display", ...key]],
  );
  return {
    data: query.data,
    forbidden: query.error instanceof ScreenForbidden,
    offline: query.isError && !(query.error instanceof ScreenForbidden),
    live,
  };
}

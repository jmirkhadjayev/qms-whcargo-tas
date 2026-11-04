import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ensureCsrf } from "../api/client";
import type { RoleCode } from "./roles";

export interface CurrentUser {
  id: number;
  username: string;
  full_name: string;
  role: RoleCode;
}

export const ME_KEY = ["me"] as const;

/** Current user, or null when not logged in. */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<CurrentUser | null> => {
      const { data, response } = await api.GET("/api/auth/me/");
      if (response.status === 401 || response.status === 403) return null;
      return (data as CurrentUser | undefined) ?? null;
    },
    staleTime: 60_000,
    retry: false,
  });
}

export class LoginError extends Error {
  constructor(
    message: string,
    readonly kind: "credentials" | "network",
  ) {
    super(message);
  }
}

export function useLogin(messages: { failed: string; network: string }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { username: string; password: string }): Promise<CurrentUser> => {
      try {
        await ensureCsrf();
        const { data, response, error } = await api.POST("/api/auth/login/", { body: input });
        if (!response.ok || !data) {
          const detail = (error as { detail?: string } | undefined)?.detail;
          throw new LoginError(detail ?? messages.failed, "credentials");
        }
        return data as CurrentUser;
      } catch (e) {
        if (e instanceof LoginError) throw e;
        throw new LoginError(messages.network, "network");
      }
    },
    onSuccess: (user) => queryClient.setQueryData(ME_KEY, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout/");
    },
    onSuccess: () => queryClient.setQueryData(ME_KEY, null),
  });
}

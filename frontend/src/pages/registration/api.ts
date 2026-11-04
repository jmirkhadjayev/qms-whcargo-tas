import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { ApiProblem, call } from "../../api/call";
import type { components } from "../../api/schema";
import { todayInTashkent } from "../../lib/dates";

export { ApiProblem };
export type PermitCheckResult = components["schemas"]["PermitCheckResult"];
export type RegistrationResponse = components["schemas"]["RegistrationResponse"];
export type TicketData = components["schemas"]["TicketData"];
export type Lookups = components["schemas"]["Lookups"];
export type QueueRequestRow = components["schemas"]["QueueRequest"];

export function usePermitCheck() {
  return useMutation({
    mutationFn: (awb_number: string) =>
      call<PermitCheckResult>(api.POST("/api/permits/check/", { body: { awb_number } })),
  });
}

export function useLookups() {
  return useQuery({
    queryKey: ["lookups"],
    queryFn: () => call<Lookups>(api.GET("/api/lookups/")),
    staleTime: 5 * 60_000,
  });
}

export const TODAY_KEY = ["requests", "today"] as const;

export function useTodayRequests() {
  return useQuery({
    queryKey: [...TODAY_KEY, todayInTashkent()],
    queryFn: () =>
      call(
        api.GET("/api/requests/", {
          params: { query: { date: todayInTashkent(), page_size: 100 } },
        }),
      ),
    refetchInterval: 15_000,
  });
}

export type RegisterBody = components["schemas"]["RegisterRequestRequest"];

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RegisterBody) =>
      call<RegistrationResponse>(api.POST("/api/requests/", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TODAY_KEY }),
  });
}

export function useReprint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      call<TicketData>(
        api.POST("/api/requests/{id}/ticket/reprint/", { params: { path: { id } } }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TODAY_KEY }),
  });
}

export function useTicket(id: number) {
  return useQuery({
    queryKey: ["ticket", id],
    queryFn: () =>
      call<TicketData>(api.GET("/api/requests/{id}/ticket/", { params: { path: { id } } })),
  });
}

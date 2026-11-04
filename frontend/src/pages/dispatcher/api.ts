import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { call } from "../../api/call";
import type { components } from "../../api/schema";

export type Overview = components["schemas"]["Overview"];
export type DockCard = components["schemas"]["DockCard"];
export type QueueRow = components["schemas"]["QueueRow"];
export type ExceptionRow = components["schemas"]["Exception"];

export const DISPATCHER_KEY = ["dispatcher"] as const;

export function useOverview() {
  return useQuery({
    queryKey: [...DISPATCHER_KEY, "overview"],
    queryFn: () => call<Overview>(api.GET("/api/dispatcher/overview/")),
    refetchInterval: 15_000,
  });
}

export function useQueue() {
  return useQuery({
    queryKey: [...DISPATCHER_KEY, "queue"],
    queryFn: () => call<QueueRow[]>(api.GET("/api/dispatcher/queue/")),
    refetchInterval: 15_000,
  });
}

function useControl<TInput>(run: (input: TInput) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DISPATCHER_KEY }),
  });
}

export function useAssignDock() {
  return useControl(({ id, dock }: { id: number; dock: string }) =>
    call(api.POST("/api/requests/{id}/assign-dock/", { params: { path: { id } }, body: { dock } })),
  );
}

export function useCallRequest() {
  return useControl((id: number) =>
    call(api.POST("/api/requests/{id}/call/", { params: { path: { id } } })),
  );
}

export function useRecallRequest() {
  return useControl((id: number) =>
    call(api.POST("/api/requests/{id}/recall/", { params: { path: { id } } })),
  );
}

export function useSetPriority() {
  return useControl(({ id, priority }: { id: number; priority: number }) =>
    call(
      api.POST("/api/requests/{id}/priority/", { params: { path: { id } }, body: { priority } }),
    ),
  );
}

export function useSetMaintenance() {
  return useControl(({ code, maintenance }: { code: string; maintenance: boolean }) =>
    call(
      api.POST("/api/dispatcher/docks/{code}/maintenance/", {
        params: { path: { code } },
        body: { maintenance },
      }),
    ),
  );
}

export function useExceptions() {
  return useQuery({
    queryKey: [...DISPATCHER_KEY, "exceptions"],
    queryFn: () => call<ExceptionRow[]>(api.GET("/api/exceptions/")),
    refetchInterval: 15_000,
  });
}

export function useResolveException() {
  return useControl(({ id, resolution }: { id: number; resolution: string }) =>
    call(
      api.POST("/api/exceptions/{id}/resolve/", {
        params: { path: { id } },
        body: { resolution },
      }),
    ),
  );
}

export function useResumeRequest() {
  return useControl(({ id, reason }: { id: number; reason: string }) =>
    call(api.POST("/api/requests/{id}/resume/", { params: { path: { id } }, body: { reason } })),
  );
}

/** The supervisor's decision about a vehicle that left with part of its cargo (K14). */
export function useDecideRemainder() {
  return useControl(
    ({ id, to, reason }: { id: number; to: "AWAITING_PREP" | "CLOSED"; reason?: string }) =>
      call(
        api.POST("/api/requests/{id}/transition/", {
          params: { path: { id } },
          body: { to_status: to, reason },
        }),
      ),
  );
}

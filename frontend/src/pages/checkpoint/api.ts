import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { call } from "../../api/call";
import type { components } from "../../api/schema";

export type CheckSummary = components["schemas"]["CheckSummary"];
export type CheckpointOverview = components["schemas"]["CheckpointOverview"];

export const CHECKPOINT_KEY = ["checkpoint"] as const;

export function useOverview() {
  return useQuery({
    queryKey: [...CHECKPOINT_KEY, "overview"],
    queryFn: () => call<CheckpointOverview>(api.GET("/api/checkpoint/overview/")),
    refetchInterval: 15_000,
  });
}

export function useScan() {
  return useMutation({
    mutationFn: (code: string) =>
      call<CheckSummary>(api.GET("/api/checkpoint/scan/", { params: { query: { code } } })),
  });
}

export function useConfirm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, plate }: { id: number; plate: string }) =>
      call<CheckSummary>(
        api.POST("/api/checkpoint/{id}/confirm/", {
          params: { path: { id } },
          body: { plate_observed: plate },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CHECKPOINT_KEY }),
  });
}

export function useHold() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, description, plate }: { id: number; description: string; plate: string }) =>
      call<CheckSummary>(
        api.POST("/api/checkpoint/{id}/hold/", {
          params: { path: { id } },
          body: { description, plate_observed: plate },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CHECKPOINT_KEY }),
  });
}

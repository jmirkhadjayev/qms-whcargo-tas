import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { call } from "../../api/call";
import type { components } from "../../api/schema";

export type WarehouseTask = components["schemas"]["WarehouseTask"];
export type ProblemKind = "MISSING" | "DAMAGE" | "SHORTAGE" | "MISMATCH";

export const WAREHOUSE_KEY = ["warehouse"] as const;

export function useTasks() {
  return useQuery({
    queryKey: [...WAREHOUSE_KEY, "tasks"],
    queryFn: () => call<WarehouseTask[]>(api.GET("/api/warehouse/tasks/")),
    refetchInterval: 15_000,
  });
}

export function useScan() {
  return useMutation({
    mutationFn: (code: string) =>
      call<WarehouseTask>(api.GET("/api/warehouse/tasks/scan/", { params: { query: { code } } })),
  });
}

function useAction<TInput>(run: (input: TInput) => Promise<WarehouseTask>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: WAREHOUSE_KEY }),
  });
}

export function useStartTask() {
  return useAction(({ id, storageLocation }: { id: number; storageLocation: string }) =>
    call<WarehouseTask>(
      api.POST("/api/warehouse/tasks/{id}/start/", {
        params: { path: { id } },
        body: { storage_location: storageLocation },
      }),
    ),
  );
}

export function useReadyTask() {
  return useAction((id: number) =>
    call<WarehouseTask>(api.POST("/api/warehouse/tasks/{id}/ready/", { params: { path: { id } } })),
  );
}

export function useHandOverTask() {
  return useAction((id: number) =>
    call<WarehouseTask>(
      api.POST("/api/warehouse/tasks/{id}/handover/", { params: { path: { id } } }),
    ),
  );
}

export function useReportProblem() {
  return useAction(
    ({
      id,
      kind,
      description,
      piecesAffected,
    }: {
      id: number;
      kind: ProblemKind;
      description: string;
      piecesAffected: number;
    }) =>
      call<WarehouseTask>(
        api.POST("/api/warehouse/tasks/{id}/problem/", {
          params: { path: { id } },
          body: { kind, description, pieces_affected: piecesAffected },
        }),
      ),
  );
}

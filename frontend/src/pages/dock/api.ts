import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { call } from "../../api/call";
import type { components } from "../../api/schema";

export type AgentScreen = components["schemas"]["AgentScreen"];
export type AgentCurrent = components["schemas"]["AgentCurrent"];
export type PartialReason = "MISSING" | "DAMAGE" | "SHORTAGE" | "CUSTOMER" | "OTHER";
export type ProblemKind = "MISSING" | "DAMAGE" | "SHORTAGE" | "MISMATCH";

export const DOCK_KEY = ["dock-agent"] as const;

export function useAgentScreen() {
  return useQuery({
    queryKey: [...DOCK_KEY, "me"],
    queryFn: () => call<AgentScreen>(api.GET("/api/dock/me/")),
    refetchInterval: 10_000,
  });
}

function useAgentAction<TInput, TResult>(run: (input: TInput) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DOCK_KEY }),
  });
}

export function useCheckIn() {
  return useAgentAction((dock: string) =>
    call<AgentScreen>(api.POST("/api/dock/checkin/", { body: { dock } })),
  );
}

export function useCheckOut() {
  return useAgentAction(() => call<AgentScreen>(api.POST("/api/dock/checkout/")));
}

export function useArrive() {
  return useAgentAction((id: number) =>
    call(api.POST("/api/requests/{id}/arrive/", { params: { path: { id } } })),
  );
}

export function useRecall() {
  return useAgentAction((id: number) =>
    call(api.POST("/api/requests/{id}/recall/", { params: { path: { id } } })),
  );
}

export function useScanTicket() {
  return useMutation({
    mutationFn: (code: string) =>
      call<components["schemas"]["ScanResult"]>(
        api.GET("/api/dock/scan/", { params: { query: { code } } }),
      ),
  });
}

// --- release (TZ 5.2) -----------------------------------------------------------------------

export function useStartRelease() {
  return useAgentAction((id: number) =>
    call(api.POST("/api/requests/{id}/release/start/", { params: { path: { id } } })),
  );
}

export function useSetProgress() {
  return useAgentAction(({ id, pieces }: { id: number; pieces: number }) =>
    call(
      api.POST("/api/requests/{id}/release/progress/", {
        params: { path: { id } },
        body: { pieces_released: pieces },
      }),
    ),
  );
}

export function useFinishRelease() {
  return useAgentAction((id: number) =>
    call(api.POST("/api/requests/{id}/release/finish/", { params: { path: { id } }, body: {} })),
  );
}

export function usePartialRelease() {
  return useAgentAction(
    ({ id, reason, comment }: { id: number; reason: PartialReason; comment: string }) =>
      call(
        api.POST("/api/requests/{id}/release/partial/", {
          params: { path: { id } },
          body: { reason, comment },
        }),
      ),
  );
}

export function useDockProblem() {
  return useAgentAction(
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
      call(
        api.POST("/api/requests/{id}/problems/", {
          params: { path: { id } },
          body: { kind, description, pieces_affected: piecesAffected },
        }),
      ),
  );
}

import {
  getAllTriggers,
  getTrigger,
  getTriggerEvents,
  getTriggerStats,
  getTriggerHealth,
  createTrigger,
  updateTrigger,
  deleteTrigger,
} from "@/lib/api/trigger";
import type {
  Trigger,
  TriggerEvent,
  TriggerStats,
  TriggerHealthCheck,
  CreateTriggerRequest,
  UpdateTriggerRequest,
} from "@/lib/types/trigger";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMetaInfo } from "@/components/context/metainfo";

/**
 * Hook to fetch all triggers for the current project
 */
export function useTriggers() {
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useQuery<Trigger[]>({
    queryKey: ["triggers", activeProject?.id],
    queryFn: async () => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return getAllTriggers(apiKey);
    },
    enabled: !!activeProject && !!apiKey,
  });
}

/**
 * Hook to create a new trigger
 */
export function useCreateTrigger() {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useMutation({
    mutationFn: async (request: CreateTriggerRequest) => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return createTrigger(request, apiKey);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["triggers"] });
    },
  });
}

/**
 * Hook to update an existing trigger
 */
export function useUpdateTrigger() {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useMutation({
    mutationFn: async ({
      triggerId,
      request,
    }: {
      triggerId: string;
      request: UpdateTriggerRequest;
    }) => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return updateTrigger(triggerId, request, apiKey);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["triggers"] });
    },
  });
}

/**
 * Hook to delete a trigger
 */
export function useDeleteTrigger() {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useMutation({
    mutationFn: async (triggerId: string) => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return deleteTrigger(triggerId, apiKey);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["triggers"] });
    },
  });
}

/**
 * Hook to fetch a single trigger by ID
 */
export function useTrigger(triggerId: string) {
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useQuery<Trigger>({
    queryKey: ["trigger", triggerId],
    queryFn: async () => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return getTrigger(triggerId, apiKey);
    },
    enabled: !!activeProject && !!apiKey && !!triggerId,
  });
}

/**
 * Hook to fetch events for a specific trigger
 */
export function useTriggerEvents(triggerId: string, status?: string) {
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useQuery<TriggerEvent[]>({
    queryKey: ["trigger-events", triggerId, status],
    queryFn: async () => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return getTriggerEvents(triggerId, apiKey, { status });
    },
    enabled: !!activeProject && !!apiKey && !!triggerId,
  });
}

/**
 * Hook to fetch statistics for a trigger
 */
export function useTriggerStats(triggerId: string) {
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useQuery<TriggerStats>({
    queryKey: ["trigger-stats", triggerId],
    queryFn: async () => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return getTriggerStats(triggerId, apiKey);
    },
    enabled: !!activeProject && !!apiKey && !!triggerId,
  });
}

/**
 * Hook to fetch health check for a trigger
 */
export function useTriggerHealth(triggerId: string) {
  const { activeProject } = useMetaInfo();
  const apiKey = activeProject?.agents?.[0]?.api_keys?.[0]?.key;

  return useQuery<TriggerHealthCheck>({
    queryKey: ["trigger-health", triggerId],
    queryFn: async () => {
      if (!apiKey) {
        throw new Error("No API key available");
      }
      return getTriggerHealth(triggerId, apiKey);
    },
    enabled: !!activeProject && !!apiKey && !!triggerId,
  });
}

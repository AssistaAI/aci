"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getAllAppConfigs,
  AppConfigsParams,
  createAppConfig,
  updateAppConfig,
  deleteAppConfig,
  getAppConfig,
} from "@/lib/api/appconfig";
import { useMetaInfo } from "@/components/context/metainfo";
import { getApiKey } from "@/lib/api/util";
import { AppConfig } from "@/lib/types/appconfig";
import { toast } from "sonner";
import { linkedAccountKeys } from "./use-linked-account";

const appConfigKeys = {
  all: (projectId: string) => [projectId, "appconfigs"] as const,
  paginated: (projectId: string, params: AppConfigsParams) =>
    [projectId, "appconfigs", params] as const,
  detail: (projectId: string, appName: string | null | undefined) =>
    [projectId, "appconfigs", appName ?? ""] as const,
};

export const useAppConfigs = (params?: AppConfigsParams) => {
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useQuery<AppConfig[], Error>({
    queryKey: params
      ? appConfigKeys.paginated(activeProject.id, params)
      : appConfigKeys.all(activeProject.id),
    queryFn: () => getAllAppConfigs(apiKey, params),
  });
};

export const useAppConfig = (appName?: string | null) => {
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useQuery<AppConfig | null, Error>({
    queryKey: appConfigKeys.detail(activeProject.id, appName),
    queryFn: () =>
      appName ? getAppConfig(appName, apiKey) : Promise.resolve(null),
    enabled: !!appName,
  });
};

type CreateAppConfigParams = {
  app_name: string;
  security_scheme: string;
  security_scheme_overrides?: {
    oauth2?: {
      client_id: string;
      client_secret: string;
      redirect_url?: string;
    } | null;
  };
};

export const useCreateAppConfig = () => {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useMutation<AppConfig, Error, CreateAppConfigParams>({
    mutationFn: (params) =>
      createAppConfig(
        params.app_name,
        params.security_scheme,
        apiKey,
        params.security_scheme_overrides,
      ),
    onSuccess: (newConfig) => {
      queryClient.setQueryData<AppConfig[]>(
        appConfigKeys.all(activeProject.id),
        (old = []) => [...old, newConfig],
      );
      queryClient.invalidateQueries({
        queryKey: appConfigKeys.all(activeProject.id),
      });
    },
    onError: (error) => {
      console.error("Create AppConfig failed:", error);
      toast.error("Failed to create app configuration");
    },
  });
};

type UpdateAppConfigParams = {
  app_name: string;
  enabled: boolean;
};

export const useUpdateAppConfig = () => {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useMutation<AppConfig, Error, UpdateAppConfigParams>({
    mutationFn: (params) =>
      updateAppConfig(params.app_name, params.enabled, apiKey),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: appConfigKeys.all(activeProject.id),
      });
      // The current page may only use the update of a single data item when updating
      queryClient.invalidateQueries({
        queryKey: appConfigKeys.detail(activeProject.id, variables.app_name),
      });
    },
    onError: (error) => {
      console.error("Update AppConfig failed:", error);
      toast.error("Failed to update app configuration");
    },
  });
};

export const useDeleteAppConfig = () => {
  const queryClient = useQueryClient();
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useMutation<Response, Error, string>({
    mutationFn: (app_name) => deleteAppConfig(app_name, apiKey),
    onSuccess: (_, app_name) => {
      queryClient.invalidateQueries({
        queryKey: appConfigKeys.all(activeProject.id),
      });
      queryClient.invalidateQueries({
        queryKey: appConfigKeys.detail(activeProject.id, app_name),
      });
      queryClient.invalidateQueries({
        queryKey: linkedAccountKeys.all(activeProject.id),
      });
    },
    onError: (error) => {
      console.error("Delete AppConfig failed:", error);
      toast.error("Failed to delete app configuration");
    },
  });
};

import { useMetaInfo } from "@/components/context/metainfo";
import { getAllApps, AppsParams } from "@/lib/api/app";
import { getApiKey } from "@/lib/api/util";
import { useQuery } from "@tanstack/react-query";

export const appKeys = {
  all: ["apps"] as const,
  paginated: (params: AppsParams) => ["apps", params] as const,
};

export function useApps(params?: AppsParams) {
  const { activeProject } = useMetaInfo();
  const apiKey = getApiKey(activeProject);

  return useQuery({
    queryKey: params ? appKeys.paginated(params) : appKeys.all,
    queryFn: () => getAllApps(apiKey, params),
  });
}

export function useApp(appName: string) {
  const query = useApps({ app_names: [appName] });
  return {
    app: query.data?.[0],
    ...query,
  };
}

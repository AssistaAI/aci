import { App } from "@/lib/types/app";

export interface AppsParams {
  limit?: number;
  offset?: number;
  app_names?: string[];
}

export async function getAllApps(
  apiKey: string,
  params?: AppsParams,
): Promise<App[]> {
  const searchParams = new URLSearchParams();

  if (params?.limit !== undefined) {
    searchParams.append("limit", params.limit.toString());
  }
  if (params?.offset !== undefined) {
    searchParams.append("offset", params.offset.toString());
  }
  if (params?.app_names) {
    params.app_names.forEach((name) => {
      searchParams.append("app_names", name);
    });
  }

  const url = searchParams.toString()
    ? `${process.env.NEXT_PUBLIC_API_URL}/v1/apps?${searchParams.toString()}`
    : `${process.env.NEXT_PUBLIC_API_URL}/v1/apps`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-API-KEY": apiKey,
    },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch app: ${response.status} ${response.statusText}`,
    );
  }

  const apps = await response.json();
  return apps;
}

export async function getApps(
  appNames: string[],
  apiKey: string,
  params?: AppsParams,
): Promise<App[]> {
  return getAllApps(apiKey, {
    ...params,
    app_names: appNames,
  });
}

export async function getApp(
  appName: string,
  apiKey: string,
): Promise<App | null> {
  const apps = await getApps([appName], apiKey);
  return apps.length > 0 ? apps[0] : null;
}

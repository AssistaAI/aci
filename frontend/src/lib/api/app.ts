import { App } from "@/lib/types/app";

export async function getAllApps(apiKey: string): Promise<App[]> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/apps?limit=1000`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

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
): Promise<App[]> {
  const params = new URLSearchParams();
  appNames.forEach((name) => {
    params.append("app_names", name);
  });
  // Add limit=1000 to ensure we get all apps (default is only 100)
  params.append("limit", "1000");

  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/apps?${params.toString()}`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch app`);
  }

  const apps = await response.json();
  return apps;
}

export async function getApp(
  appName: string,
  apiKey: string,
): Promise<App | null> {
  const apps = await getApps([appName], apiKey);
  return apps.length > 0 ? apps[0] : null;
}

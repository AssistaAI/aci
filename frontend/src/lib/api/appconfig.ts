import { AppConfig } from "@/lib/types/appconfig";

export interface AppConfigsParams {
  limit?: number;
  offset?: number;
  app_names?: string[];
}

export async function getAllAppConfigs(
  apiKey: string,
  params?: AppConfigsParams,
): Promise<AppConfig[]> {
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
    ? `${process.env.NEXT_PUBLIC_API_URL}/v1/app-configurations?${searchParams.toString()}`
    : `${process.env.NEXT_PUBLIC_API_URL}/v1/app-configurations`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-API-KEY": apiKey,
    },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch app configurations: ${response.status} ${response.statusText}`,
    );
  }

  const appConfigs = await response.json();
  return appConfigs;
}

export async function getAppConfig(
  appName: string,
  apiKey: string,
): Promise<AppConfig | null> {
  const configs = await getAllAppConfigs(apiKey, {
    app_names: [appName],
  });
  return configs.length > 0 ? configs[0] : null;
}

export class AppAlreadyConfiguredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AppAlreadyConfiguredError";
    Object.setPrototypeOf(this, new.target.prototype); // Restore prototype chain
  }
}

export async function createAppConfig(
  appName: string,
  security_scheme: string,
  apiKey: string,
  security_scheme_overrides?: {
    oauth2?: {
      client_id: string;
      client_secret: string;
      redirect_url?: string;
    } | null;
  },
): Promise<AppConfig> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/app-configurations`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": apiKey,
      },
      body: JSON.stringify({
        app_name: appName,
        security_scheme: security_scheme,
        security_scheme_overrides: security_scheme_overrides ?? {},
        all_functions_enabled: true,
        enabled_functions: [],
      }),
    },
  );

  if (response.status === 409) {
    throw new AppAlreadyConfiguredError(
      `App configuration already exists for app: ${appName}`,
    );
  }

  if (!response.ok) {
    throw new Error(
      `Failed to configure app: ${response.status} ${response.statusText}`,
    );
  }

  const appConfig = await response.json();
  return appConfig;
}

export async function updateAppConfig(
  appName: string,
  enabled: boolean,
  apiKey: string,
): Promise<AppConfig> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/app-configurations/${appName}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": apiKey,
      },
      body: JSON.stringify({
        enabled: enabled,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to update app configuration for ${appName}: ${response.status} ${response.statusText}`,
    );
  }

  const appConfig = await response.json();
  return appConfig;
}

export async function deleteAppConfig(
  appName: string,
  apiKey: string,
): Promise<Response> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/app-configurations/${appName}`,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to delete app configuration for ${appName}: ${response.status} ${response.statusText}`,
    );
  }

  return response;
}

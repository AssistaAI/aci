/**
 * Optimized API client for playground initialization
 * Uses lightweight endpoints to reduce payload size and improve performance
 */

export interface PlaygroundAppSummary {
  name: string;
  display_name: string;
  logo: string | null;
}

export interface PlaygroundLinkedAccountOwner {
  linked_account_owner_id: string;
  app_count: number;
}

export interface PlaygroundInitResponse {
  apps: PlaygroundAppSummary[];
  linked_account_owners: PlaygroundLinkedAccountOwner[];
  total_function_count: number;
}

/**
 * Fetch optimized playground initialization data
 * This endpoint returns only essential data without full function definitions
 */
export async function getPlaygroundInit(
  apiKey: string,
  linked_account_owner_id?: string
): Promise<PlaygroundInitResponse> {
  const params = new URLSearchParams();
  if (linked_account_owner_id) {
    params.append("linked_account_owner_id", linked_account_owner_id);
  }

  const url = `${process.env.NEXT_PUBLIC_API_URL}/v1/playground/init${params.toString() ? `?${params.toString()}` : ""}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-API-KEY": apiKey,
    },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch playground init: ${response.status} ${response.statusText}`
    );
  }

  return response.json();
}

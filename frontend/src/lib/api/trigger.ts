import {
  Trigger,
  TriggerEvent,
  CreateTriggerRequest,
  UpdateTriggerRequest,
  TriggerStats,
  TriggerHealthCheck,
  TriggerWithToken,
} from "@/lib/types/trigger";

/**
 * Get all triggers for the current project
 */
export async function getAllTriggers(apiKey: string): Promise<Trigger[]> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch triggers: ${response.status} ${response.statusText}`,
    );
  }

  const triggers = await response.json();
  return triggers;
}

/**
 * Get triggers filtered by app name
 */
export async function getAppTriggers(
  appName: string,
  apiKey: string,
): Promise<Trigger[]> {
  const params = new URLSearchParams();
  params.append("app_name", appName);

  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers?${params.toString()}`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch app triggers: ${response.status} ${response.statusText}`,
    );
  }

  const triggers = await response.json();
  return triggers;
}

/**
 * Get a specific trigger by ID
 */
export async function getTrigger(
  triggerId: string,
  apiKey: string,
): Promise<Trigger> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch trigger: ${response.status} ${response.statusText}`,
    );
  }

  const trigger = await response.json();
  return trigger;
}

/**
 * Create a new trigger subscription
 */
export async function createTrigger(
  request: CreateTriggerRequest,
  apiKey: string,
): Promise<TriggerWithToken> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": apiKey,
      },
      body: JSON.stringify(request),
    },
  );

  if (!response.ok) {
    let errorMsg = `Failed to create trigger: ${response.status} ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData && errorData.detail) {
        errorMsg = errorData.detail;
      }
    } catch (e) {
      console.error("Error parsing error response:", e);
    }
    throw new Error(errorMsg);
  }

  const trigger = await response.json();
  return trigger;
}

/**
 * Update a trigger (pause/resume, update config)
 */
export async function updateTrigger(
  triggerId: string,
  request: UpdateTriggerRequest,
  apiKey: string,
): Promise<Trigger> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-API-KEY": apiKey,
      },
      body: JSON.stringify(request),
    },
  );

  if (!response.ok) {
    let errorMsg = `Failed to update trigger: ${response.status} ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData && errorData.detail) {
        errorMsg = errorData.detail;
      }
    } catch (e) {
      console.error("Error parsing error response:", e);
    }
    throw new Error(errorMsg);
  }

  const trigger = await response.json();
  return trigger;
}

/**
 * Delete a trigger and unsubscribe from the third-party service
 */
export async function deleteTrigger(
  triggerId: string,
  apiKey: string,
): Promise<void> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}`,
    {
      method: "DELETE",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to delete trigger: ${response.status} ${response.statusText}`,
    );
  }
}

/**
 * Get events for a specific trigger
 */
export async function getTriggerEvents(
  triggerId: string,
  apiKey: string,
  options?: {
    status?: string;
    limit?: number;
    offset?: number;
  },
): Promise<TriggerEvent[]> {
  const params = new URLSearchParams();
  if (options?.status) params.append("status", options.status);
  if (options?.limit) params.append("limit", options.limit.toString());
  if (options?.offset) params.append("offset", options.offset.toString());

  const queryString = params.toString();
  const url = queryString
    ? `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}/events?${queryString}`
    : `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}/events`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-API-KEY": apiKey,
    },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch trigger events: ${response.status} ${response.statusText}`,
    );
  }

  const events = await response.json();
  return events;
}

/**
 * Get all events across all triggers (with optional filters)
 */
export async function getAllTriggerEvents(
  apiKey: string,
  options?: {
    trigger_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  },
): Promise<TriggerEvent[]> {
  const params = new URLSearchParams();
  if (options?.trigger_id) params.append("trigger_id", options.trigger_id);
  if (options?.status) params.append("status", options.status);
  if (options?.limit) params.append("limit", options.limit.toString());
  if (options?.offset) params.append("offset", options.offset.toString());

  const queryString = params.toString();
  const url = queryString
    ? `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/events/all?${queryString}`
    : `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/events/all`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "X-API-KEY": apiKey,
    },
  });

  if (!response.ok) {
    throw new Error(
      `Failed to fetch all trigger events: ${response.status} ${response.statusText}`,
    );
  }

  const events = await response.json();
  return events;
}

/**
 * Get statistics for a trigger
 */
export async function getTriggerStats(
  triggerId: string,
  apiKey: string,
): Promise<TriggerStats> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}/stats`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch trigger stats: ${response.status} ${response.statusText}`,
    );
  }

  const stats = await response.json();
  return stats;
}

/**
 * Get health check for a trigger
 */
export async function getTriggerHealth(
  triggerId: string,
  apiKey: string,
): Promise<TriggerHealthCheck> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/v1/triggers/${triggerId}/health`,
    {
      method: "GET",
      headers: {
        "X-API-KEY": apiKey,
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch trigger health: ${response.status} ${response.statusText}`,
    );
  }

  const health = await response.json();
  return health;
}

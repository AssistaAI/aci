export type TriggerStatus = "active" | "paused" | "error" | "expired";

export type TriggerEventStatus = "pending" | "delivered" | "failed" | "expired";

export type Trigger = {
  id: string;
  project_id: string;
  app_id: string;
  app_name: string;
  linked_account_id: string;
  trigger_name: string;
  trigger_type: string;
  description: string;
  webhook_url: string;
  external_webhook_id: string | null;
  verification_token: string;
  config: Record<string, any>;
  status: TriggerStatus;
  last_triggered_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TriggerEvent = {
  id: string;
  trigger_id: string;
  event_type: string;
  event_data: Record<string, any>;
  external_event_id: string | null;
  status: TriggerEventStatus;
  error_message: string | null;
  received_at: string;
  processed_at: string | null;
  delivered_at: string | null;
  expires_at: string | null;
};

export type CreateTriggerRequest = {
  app_name: string;
  linked_account_owner_id: string;
  trigger_name: string;
  trigger_type: string;
  description: string;
  config?: Record<string, any>;
  status?: TriggerStatus;
  expires_at?: string;
};

export type UpdateTriggerRequest = {
  status?: TriggerStatus;
  config?: Record<string, any>;
};

export type TriggerStats = {
  total_events: number;
  delivered_events: number;
  failed_events: number;
  pending_events: number;
  last_event_at: string | null;
  success_rate: number;
};

export type TriggerHealthCheck = {
  is_healthy: boolean;
  status: TriggerStatus;
  last_event_at: string | null;
  days_since_last_event: number | null;
  error_rate: number;
  issues: string[];
};

export type TriggerWithToken = Trigger & {
  verification_token: string;
};

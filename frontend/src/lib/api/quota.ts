import { Plan } from "@/lib/types/billing";
import { QuotaUsage } from "@/lib/types/quota";

export async function getQuotaUsage(
  accessToken: string,
  orgId: string,
): Promise<QuotaUsage> {
  void accessToken;
  void orgId;

  return {
    projects_used: 0,
    linked_accounts_used: 0,
    agent_credentials_used: 0,
    api_calls_used: 0,
    plan: {
      name: Plan.Unlimited,
      is_unlimited: true,
      features: {
        projects: Number.MAX_SAFE_INTEGER,
        linked_accounts: Number.MAX_SAFE_INTEGER,
        api_calls_monthly: Number.MAX_SAFE_INTEGER,
        agent_credentials: Number.MAX_SAFE_INTEGER,
        developer_seats: Number.MAX_SAFE_INTEGER,
        custom_oauth: true,
        log_retention_days: 3650,
      },
    },
  };
}

import {
  Interval,
  Plan,
  Subscription,
  SubscriptionStatus,
} from "@/lib/types/billing";

export async function getSubscription(
  accessToken: string,
  orgId: string,
): Promise<Subscription> {
  void accessToken;
  void orgId;

  return {
    plan: Plan.Unlimited,
    status: SubscriptionStatus.Active,
  };
}

export async function createCheckoutSession(
  accessToken: string,
  orgId: string,
  planName: string,
  interval: Interval,
): Promise<string> {
  void accessToken;
  void orgId;
  void planName;
  void interval;

  throw new Error("Billing actions are disabled in unlimited mode.");
}

export async function createCustomerPortalSession(
  accessToken: string,
  orgId: string,
): Promise<string> {
  void accessToken;
  void orgId;

  throw new Error("Billing portal is unavailable in unlimited mode.");
}

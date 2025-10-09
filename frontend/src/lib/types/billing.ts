export enum Interval {
  Month = "month",
  Year = "year",
}

export enum SubscriptionStatus {
  Incomplete = "incomplete",
  IncompleteExpired = "incomplete_expired",
  Trialing = "trialing",
  Active = "active",
  PastDue = "past_due",
  Canceled = "canceled",
  Unpaid = "unpaid",
  Paused = "paused",
}

export enum Plan {
  Free = "free",
  Starter = "starter",
  Team = "team",
  Unlimited = "unlimited",
}

export interface Subscription {
  plan: Plan;
  status: SubscriptionStatus;
}

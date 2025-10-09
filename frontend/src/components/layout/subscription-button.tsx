"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { BsStars } from "react-icons/bs";
import { Plan } from "@/lib/types/billing";
import { useQuota } from "@/hooks/use-quota";

export function getUpgradeButtonText(planName: Plan): string {
  switch (planName) {
    case Plan.Free:
      return "Upgrade to Starter Plan";
    case Plan.Starter:
      return "Starter Plan";
    case Plan.Team:
      return "Team Plan";
    case Plan.Unlimited:
      return "Unlimited Plan";
    default:
      return "Upgrade Plan";
  }
}

interface UpgradeButtonProps {
  size?: "default" | "sm";
  className?: string;
}

export function UpgradeButton({
  size = "default",
  className,
}: UpgradeButtonProps = {}) {
  const { data: quotaData, isPending, error } = useQuota();

  if (isPending || error || !quotaData?.plan?.name) {
    return null;
  }

  const planName = (quotaData.plan.name as Plan) ?? Plan.Unlimited;

  if (planName === Plan.Unlimited) {
    return (
      <Button
        size={size}
        className={`gap-2 ${className?.includes("w-full") ? "w-full" : ""} ${className ?? ""}`}
        variant="outline"
        disabled
      >
        <BsStars className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
        {getUpgradeButtonText(planName)}
      </Button>
    );
  }

  return (
    <Link href="/pricing" className={className}>
      <Button
        size={size}
        className={`gap-2 transition-all duration-200 hover:scale-105 ${className?.includes("w-full") ? "w-full" : ""}`}
      >
        <BsStars className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
        {getUpgradeButtonText(planName)}
      </Button>
    </Link>
  );
}

import { Badge } from "@/components/ui/badge";
import { TriggerStatus } from "@/lib/types/trigger";
import { CheckCircle2, Pause, AlertCircle, Clock } from "lucide-react";

interface TriggerStatusBadgeProps {
  status: TriggerStatus;
}

export function TriggerStatusBadge({ status }: TriggerStatusBadgeProps) {
  const config = {
    active: {
      label: "Active",
      variant: "default" as const,
      icon: CheckCircle2,
      className: "bg-green-100 text-green-800 hover:bg-green-100",
    },
    paused: {
      label: "Paused",
      variant: "secondary" as const,
      icon: Pause,
      className: "bg-gray-100 text-gray-800 hover:bg-gray-100",
    },
    error: {
      label: "Error",
      variant: "destructive" as const,
      icon: AlertCircle,
      className: "",
    },
    expired: {
      label: "Expired",
      variant: "outline" as const,
      icon: Clock,
      className: "bg-orange-100 text-orange-800 hover:bg-orange-100",
    },
  };

  const { label, variant, icon: Icon, className } = config[status];

  return (
    <Badge variant={variant} className={className}>
      <Icon className="mr-1 h-3 w-3" />
      {label}
    </Badge>
  );
}

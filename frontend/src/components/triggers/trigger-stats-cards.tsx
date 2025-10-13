import { TriggerStats } from "@/lib/types/trigger";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
} from "lucide-react";

interface TriggerStatsCardsProps {
  stats: TriggerStats;
}

export function TriggerStatsCards({ stats }: TriggerStatsCardsProps) {
  const cards = [
    {
      title: "Total Events",
      value: stats.total_events.toLocaleString(),
      icon: Activity,
      description: "Events received",
      color: "text-blue-600",
      bgColor: "bg-blue-100",
    },
    {
      title: "Delivered",
      value: stats.delivered_events.toLocaleString(),
      icon: CheckCircle2,
      description: "Successfully processed",
      color: "text-green-600",
      bgColor: "bg-green-100",
    },
    {
      title: "Failed",
      value: stats.failed_events.toLocaleString(),
      icon: XCircle,
      description: "Processing errors",
      color: "text-red-600",
      bgColor: "bg-red-100",
    },
    {
      title: "Pending",
      value: stats.pending_events.toLocaleString(),
      icon: Clock,
      description: "Awaiting processing",
      color: "text-yellow-600",
      bgColor: "bg-yellow-100",
    },
    {
      title: "Success Rate",
      value: `${Math.round(stats.success_rate * 100)}%`,
      icon: TrendingUp,
      description: stats.total_events > 0 ? "Delivery success" : "No events yet",
      color: stats.success_rate > 0.8 ? "text-green-600" : "text-orange-600",
      bgColor: stats.success_rate > 0.8 ? "bg-green-100" : "bg-orange-100",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <Card key={card.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {card.title}
              </CardTitle>
              <div className={`${card.bgColor} rounded-full p-2`}>
                <Icon className={`h-4 w-4 ${card.color}`} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{card.value}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {card.description}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

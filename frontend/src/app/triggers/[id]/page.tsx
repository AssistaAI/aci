"use client";

import { useTrigger, useTriggerEvents, useTriggerStats } from "@/hooks/use-triggers";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";
import { TriggerStatusBadge } from "@/components/triggers/trigger-status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { TriggerEventsTable } from "@/components/triggers/trigger-events-table";
import { TriggerStatsCards } from "@/components/triggers/trigger-stats-cards";

export default function TriggerDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const triggerId = params.id as string;

  const { data: trigger, isPending: triggerLoading, isError: triggerError } = useTrigger(triggerId);
  const { data: events, isPending: eventsLoading } = useTriggerEvents(triggerId);
  const { data: stats } = useTriggerStats(triggerId);

  if (triggerLoading) {
    return (
      <div className="flex justify-center items-center py-16">
        <Loader2 className="animate-spin h-10 w-10 text-muted-foreground mr-2" />
        Loading trigger details...
      </div>
    );
  }

  if (triggerError || !trigger) {
    return (
      <div className="flex flex-col justify-center items-center py-16">
        <AlertCircle className="h-10 w-10 text-destructive mb-2" />
        <p className="text-sm text-muted-foreground">
          Failed to load trigger. It may have been deleted.
        </p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => router.push("/triggers")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Triggers
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="m-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/triggers")}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Triggers
        </Button>

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold">{trigger.trigger_name}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {trigger.description}
            </p>
          </div>
          <TriggerStatusBadge status={trigger.status} />
        </div>

        <div className="flex gap-2 mt-4">
          <Badge variant="outline">{trigger.app_name}</Badge>
          <Badge variant="secondary">
            <code className="text-xs">{trigger.trigger_type}</code>
          </Badge>
        </div>
      </div>

      <Separator />

      <div className="m-4 space-y-6">
        {/* Stats Cards */}
        {stats && <TriggerStatsCards stats={stats} />}

        {/* Webhook Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
            <CardDescription>
              Webhook details and connection information
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Webhook URL
              </label>
              <div className="mt-1">
                <code className="text-xs bg-muted px-3 py-2 rounded block break-all">
                  {trigger.webhook_url}
                </code>
              </div>
            </div>

            {trigger.external_webhook_id && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  External Webhook ID
                </label>
                <div className="mt-1">
                  <code className="text-xs bg-muted px-3 py-2 rounded block">
                    {trigger.external_webhook_id}
                  </code>
                </div>
              </div>
            )}

            {trigger.last_triggered_at && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">
                  Last Triggered
                </label>
                <div className="mt-1 text-sm">
                  {new Date(trigger.last_triggered_at).toLocaleString()}
                </div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Created At
              </label>
              <div className="mt-1 text-sm">
                {new Date(trigger.created_at).toLocaleString()}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Events Table */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Events</CardTitle>
            <CardDescription>
              Webhook events received from {trigger.app_name}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {eventsLoading ? (
              <div className="flex justify-center items-center py-8">
                <Loader2 className="animate-spin h-6 w-6 text-muted-foreground" />
              </div>
            ) : (
              <TriggerEventsTable events={events || []} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

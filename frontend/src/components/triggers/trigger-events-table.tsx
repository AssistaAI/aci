"use client";

import { TriggerEvent } from "@/lib/types/trigger";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { formatDistanceToNow } from "date-fns";
import { InboxIcon, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState } from "react";

interface TriggerEventsTableProps {
  events: TriggerEvent[];
}

const EVENT_STATUS_CONFIG = {
  pending: {
    variant: "secondary" as const,
    className: "bg-yellow-100 text-yellow-800 hover:bg-yellow-100",
  },
  delivered: {
    variant: "default" as const,
    className: "bg-green-100 text-green-800 hover:bg-green-100",
  },
  failed: {
    variant: "destructive" as const,
    className: "",
  },
  expired: {
    variant: "outline" as const,
    className: "bg-gray-100 text-gray-800 hover:bg-gray-100",
  },
} as const;

export function TriggerEventsTable({ events }: TriggerEventsTableProps) {
  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <div className="rounded-full bg-muted p-4 mb-3">
          <InboxIcon className="h-8 w-8 text-muted-foreground" />
        </div>
        <h4 className="text-sm font-semibold mb-1">No events yet</h4>
        <p className="text-xs text-muted-foreground">
          Events will appear here when your trigger receives webhooks
        </p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Event Type</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Received</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => (
          <EventRow key={event.id} event={event} />
        ))}
      </TableBody>
    </Table>
  );
}

function EventRow({ event }: { event: TriggerEvent }) {
  const [isOpen, setIsOpen] = useState(false);

  const config = EVENT_STATUS_CONFIG[event.status] ?? {
    variant: "secondary" as const,
    className: "",
  };

  return (
    <>
      <TableRow>
        <TableCell>
          <code className="text-xs bg-muted px-2 py-1 rounded">
            {event.event_type || "unknown"}
          </code>
        </TableCell>
        <TableCell>
          <Badge variant={config.variant} className={config.className}>
            {event.status}
          </Badge>
        </TableCell>
        <TableCell>
          <span className="text-sm">
            {formatDistanceToNow(new Date(event.received_at), {
              addSuffix: true,
            })}
          </span>
        </TableCell>
        <TableCell className="text-right">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsOpen(!isOpen)}
            aria-expanded={isOpen}
            aria-controls={`event-details-${event.id}`}
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform ${
                isOpen ? "transform rotate-180" : ""
              }`}
            />
            {isOpen ? "Hide" : "View"} Data
          </Button>
        </TableCell>
      </TableRow>
      {isOpen && (
        <TableRow>
          <TableCell colSpan={4} className="bg-muted/30">
            <div id={`event-details-${event.id}`} className="p-4 space-y-3">
              {event.external_event_id && (
                <div>
                  <label className="text-xs font-medium text-muted-foreground">
                    Event ID
                  </label>
                  <div className="mt-1">
                    <code className="text-xs bg-background px-2 py-1 rounded">
                      {event.external_event_id}
                    </code>
                  </div>
                </div>
              )}

              {event.error_message && (
                <div>
                  <label className="text-xs font-medium text-destructive">
                    Error Message
                  </label>
                  <div className="mt-1 text-xs text-destructive">
                    {event.error_message}
                  </div>
                </div>
              )}

              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Event Data
                </label>
                <div className="mt-1">
                  <pre className="text-xs bg-background p-3 rounded border overflow-x-auto max-h-96">
                    {JSON.stringify(event.event_data, null, 2)}
                  </pre>
                </div>
              </div>

              <div className="flex gap-4 text-xs text-muted-foreground">
                {event.processed_at && (
                  <div>
                    Processed: {new Date(event.processed_at).toLocaleString()}
                  </div>
                )}
                {event.delivered_at && (
                  <div>
                    Delivered: {new Date(event.delivered_at).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

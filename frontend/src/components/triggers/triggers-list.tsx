"use client";

import { useState, useMemo } from "react";
import { Trigger, TriggerStatus } from "@/lib/types/trigger";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TriggerStatusBadge } from "./trigger-status-badge";
import { TriggerActionsMenu } from "./trigger-actions-menu";
import { CreateTriggerDialog } from "./create-trigger-dialog";
import { formatDistanceToNow } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { InboxIcon, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface TriggersListProps {
  triggers: Trigger[];
  isCreateDialogOpen: boolean;
  setIsCreateDialogOpen: (open: boolean) => void;
}

export function TriggersList({
  triggers,
  isCreateDialogOpen,
  setIsCreateDialogOpen,
}: TriggersListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<TriggerStatus | "all">(
    "all",
  );
  const [appFilter, setAppFilter] = useState<string>("all");

  // Get unique app names for filter
  const uniqueApps = useMemo(() => {
    const apps = new Set(triggers.map((t) => t.app_name));
    return Array.from(apps).sort();
  }, [triggers]);

  // Filter triggers based on search and filters
  const filteredTriggers = useMemo(() => {
    return triggers.filter((trigger) => {
      // Search filter
      const matchesSearch =
        searchQuery === "" ||
        trigger.trigger_name
          .toLowerCase()
          .includes(searchQuery.toLowerCase()) ||
        trigger.trigger_type
          .toLowerCase()
          .includes(searchQuery.toLowerCase()) ||
        trigger.description?.toLowerCase().includes(searchQuery.toLowerCase());

      // Status filter
      const matchesStatus =
        statusFilter === "all" || trigger.status === statusFilter;

      // App filter
      const matchesApp = appFilter === "all" || trigger.app_name === appFilter;

      return matchesSearch && matchesStatus && matchesApp;
    });
  }, [triggers, searchQuery, statusFilter, appFilter]);
  if (triggers.length === 0) {
    return (
      <>
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="rounded-full bg-muted p-6 mb-4">
            <InboxIcon className="h-12 w-12 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No triggers yet</h3>
          <p className="text-sm text-muted-foreground mb-4 max-w-sm">
            Get started by creating your first trigger to receive real-time
            events from your connected apps.
          </p>
        </div>
        <CreateTriggerDialog
          open={isCreateDialogOpen}
          onOpenChange={setIsCreateDialogOpen}
        />
      </>
    );
  }

  return (
    <>
      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search triggers..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            aria-label="Search triggers"
          />
        </div>
        <Select value={appFilter} onValueChange={setAppFilter}>
          <SelectTrigger
            className="w-full sm:w-[180px]"
            aria-label="Filter by app"
          >
            <SelectValue placeholder="All Apps" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Apps</SelectItem>
            {uniqueApps.map((app) => (
              <SelectItem key={app} value={app}>
                {app}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={statusFilter}
          onValueChange={(value) =>
            setStatusFilter(value as TriggerStatus | "all")
          }
        >
          <SelectTrigger
            className="w-full sm:w-[180px]"
            aria-label="Filter by status"
          >
            <SelectValue placeholder="All Statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="paused">Paused</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="expired">Expired</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Results count */}
      {filteredTriggers.length !== triggers.length && (
        <div className="text-sm text-muted-foreground mb-4">
          Showing {filteredTriggers.length} of {triggers.length} triggers
        </div>
      )}

      {filteredTriggers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center border rounded-md">
          <div className="rounded-full bg-muted p-6 mb-4">
            <InboxIcon className="h-12 w-12 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold mb-2">No triggers found</h3>
          <p className="text-sm text-muted-foreground mb-4 max-w-sm">
            Try adjusting your search or filters to find what you're looking
            for.
          </p>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>App</TableHead>
                <TableHead>Trigger Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Triggered</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTriggers.map((trigger) => (
                <TableRow key={trigger.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{trigger.app_name}</Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium">{trigger.trigger_name}</div>
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      {trigger.description}
                    </div>
                  </TableCell>
                  <TableCell>
                    <code className="text-xs bg-muted px-2 py-1 rounded">
                      {trigger.trigger_type}
                    </code>
                  </TableCell>
                  <TableCell>
                    <TriggerStatusBadge status={trigger.status} />
                  </TableCell>
                  <TableCell>
                    {trigger.last_triggered_at ? (
                      <span className="text-sm">
                        {formatDistanceToNow(
                          new Date(trigger.last_triggered_at),
                          {
                            addSuffix: true,
                          },
                        )}
                      </span>
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        Never
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <TriggerActionsMenu trigger={trigger} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <CreateTriggerDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
      />
    </>
  );
}

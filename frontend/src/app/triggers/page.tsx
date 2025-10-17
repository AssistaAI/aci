"use client";

import { TriggersList } from "@/components/triggers/triggers-list";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useTriggers } from "@/hooks/use-triggers";
import { AlertCircle, Loader2, Plus } from "lucide-react";
import { useState } from "react";

export default function TriggersPage() {
  const { data: triggers, isPending, isError } = useTriggers();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);

  return (
    <div>
      <div className="m-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Triggers</h1>
          <p className="text-sm text-muted-foreground">
            Manage real-time event subscriptions from your connected apps.
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create Trigger
        </Button>
      </div>
      <Separator />

      <div className="m-4">
        {isPending ? (
          <div className="flex justify-center items-center py-16">
            <Loader2 className="animate-spin h-10 w-10 text-muted-foreground mr-2" />
            Loading triggers...
          </div>
        ) : isError ? (
          <div className="flex flex-col justify-center items-center py-16">
            <AlertCircle className="h-10 w-10 text-destructive mb-2" />
            <p className="text-sm text-muted-foreground">
              Failed to load triggers. Please try to refresh the page.
            </p>
          </div>
        ) : (
          <TriggersList
            triggers={triggers || []}
            isCreateDialogOpen={isCreateDialogOpen}
            setIsCreateDialogOpen={setIsCreateDialogOpen}
          />
        )}
      </div>
    </div>
  );
}

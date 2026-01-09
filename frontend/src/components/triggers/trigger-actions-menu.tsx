"use client";

import { Trigger } from "@/lib/types/trigger";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import {
  MoreHorizontal,
  Play,
  Pause,
  Trash2,
  Eye,
  BarChart3,
} from "lucide-react";
import { useUpdateTrigger, useDeleteTrigger } from "@/hooks/use-triggers";
import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface TriggerActionsMenuProps {
  trigger: Trigger;
}

export function TriggerActionsMenu({ trigger }: TriggerActionsMenuProps) {
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const updateTrigger = useUpdateTrigger();
  const deleteTrigger = useDeleteTrigger();
  const router = useRouter();

  const handleToggleStatus = async () => {
    try {
      const newStatus = trigger.status === "active" ? "paused" : "active";
      await updateTrigger.mutateAsync({
        triggerId: trigger.id,
        request: { status: newStatus },
      });
      toast.success("Trigger updated", {
        description: `Trigger has been ${newStatus === "active" ? "resumed" : "paused"}.`,
      });
    } catch (error) {
      toast.error("Failed to update trigger", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteTrigger.mutateAsync(trigger.id);
      toast.success("Trigger deleted", {
        description: "Trigger has been successfully deleted.",
      });
      setIsDeleteDialogOpen(false);
    } catch (error) {
      toast.error("Failed to delete trigger", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    }
  };

  const handleViewDetails = () => {
    router.push(`/triggers/${trigger.id}`);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={handleViewDetails}>
            <Eye className="mr-2 h-4 w-4" />
            View Details
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleViewDetails}>
            <BarChart3 className="mr-2 h-4 w-4" />
            View Events
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={handleToggleStatus}
            disabled={updateTrigger.isPending}
          >
            {trigger.status === "active" ? (
              <>
                <Pause className="mr-2 h-4 w-4" />
                Pause Trigger
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Resume Trigger
              </>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setIsDeleteDialogOpen(true)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete Trigger
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete the trigger &quot;{trigger.trigger_name}&quot;
              and unsubscribe from the third-party service. This action cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleteTrigger.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteTrigger.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

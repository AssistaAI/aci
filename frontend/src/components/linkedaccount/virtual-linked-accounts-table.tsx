"use client";

import { useRef, useMemo, useEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { LinkedAccount } from "@/lib/types/linkedaccount";
import { useLinkedAccountsInfinite } from "@/hooks/use-linked-account";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { IdDisplay } from "@/components/apps/id-display";
import { Button } from "@/components/ui/button";
import { EnhancedSwitch } from "@/components/ui-extensions/enhanced-switch/enhanced-switch";
import { LinkedAccountDetails } from "@/components/linkedaccount/linked-account-details";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { GoTrash } from "react-icons/go";
import { toast } from "sonner";
import {
  useDeleteLinkedAccount,
  useUpdateLinkedAccount,
} from "@/hooks/use-linked-account";
import { useMetaInfo } from "@/components/context/metainfo";
import { formatToLocalTime } from "@/utils/time";
import Image from "next/image";
import { App } from "@/lib/types/app";
import { Loader2 } from "lucide-react";

interface VirtualLinkedAccountsTableProps {
  appsMap: Record<string, App>;
}

export function VirtualLinkedAccountsTable({
  appsMap,
}: VirtualLinkedAccountsTableProps) {
  const { activeProject } = useMetaInfo();
  const parentRef = useRef<HTMLDivElement>(null);

  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useLinkedAccountsInfinite();

  const { mutateAsync: deleteLinkedAccount } = useDeleteLinkedAccount();
  const { mutateAsync: updateLinkedAccount } = useUpdateLinkedAccount();

  // Flatten all pages into a single array
  const allRows = useMemo(
    () => data?.pages.flatMap((page) => page.data) ?? [],
    [data],
  );

  const rowVirtualizer = useVirtualizer({
    count: hasNextPage ? allRows.length + 1 : allRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 60, // Estimated row height in pixels
    overscan: 10, // Number of items to render outside visible area
  });

  const virtualItems = rowVirtualizer.getVirtualItems();

  // Fetch next page when near the end
  useEffect(() => {
    const [lastItem] = [...virtualItems].reverse();

    if (!lastItem) return;

    if (
      lastItem.index >= allRows.length - 1 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [
    hasNextPage,
    fetchNextPage,
    allRows.length,
    isFetchingNextPage,
    virtualItems,
  ]);

  const toggleAccountStatus = async (
    accountId: string,
    newStatus: boolean,
  ): Promise<boolean> => {
    try {
      await updateLinkedAccount({
        linkedAccountId: accountId,
        enabled: newStatus,
      });
      return true;
    } catch (error) {
      console.error("Failed to update linked account:", error);
      toast.error("Failed to update linked account");
      return false;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="flex flex-col items-center space-y-4">
          <Loader2 className="h-8 w-8 animate-spin" />
          <p className="text-sm text-muted-foreground">
            Loading linked accounts...
          </p>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center p-8 text-destructive">
        Failed to load linked accounts. Please refresh the page.
      </div>
    );
  }

  if (allRows.length === 0) {
    return (
      <div className="text-center p-8 text-muted-foreground">
        No linked accounts found
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className="h-[calc(100vh-300px)] overflow-auto border rounded-md"
    >
      <Table>
        <TableHeader className="sticky top-0 bg-background z-10">
          <TableRow>
            <TableHead className="w-[250px]">App Name</TableHead>
            <TableHead className="w-[200px]">Linked Account Owner ID</TableHead>
            <TableHead className="w-[180px]">Created At</TableHead>
            <TableHead className="w-[180px]">Last Used At</TableHead>
            <TableHead className="w-[100px]">Enabled</TableHead>
            <TableHead className="w-[120px]">Details</TableHead>
            <TableHead className="w-[80px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <tr style={{ height: `${rowVirtualizer.getTotalSize()}px` }}>
            <td />
          </tr>
          {virtualItems.map((virtualRow) => {
            const isLoaderRow = virtualRow.index > allRows.length - 1;
            const account = allRows[virtualRow.index];

            return (
              <TableRow
                key={virtualRow.index}
                data-index={virtualRow.index}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {isLoaderRow ? (
                  <TableCell colSpan={7} className="text-center">
                    {isFetchingNextPage ? (
                      <Loader2 className="inline h-4 w-4 animate-spin" />
                    ) : (
                      "No more results"
                    )}
                  </TableCell>
                ) : (
                  <>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {appsMap[account.app_name]?.logo && (
                          <div className="relative h-6 w-6 shrink-0 overflow-hidden">
                            <Image
                              src={appsMap[account.app_name].logo}
                              alt={`${account.app_name} logo`}
                              fill
                              className="object-contain rounded-sm"
                            />
                          </div>
                        )}
                        <span className="font-medium">{account.app_name}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <IdDisplay id={account.linked_account_owner_id} />
                    </TableCell>
                    <TableCell>
                      {formatToLocalTime(account.created_at)}
                    </TableCell>
                    <TableCell>
                      {account.last_used_at
                        ? formatToLocalTime(account.last_used_at)
                        : "Never"}
                    </TableCell>
                    <TableCell>
                      <EnhancedSwitch
                        checked={account.enabled}
                        onAsyncChange={(checked) =>
                          toggleAccountStatus(account.id, checked)
                        }
                        successMessage={(newState) =>
                          `Linked account ${account.linked_account_owner_id} ${newState ? "enabled" : "disabled"}`
                        }
                        errorMessage="Failed to update linked account"
                      />
                    </TableCell>
                    <TableCell>
                      <LinkedAccountDetails
                        account={account}
                        toggleAccountStatus={toggleAccountStatus}
                      >
                        <Button variant="outline" size="sm">
                          See Details
                        </Button>
                      </LinkedAccountDetails>
                    </TableCell>
                    <TableCell>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                          >
                            <GoTrash />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              Confirm Deletion?
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              This action cannot be undone. This will
                              permanently delete the linked account for owner ID
                              &quot;
                              {account.linked_account_owner_id}&quot;.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={async () => {
                                try {
                                  if (!activeProject) {
                                    console.warn("No active project");
                                    return;
                                  }
                                  await deleteLinkedAccount({
                                    linkedAccountId: account.id,
                                  });
                                  toast.success(
                                    `Linked account ${account.linked_account_owner_id} deleted`,
                                  );
                                } catch (error) {
                                  console.error(error);
                                  toast.error(
                                    "Failed to delete linked account",
                                  );
                                }
                              }}
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </TableCell>
                  </>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

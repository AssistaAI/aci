"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AddAccountForm } from "@/components/appconfig/add-account";
import { useMetaInfo } from "@/components/context/metainfo";
import { useApps } from "@/hooks/use-app";
import { useAppConfigs } from "@/hooks/use-app-config";
import { VirtualLinkedAccountsTable } from "@/components/linkedaccount/virtual-linked-accounts-table";
import { App } from "@/lib/types/app";
import { Loader2 } from "lucide-react";

export default function LinkedAccountsPageOptimized() {
  const { data: appConfigs = [], isPending: isConfigsPending } =
    useAppConfigs();
  const { data: apps, isPending: isAppsPending, isError } = useApps();
  const [appsMap, setAppsMap] = useState<Record<string, App>>({});

  // Build apps map for fast lookups
  useEffect(() => {
    if (apps && apps.length > 0) {
      setAppsMap(
        apps.reduce(
          (acc, app) => {
            acc[app.name] = app;
            return acc;
          },
          {} as Record<string, App>,
        ),
      );
    }
  }, [apps]);

  const isPageLoading = isAppsPending || isConfigsPending;

  return (
    <div>
      <div className="m-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Linked Accounts</h1>
          <p className="text-sm text-muted-foreground">
            Manage your linked accounts here. Optimized for large datasets with
            virtual scrolling.
          </p>
        </div>
        <div>
          {!isPageLoading && !isError && appConfigs.length > 0 && (
            <AddAccountForm
              appInfos={appConfigs.map((config) => ({
                name: config.app_name,
                logo: apps?.find((app) => app.name === config.app_name)?.logo,
                supported_security_schemes:
                  apps?.find((app) => app.name === config.app_name)
                    ?.supported_security_schemes || {},
              }))}
            />
          )}
        </div>
      </div>
      <Separator />

      <div className="m-4">
        {isPageLoading ? (
          <div className="flex items-center justify-center p-8">
            <div className="flex flex-col items-center space-y-4">
              <Loader2 className="h-8 w-8 animate-spin" />
              <p className="text-sm text-muted-foreground">Loading...</p>
            </div>
          </div>
        ) : (
          <VirtualLinkedAccountsTable appsMap={appsMap} />
        )}
      </div>
    </div>
  );
}

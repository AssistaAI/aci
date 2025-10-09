"use client";

import {
  DistributionDatapoint,
  TimeSeriesDatapoint,
} from "@/lib/types/analytics";

export function useAnalyticsQueries() {
  return {
    appDistributionData: [] as DistributionDatapoint[],
    functionDistributionData: [] as DistributionDatapoint[],
    appTimeSeriesData: [] as TimeSeriesDatapoint[],
    functionTimeSeriesData: [] as TimeSeriesDatapoint[],
    isLoading: false,
    error: null as Error | null,
    refetchAll: async () => [],
  };
}

import {
  DistributionDatapoint,
  TimeSeriesDatapoint,
} from "@/lib/types/analytics";

export async function getAppDistributionData(
  apiKey: string,
): Promise<DistributionDatapoint[]> {
  void apiKey;
  return [];
}

export async function getFunctionDistributionData(
  apiKey: string,
): Promise<DistributionDatapoint[]> {
  void apiKey;
  return [];
}

export async function getAppTimeSeriesData(
  apiKey: string,
): Promise<TimeSeriesDatapoint[]> {
  void apiKey;
  return [];
}

export async function getFunctionTimeSeriesData(
  apiKey: string,
): Promise<TimeSeriesDatapoint[]> {
  void apiKey;
  return [];
}

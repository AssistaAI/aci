import { getAllLinkedAccounts } from "@/lib/api/linkedaccount";
import { LinkedAccount } from "@/lib/types/linkedaccount";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import { useSelectedApiKey } from "./use-selected-api-key";

/**
 * Hook to fetch all linked accounts for the current project
 */
export function useLinkedAccounts() {
  const { data: session } = useSession();
  const { selectedApiKeyData } = useSelectedApiKey();

  return useQuery<LinkedAccount[]>({
    queryKey: ["linked-accounts", selectedApiKeyData?.id],
    queryFn: async () => {
      if (!selectedApiKeyData) {
        throw new Error("No API key selected");
      }
      return getAllLinkedAccounts(selectedApiKeyData.api_key);
    },
    enabled: !!session && !!selectedApiKeyData,
  });
}

import { useState, useCallback } from "react";

export interface PaginationState {
  pageIndex: number;
  pageSize: number;
}

export interface UsePaginationOptions {
  initialPageSize?: number;
  initialPageIndex?: number;
}

export interface UsePaginationReturn {
  pagination: PaginationState;
  limit: number;
  offset: number;
  setPageIndex: (pageIndex: number) => void;
  setPageSize: (pageSize: number) => void;
  nextPage: () => void;
  previousPage: () => void;
  resetPagination: () => void;
}

/**
 * Reusable hook for managing pagination state with server-side pagination support.
 * Provides both TanStack Table-compatible state and backend API-compatible limit/offset.
 */
export function usePagination(
  options: UsePaginationOptions = {},
): UsePaginationReturn {
  const { initialPageSize = 15, initialPageIndex = 0 } = options;

  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: initialPageIndex,
    pageSize: initialPageSize,
  });

  const limit = pagination.pageSize;
  const offset = pagination.pageIndex * pagination.pageSize;

  const setPageIndex = useCallback((pageIndex: number) => {
    setPagination((prev) => ({ ...prev, pageIndex }));
  }, []);

  const setPageSize = useCallback((pageSize: number) => {
    setPagination((prev) => ({ ...prev, pageSize, pageIndex: 0 }));
  }, []);

  const nextPage = useCallback(() => {
    setPagination((prev) => ({ ...prev, pageIndex: prev.pageIndex + 1 }));
  }, []);

  const previousPage = useCallback(() => {
    setPagination((prev) => ({
      ...prev,
      pageIndex: Math.max(0, prev.pageIndex - 1),
    }));
  }, []);

  const resetPagination = useCallback(() => {
    setPagination({
      pageIndex: initialPageIndex,
      pageSize: initialPageSize,
    });
  }, [initialPageIndex, initialPageSize]);

  return {
    pagination,
    limit,
    offset,
    setPageIndex,
    setPageSize,
    nextPage,
    previousPage,
    resetPagination,
  };
}

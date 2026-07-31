interface PaginatedResponse<T> {
  data: T[];
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export function paginate<T>(items: T[], page: number, limit: number): PaginatedResponse<T> {
  const start = (page - 1) * limit;
  const data = items.slice(start, start + limit);
  return {
    data,
    page,
    limit,
    total: items.length,
    totalPages: Math.max(1, Math.ceil(items.length / limit)),
  };
}

export function defaultPage(query: Record<string, string | undefined>): number {
  const p = parseInt(query["page"] ?? "1", 10);
  return Number.isFinite(p) && p > 0 ? p : 1;
}

export function defaultLimit(query: Record<string, string | undefined>): number {
  const l = parseInt(query["limit"] ?? "20", 10);
  return Number.isFinite(l) && l > 0 && l <= 100 ? l : 20;
}

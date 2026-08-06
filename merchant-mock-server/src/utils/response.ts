interface PaginatedResponse<T> {
  data: T[];
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export function paginate<T>(items: T[], page: number, limit: number): PaginatedResponse<T> {
  const start = (page - 1) * limit;
  return {
    data: items.slice(start, start + limit),
    page,
    limit,
    total: items.length,
    totalPages: Math.max(1, Math.ceil(items.length / limit)),
  };
}

export function defaultPage(query: Record<string, string | undefined>): number {
  const raw = query["page"];
  if (raw === undefined) return 1;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

export function defaultLimit(query: Record<string, string | undefined>): number {
  const raw = query["limit"];
  if (raw === undefined) return 20;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return 20;
  return Math.min(n, 100);
}

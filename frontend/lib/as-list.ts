/** A list from either a plain array or a paginated `{ results }` response, never
 * undefined: a page must not crash on an unexpected API shape. */
export function asList<T>(
  data: T[] | { results?: T[] } | null | undefined,
): T[] {
  if (Array.isArray(data)) return data;
  return Array.isArray(data?.results) ? data.results : [];
}

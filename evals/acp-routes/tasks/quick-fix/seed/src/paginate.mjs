/**
 * paginate(items, page, pageSize)
 *
 * Contract:
 * - `page` is 1-based. `pageSize` is the maximum number of items per page.
 * - Throws RangeError when page or pageSize is not a positive integer.
 * - Returns { items, page, pageSize, totalItems, totalPages, hasPrev, hasNext }.
 * - totalPages is Math.max(1, Math.ceil(totalItems / pageSize)), so an empty
 *   list still has one (empty) page.
 * - A page beyond totalPages returns an empty `items` array (it does not throw);
 *   hasPrev is then true and hasNext is false.
 * - Never mutates `items`.
 */
export function paginate(items, page, pageSize) {
  if (page < 1 || pageSize < 1) throw new RangeError("page and pageSize must be positive");
  const totalItems = items.length;
  const totalPages = Math.floor(totalItems / pageSize) + 1;
  const start = page * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page,
    pageSize,
    totalItems,
    totalPages,
    hasPrev: page > 1,
    hasNext: page <= totalPages,
  };
}

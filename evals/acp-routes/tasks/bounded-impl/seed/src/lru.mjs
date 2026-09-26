/**
 * LRUCache specification
 *
 * new LRUCache(capacity, { onEvict } = {})
 *   - capacity must be a positive integer, otherwise throw RangeError.
 *   - onEvict(key, value) is optional; call it once for every entry removed
 *     because of capacity (not for delete() or clear()).
 *
 * get(key)        -> value or undefined. A hit marks the key most recently used.
 * set(key, value) -> returns the cache (chainable). Inserting or updating marks
 *                    the key most recently used. If size would exceed capacity,
 *                    evict the least recently used entry first.
 * has(key)        -> boolean. Does NOT change recency.
 * peek(key)       -> value or undefined. Does NOT change recency.
 * delete(key)     -> true if an entry was removed, else false.
 * clear()         -> removes everything.
 * size            -> getter, number of entries.
 * keys()          -> array of keys, most recently used first.
 *
 * Keys may be any value (use SameValueZero, like Map). Values may be undefined;
 * has() must still report such entries as present.
 */
export class LRUCache {
  constructor(capacity, options = {}) {
    throw new Error("not implemented");
  }
}

export class LRUCache {
  #map = new Map();
  #capacity;
  #onEvict;
  constructor(capacity, { onEvict } = {}) {
    if (!Number.isInteger(capacity) || capacity < 1) throw new RangeError("capacity must be a positive integer");
    this.#capacity = capacity;
    this.#onEvict = onEvict;
  }
  get(key) {
    if (!this.#map.has(key)) return undefined;
    const value = this.#map.get(key);
    this.#map.delete(key);
    this.#map.set(key, value);
    return value;
  }
  set(key, value) {
    if (this.#map.has(key)) this.#map.delete(key);
    else if (this.#map.size >= this.#capacity) {
      const [oldKey, oldValue] = this.#map.entries().next().value;
      this.#map.delete(oldKey);
      this.#onEvict?.(oldKey, oldValue);
    }
    this.#map.set(key, value);
    return this;
  }
  has(key) { return this.#map.has(key); }
  peek(key) { return this.#map.get(key); }
  delete(key) { return this.#map.delete(key); }
  clear() { this.#map.clear(); }
  get size() { return this.#map.size; }
  keys() { return [...this.#map.keys()].reverse(); }
}

// The standing catalog Full catalog keeps on a test store, so the journeys run against a store with
// as many products as a real shop. Every name starts with "Catalog", so the test's products are easy to
// spot, and stays the same from run to run, so a run finds what earlier runs added.

// Each kind's prices end in their own cents, so no two products in the catalog share a price.
const KINDS = [
  { style: "TEE", one: "Tee", many: "Tees", cents: 1800, ounces: 6 },
  { style: "HOODIE", one: "Hoodie", many: "Hoodies", cents: 4225, ounces: 18 },
  { style: "CAP", one: "Cap", many: "Caps", cents: 2250, ounces: 4 },
  { style: "BEANIE", one: "Beanie", many: "Beanies", cents: 1675, ounces: 3 },
];

export const MAX_PER_CATEGORY = 50;

/**
 * The catalog of a size such as "3x8" (3 categories of 8 products): each category's title and
 * illustration style, and its products, each with a name, SKU, price, weight and photo of its own. A
 * size the catalog can't take throws, naming the sizes it can.
 */
export function catalogPlan(size) {
  const [, categories, perCategory] = String(size).match(/^\s*(\d+)\s*x\s*(\d+)\s*$/i)?.map(Number) ?? [];
  if (!(categories >= 1 && categories <= KINDS.length && perCategory >= 1 && perCategory <= MAX_PER_CATEGORY)) {
    throw new Error(`DINKUS_E2E_CATALOG is "${size}"; it takes categories x products per category, from 1x1 to ${KINDS.length}x${MAX_PER_CATEGORY}, such as 3x8.`);
  }
  return KINDS.slice(0, categories).map(kind => {
    const title = `Catalog ${kind.many}`;
    return {
      title,
      style: kind.style,
      products: Array.from({ length: perCategory }, (_, i) => {
        // Two digits keep one name from being the start of another ("Catalog Tee 1" and "Catalog Tee 10").
        const number = String(i + 1).padStart(2, "0");
        return {
          name: `Catalog ${kind.one} ${number}`,
          sku: `CATALOG-${kind.style}-${number}`,
          // A price of its own, so a card showing another product's price is caught.
          cents: kind.cents + i * 100,
          ounces: kind.ounces,
          photo: `catalog-${kind.one.toLowerCase()}-${number}.png`,
          category: title,
          style: kind.style,
        };
      }),
    };
  });
}

import { expect } from "./browser.mjs";

/** How long a check waits for something a loaded page should already show. */
export const quick = { timeout: 5_000 };

// innerText also reads an element the page hides, so only the first one a shopper can see counts.
export const text = async (locator) => (await locator.filter({ visible: true }).first().innerText(quick).catch(() => "")).replace(/\s+/g, " ").trim();

// Pages are fully loaded when read, so a missing link is absent now rather than worth waiting for.
export const firstHref = async (locator) => await locator.count() ? locator.first().getAttribute("href") : null;

/**
 * "photo", "placeholder" (the store's stand-in image), "illustration" (a picture that isn't the
 * product's own), "none", "broken" or "hidden" for a product's image area. The store marks a product's own
 * photo from Commerce with data-commerce-image.
 */
export async function photo(media) {
  const img = media.locator("img[data-commerce-image]").first();
  if (!await img.count()) return await media.locator("img").count() ? "illustration" : "none";
  // Product photos load lazily, so bring each into view first.
  await img.scrollIntoViewIfNeeded(quick).catch(() => {});
  const loaded = await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0), { timeout: 15_000 }).toBe(true).then(() => true, () => false);
  if (!loaded) return "broken";
  // A photo the page's styles hide is no photo to a shopper.
  if (!await img.isVisible()) return "hidden";
  return await img.getAttribute("data-placeholder") === "true" ? "placeholder" : "photo";
}

export const photoProblem = {
  placeholder: "has no photo of its own (the store shows its placeholder)",
  illustration: "shows a stand-in drawing instead of its photo",
  none: 'has no photo ("No image")',
  broken: "has a photo that didn't load",
  hidden: "has a photo shoppers can't see (the page hides it)",
};

/**
 * One product card's name, price, photo and the product page it links to, as a shopper sees them.
 * `withPhoto: false` leaves the photo unread, sparing the wait on one that doesn't load.
 */
export async function readCard(card, { withPhoto = true } = {}) {
  return {
    name: await text(card.locator("h2, h3, h4")),
    price: await text(card.locator(".price, [data-product-price]")),
    image: withPhoto ? await photo(card) : undefined,
    href: await card.getAttribute("href") ?? await firstHref(card.locator('a[href^="/products/"]')),
  };
}

# GrillTrack Visual Cycle & EmDash Translation

Use this playbook when running a visual design cycle on `template-store` or any EmDash Astro site.

## 1. Uploading the Real Verified Page (`code-to-design`)

Rather than prompting Stitch in a vacuum, start from the real verified EmDash route so Stitch sees the exact content sections, product cards, availability summaries, and disclosures:

1. Start the local Astro server or run a single-route HTML snapshot of the rendered page.
2. Inline critical stylesheet rules into a temporary standalone HTML snapshot (e.g., `.stitch/snapshots/home.html`) so Stitch renders the current baseline accurately.
3. Call `stitch_upload_file`:
   ```json
   {
     "projectId": "<PROJECT_ID>",
     "filePath": "/abs/path/to/.stitch/snapshots/home.html",
     "title": "/"
   }
   ```
4. Upload `.stitch/DESIGN.md` with `stitch_upload_file`, inspect `get_project` to find the uploaded screen instance (`id` + `sourceScreen`), and call `create_design_system_from_design_md`.

## 2. Generating the 5 GrillTrack Candidates

When `design.md` or the active GrillTrack track calls for comparing materially distinct candidates on the verified real page:

1. Call `generate_variants` on the uploaded baseline screen:
   ```json
   {
     "projectId": "<PROJECT_ID>",
     "selectedScreenIds": ["<BASELINE_SCREEN_ID>"],
     "prompt": "Explore 5 materially distinct editorial and storefront visual directions for this neutral DinkusKit store starter. Preserve all sections: Home opener hero, Persisted Shop catalog, Classic Merchandise catalog (Tees, Hoodies, Hats), and Connected Availability Summary panels with collapsible technical details. Do not add cart, checkout, or buy buttons.",
     "variantOptions": {
       "variantCount": 5,
       "creativeRange": "EXPLORE",
       "aspects": ["LAYOUT", "COLOR_SCHEME", "TEXT_FONT"]
     }
   }
   ```
2. For distinct aesthetic archetypes (e.g., *Warm Architectural Studio*, *Swiss Utilitarian Catalog*, *Editorial Monograph*, *Tactile Field Goods*, *High-Contrast Gallery*), you can also call `generate_screen_from_text` or `edit_screens` per candidate and download each via `stitch_download_screen` with `width: 2560`.

## 3. Translating Stitch HTML into Astro / EmDash Safely

Stitch outputs static HTML + Tailwind/CSS tokens. When applying the winning candidate to an EmDash site:

- **Token & CSS Extraction:** Map Stitch's palette, font pairings, border radii, and surface elevation into CSS custom properties on the site's root stylesheet or `store-shell` theme tokens.
- **Preserve Authority Boundaries:**
  - Never hardcode Stitch sample copy, prices, or stock numbers into `.astro` templates.
  - CMS-authored fields (`hero`, `merchandise` entries, `layout` blocks, `QueryCard`) must still render from live EmDash data.
  - Commerce `Regular`/`Sale` prices and Inventory `8 -> 5 -> 8` or unmanaged availability states must still read from their runtime resolvers.
- **Preserve `FEATURE_MAP.md` Selectors:**
  - Verify every `data-*` attribute (`data-collection-nav`, `data-merch-catalog`, `data-managed-product`, `data-unmanaged-product`, `data-commerce-sku`, `data-inventory-sku`, `data-stock-value`, `data-stock-version`, `data-availability-status`, `data-sellable`, `data-quantity-shown`, `data-regular-price`, `data-sale-price`) remains attached to the exact semantic element expected by Playwright acceptance tests.
  - Keep `<details>` / `<summary>` keyboard-operable and ensure focus rings and contrast pass on both desktop and mobile viewports with zero horizontal overflow.

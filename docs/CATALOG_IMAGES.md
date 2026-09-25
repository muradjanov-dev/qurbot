# Storefront catalogue photos

The 393 active products observed on 2026-09-25 are grouped by material or
fastener type in `app/domain/catalog_images.py`. Dimension and brand variants
share a representative image; these photos do not claim to show the exact SKU.

The optimized WebP files live in `app/web/storefront/static/images/` and ship in
the web image. `credits.json` records each original, author and license and is
shown at `/image-credits`. Copies were resized to at most 960 × 720 pixels and
converted to WebP. The original source pages link to the applicable license.

`/media/product/{id}` serves an approved owner photo first, then an admin-uploaded
local photo, then the family image. Unknown future product types get the neutral
`no-photo.svg` until a suitable licensed image is added. Update the classifier,
asset, credits and coverage fixture together when extending the catalogue.

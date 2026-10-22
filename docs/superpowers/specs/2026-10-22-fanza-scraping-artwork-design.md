# FANZA scraping source and distinct artwork

## Intent

Scraping a stored movie should produce useful metadata and artwork. The current
image files can show the same picture at different resolutions, as reported for
MIDA-819. Add FANZA as a selectable metadata source and avoid saving visually
duplicate artwork into different slots.

## Current behavior and reference

- Media Forge maps `movie.cover` to `folder.jpg` and the first two preview URLs
  from a fetched JavDB/JavBus detail page to `backdrop.jpg` and `landscape.jpg`.
  It does not check whether those images show the same scene. It only fetches
  source metadata when database fields are missing, so a complete movie row
  receives no new preview images. The nfo always references `backdrop.jpg`.
- The local `metatube-sdk-go` FANZA provider searches identifiers, verifies
  results, and reads digital detail data from FANZA GraphQL or DVD detail HTML.
  Digital data exposes package image sizes and sample images separately. Its
  image engine may derive primary, thumb and backdrop images from the same cover
  URL with different crops; those outputs are not necessarily distinct scenes.
  The provider also detects when the first sample is a larger version of the
  package image and excludes that sample from the preview list.

## Approaches

1. **Chosen:** Add FANZA to the existing ordered source list. Implement a
   Media Forge source adapter that finds an exact code match, reads FANZA detail
   fields, and returns cover and preview image URLs. Independently fetch artwork
   candidates for each scrape task, then select distinct images for each slot.
   This keeps source selection and task provenance visible in the current UI.
2. Use FANZA only as a supplemental image source. This is a smaller UI change,
   but combines metadata from one site with untracked images from another and
   gives users no way to prioritize FANZA metadata.

## Behavior

- Show FANZA in the existing source priority control, disabled for existing
  configurations unless the user enables it. New configurations may keep the
  current JavDB/JavBus defaults. Persist and validate `fanza` in the existing
  source list; no new source-specific settings are required.
- Use code search plus an exact normalized product-number check before using a
  FANZA result. Resolve its canonical content ID and detail URL. Read digital
  GraphQL data where available and DVD HTML for DVD results, following the local
  Go provider's field mapping. Require a credible match; network errors, empty
  data, regional blocks and parse changes fall through to the next configured
  source. Do not overwrite populated movie database fields.
- Fetch artwork candidates even when the movie already has complete database
  metadata. Preserve the current cover unless absent; select distinct preview
  images for backdrop and landscape. Compare actual decoded image content so
  differently sized versions of one picture are treated as duplicates. Do not
  reuse a cover-like FANZA sample as a backdrop. If fewer distinct scenes exist,
  write only the available slots and make nfo art references match files that
  exist. On a rerun, replace a generated slot only after a successful download;
  remove an old slot only when it is proven visually duplicate to another saved
  slot, and leave other existing files intact.
- Keep image size and type limits, request timeouts, atomic writes and site
  referer handling. Use the existing task status and source fields. Record
  enough diagnostic information in logs to distinguish no match, blocked
  source, unavailable image and duplicate image without logging secrets.

## Scope and verification

Touch the scraping source adapter, artwork selection, item runner, nfo output,
source priority UI and focused tests. Update `frontend/README.md` only if its
documented source behavior changes. Test exact and false code matches, digital
and DVD mapping, source fallback, complete movie rows, visually identical
images at different sizes, partial downloads, existing files, and nfo paths.
Run focused backend tests, frontend tests and build. A live FANZA sample from
this host is useful to validate site access but is not a substitute for parser
fixtures; site availability may vary by region or time.

## Non-goals and limits

No new movie fields, source accounts, broad crawler changes, image upscaling,
or direct runtime dependency on the Go SDK. This design cannot guarantee three
different pictures for a title that has fewer than three available scenes.

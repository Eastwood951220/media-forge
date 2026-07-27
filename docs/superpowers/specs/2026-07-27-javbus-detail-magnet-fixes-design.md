# JavBus Detail Magnet Fixes Design

## Reproduced Root Causes

1. **Code field captured the label text.** The real JavBus detail page places the identification code (`CEMD-869`) in a `<span style="color:#CC0000;">` sibling, not as direct text after the `識別碼:` label. The old parser read the label itself as the code value.

2. **Tags and actors used wrong DOM structure.** Real markup puts genre tags in a separate `<p>` after the `類別` header `<p>`, and actors in `#star-div .avatar-box > span`. The old parser expected them inline in the same `<p>` as the header.

3. **Ajax request lacked context.** The spider sent Ajax requests without the detail page's Referer, XHR headers, or response cookies. JavBus requires these for the magnet endpoint to return results.

## Design Decision: Per-Request Override vs Persistent Session

**Chosen:** Stateless per-request header/cookie merge in `ScraplingFetcher.get()`.

**Why not persistent session:** The fetcher is shared across spiders (JavDB, JavBus). Session-level cookies would leak context between unrelated requests and create ordering dependencies.

**Why not browser automation:** The existing Scrapling static fetcher is sufficient for JavBus's server-rendered HTML. Browser automation adds latency and complexity without benefit for this use case.

The merge is `{**self.headers, **(headers or {})}` — caller overrides win, instance defaults are never mutated.

## Alert Bar Name Extraction Rule

JavBus list/star pages show a header like:

```
波多野結衣 - 女優 - 影片
```

The rule: split on ` - `, take the first segment. Applied via `parse_javbus_url_name()`. The spider's `extract_url_name()` routes to this for non-detail URLs.

## Ajax Request Data Flow

```
detail page → extract_ajax_params (gid, uc, img)
            → _response_cookies (normalize page.cookies to dict)
            → build ajax_url with urlencode(gid, lang=zh, img, uc, floor=randint(1,1000))
            → fetch ajax_url with:
                headers: {Accept: */*, Referer: <detail_url>, X-Requested-With: XMLHttpRequest}
                cookies: {**detail_response_cookies, existmag: mag}
            → parse_magnet_ajax → magnets list
```

## Zero Magnets vs Failure Boundary

- Ajax request fails (network/parse error) → detail status = `failed`, reason includes error.
- Ajax succeeds but returns zero `<tr>` rows → detail status = `completed`, magnets = `[]`.
- Missing `gid`/`uc`/`img` params → detail status = `failed`, reason lists missing keys.

## Real Fixture Acceptance Assertions

| Assertion | Source |
|-----------|--------|
| `code == "CEMD-869"` (not `識別碼:`) | Real detail HTML fixture |
| `tags == ["成熟的女人", "高畫質"]` | Real detail HTML, separate `<p>` structure |
| `actors == ["波多野結衣"]` | Real detail HTML, `#star-div` structure |
| `cover_url` is absolute | `urljoin(source_url, relative_path)` |
| `date == "2026-07-21"` in magnet row | Real magnet HTML, `<a>` inside `<td>` |
| 7 magnets parsed from fixture | Seven `<tr>` fixture in spider test |
| `floor` is random, not fixed `735` | `randint(1, 1000)` |
| Ajax cookies include detail response | `_response_cookies(page)` merged with `existmag=mag` |

## Sensitive Data Exclusion

No Cookie values, PHPSESSID, or full request headers are logged or persisted. The `_response_cookies` helper is purely in-memory for the duration of a single detail task.

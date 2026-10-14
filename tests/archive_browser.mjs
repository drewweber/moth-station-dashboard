// Run with Node and Playwright installed. PLAYWRIGHT_MODULE may name an absolute
// module path; PLAYWRIGHT_CHANNEL defaults to chrome for local verification.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const fixture = spawnSync("python3", ["-c", `
import json
from mothdash.render import _archive_page, DASHBOARD_JS
rows = [{"label": f"Species {i:04d}", "station_name": "Alpha" if i < 100 else "Beta", "station_id": "alpha" if i < 100 else "beta", "first": f"2026-07-{i % 28 + 1:02d}", "flags": ["county iNat first" if i < 210 else "state iNat first"], "url": f"https://example.test/observations/{i}", "photo_url": None} for i in range(225)]
from mothdash.config import Station
stations = [Station(id=id, name=id.title(), enabled=True, active=True, query={}) for id in ("alpha", "beta")]
page = _archive_page(year=2026, pulses=[], all_time_pulses=[], year_calendar=[], all_time_calendar=[], records=rows, uniques=[], taxa=[], year_taxa=[], recent_week_taxa=[], latest_night_taxa=[], stations=stations)
print(json.dumps({"html": page, "js": DASHBOARD_JS, "records": rows}))
`], { encoding: "utf8" });
assert.equal(fixture.status, 0, fixture.stderr);
const assets = JSON.parse(fixture.stdout);
const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || "chrome", headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  let recordRequests = 0;
  let failNextRequest = false;
  page.on("pageerror", error => errors.push(error.message));
  await page.route("https://archive.test/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("dashboard.js")) return route.fulfill({ contentType: "text/javascript", body: assets.js });
    if (path.endsWith("archive-records.json")) {
      recordRequests += 1;
      if (failNextRequest) {
        failNextRequest = false;
        return route.fulfill({ status: 503, body: "temporarily unavailable" });
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(assets.records) });
    }
    if (path.endsWith(".css")) return route.fulfill({ body: "" });
    return route.fulfill({ contentType: "text/html", body: assets.html });
  });
  const rowCount = () => page.locator("[data-record-table] tbody tr").count();
  const status = () => page.locator("[data-record-count]").innerText();
  const settle = () => page.waitForFunction(() => !document.querySelector("#archive-records").hasAttribute("aria-busy"));
  await page.goto("https://archive.test/archive.html");
  assert.equal(await rowCount(), 100, "initial table must be bounded before interaction");
  assert.equal(recordRequests, 0, "full record data must not be requested on initial load");
  const expandPhotos = page.locator("[data-record-grid-expand]");
  assert.equal(await expandPhotos.getAttribute("aria-expanded"), "false");
  const controlledGrid = await expandPhotos.getAttribute("aria-controls");
  assert.equal(controlledGrid, await page.locator("[data-record-grid]").getAttribute("id"));
  assert.ok(controlledGrid, "photo expansion must identify the controlled grid");

  // Sorting must search the complete data, including records beyond the preview.
  await page.getByRole("button", { name: "Species", exact: true }).click();
  await settle();
  await page.getByRole("button", { name: "Species", exact: true }).click();
  await settle();
  assert.match(await page.locator("[data-record-table] tbody tr").first().innerText(), /Species 0224/);
  assert.equal(await rowCount(), 100);
  assert.equal(recordRequests, 1);

  await page.locator('[data-record-filter="location"]').selectOption("beta");
  await settle();
  assert.equal(await rowCount(), 100);
  assert.match(await status(), /100 of 125 matching records/);
  await page.locator("[data-record-show-more]").click();
  await settle();
  assert.equal(await rowCount(), 125);
  await page.locator('[data-record-filter="type"]').selectOption("state iNat first");
  await settle();
  assert.equal(await rowCount(), 15);
  assert.equal(await page.locator("[data-record-grid] .record-card").count(), 12);
  await page.locator("[data-record-grid-expand]").click();
  assert.equal(await page.locator("[data-record-grid] .record-card").count(), 15);
  assert.equal(await expandPhotos.getAttribute("aria-expanded"), "true");

  await page.locator('[data-record-filter="location"]').selectOption("alpha");
  await settle();
  assert.equal(await rowCount(), 0);
  assert.equal(await expandPhotos.getAttribute("aria-expanded"), "false");
  assert.equal(await page.locator("[data-record-empty]").isVisible(), true);
  await page.locator('[data-record-filter="type"]').selectOption("");
  await page.locator('[data-record-filter="location"]').selectOption("");
  await settle();
  assert.equal(await rowCount(), 100);
  assert.equal(await page.locator("[data-record-empty]").isVisible(), false);
  await page.locator("[data-record-show-more]").click();
  await settle();
  assert.equal(await rowCount(), 200);
  await page.locator("[data-record-show-more]").click();
  await settle();
  assert.equal(await rowCount(), 225);
  assert.equal(await page.locator("[data-record-show-more]").isVisible(), false);
  assert.equal(recordRequests, 1, "loaded records must be reused");

  // Failed requests retain the usable preview and expose a retry.
  await page.reload();
  failNextRequest = true;
  await page.locator('[data-record-filter="location"]').selectOption("beta");
  await page.waitForSelector("[data-record-error]:not([hidden])");
  assert.equal(await page.locator("[data-record-error]").getAttribute("role"), "status");
  assert.equal(await page.getByRole("button", { name: "Retry loading records" }).isVisible(), true);
  assert.equal(await rowCount(), 100);
  await page.locator("[data-record-retry]").click();
  await settle();
  assert.equal(await rowCount(), 100);
  assert.match(await status(), /100 of 125 matching records/);
  assert.equal(await page.locator("[data-record-error]").isVisible(), false);
  assert.deepEqual(errors, []);
  console.log("PASS: bounded initial archive, full-data sorting/filtering/pagination, photos, empty state, load failure and retry");
} finally {
  await browser.close();
}

// Capture the IPMG Web screenshots used in the README from the seeded demo.
// See docs/record-demo.md for the exact commands; in short, from the
// repository root, with the static files served on port 4173:
//
//   NODE_PATH="$TOOLS/node_modules" node docs/demo/screenshots.cjs
//
// The demo (?demo=1) uses the browser-only data in js/demo.js, so no scan,
// server, or real network is involved. Files are written relative to the
// current directory.

const { chromium } = require("playwright");

const BASE = process.env.IPMG_DEMO_URL || "http://127.0.0.1:4173/?demo=1";

const SHOTS = [
  { route: "#/", file: "docs/assets/ipmg-web.png", ready: ".card.tile" },
  // #/changes/TARGET/BASELINE: yesterday's scan (#23) against today's (#24).
  { route: "#/changes/24/23", file: "docs/assets/ipmg-changes.png", ready: "table tbody tr" },
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1440, height: 720 },
    colorScheme: "dark",
  });

  for (const shot of SHOTS) {
    await page.goto(`${BASE}${shot.route}`);
    await page.waitForSelector(shot.ready);
    await page.waitForTimeout(500); // let the charts finish drawing
    await page.screenshot({ path: shot.file });
    console.log(`wrote ${shot.file}`);
  }

  await browser.close();
})();

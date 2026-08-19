// One-off screenshot script for reviewing the login page redesign.
// Not part of the app build — run manually: node scripts/screenshot-login.js
const puppeteer = require("puppeteer");
const path = require("path");

const BASE_URL = process.env.SCREENSHOT_BASE_URL || "http://localhost:3000";
const OUT_DIR =
  process.env.SCREENSHOT_OUT_DIR ||
  "/private/tmp/claude-501/-Users-sushil-Documents-ClaudeProjects-BD-Console/b47a3384-5ebd-437d-ba9f-479316f53020/scratchpad/screenshots";

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "desktop", width: 1440, height: 900 },
];

async function main() {
  const fs = require("fs");
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await puppeteer.launch({ headless: "new" });
  try {
    for (const vp of VIEWPORTS) {
      const page = await browser.newPage();
      await page.setViewport({ width: vp.width, height: vp.height });
      await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle0" });

      // Picker state (role not yet chosen)
      await page.screenshot({ path: path.join(OUT_DIR, `login-${vp.name}-picker.png`) });

      // Menu open (role dropdown expanded, nothing picked yet)
      await page.click('button[aria-haspopup="menu"]');
      await page.waitForSelector('[role="menu"]');
      await page.screenshot({ path: path.join(OUT_DIR, `login-${vp.name}-menu-open.png`) });

      // Pick "Customer" to reveal the full form
      const items = await page.$$('[role="menuitem"]');
      await items[0].click();
      await page.waitForSelector('input[name="phone"]');
      await page.screenshot({ path: path.join(OUT_DIR, `login-${vp.name}-form.png`) });

      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log(`Screenshots written to ${OUT_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

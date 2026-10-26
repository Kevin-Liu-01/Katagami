// Draws the website's stills (public/stills/ in the site checkout): pictures a page
// shows in place of a live frame until the reader asks for one, so the first frame
// already has them. Serve the built site at BASE first (pnpm build && pnpm start).
// Needs playwright-core, Chrome and cwebp; set KATAGAMI_PLAYWRIGHT and CHROME as for og.mjs.
//
//   fontify-before.webp, fontify-katagami.webp
//       the landing page's Font-ify cell: fontify-sample.html in its own fonts and
//       converted to Katagami by the same katagami-apply.js and fontify.js the cell
//       runs, 1280 px wide at 1.5x
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = process.env.KATAGAMI_SITE || path.resolve(ROOT, "../Katagami-Website");
const OUT = path.join(SITE, "public", "stills");
const BASE = process.env.BASE || "http://localhost:3078";
const PW = process.env.KATAGAMI_PLAYWRIGHT || "/Users/kevinliu/repos/Prototemplate/node_modules/playwright-core/index.mjs";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const { chromium } = await import(PW);

fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: CHROME });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 1.5 });

// a still as WebP: the screenshot's PNG through cwebp, at a quality text stays sharp at
const save = (png, name) => {
  const tmp = path.join(OUT, `${name}.png`);
  fs.writeFileSync(tmp, png);
  execFileSync("cwebp", ["-quiet", "-q", "86", "-m", "6", tmp, "-o", path.join(OUT, `${name}.webp`)]);
  fs.unlinkSync(tmp);
  console.log(`${name}.webp ${(fs.statSync(path.join(OUT, `${name}.webp`)).size / 1024).toFixed(1)} KB`);
};
const shoot = async (name) => {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const height = await page.evaluate(() => Math.min(1400, document.documentElement.scrollHeight));
  save(await page.screenshot({ clip: { x: 0, y: 0, width: 1280, height }, type: "png" }), name);
};

// the sample in its own fonts, as the cell's first frame shows it
await page.goto(`${BASE}/fontify-sample.html`, { waitUntil: "networkidle" });
await shoot("fontify-before");

// the sample in Katagami: the cell's own conversion, written into this page
await page.goto(`${BASE}/convert`, { waitUntil: "networkidle" });
const doc = await page.evaluate(async () => {
  const base = new URL("/fontify-sample.html", location.href).href;
  const html = await (await fetch(base)).text();
  await window.Fontify.ready;
  const F = window.Fontify, K = window.KatagamiConvert;
  return F.previewDoc(K.rewriteHTML(html, { sans: "sans", base, sheets: new Map(), fontBase: F.FONTS, fontURL: null }).doc, true, "sans");
});
await page.setContent(doc, { waitUntil: "networkidle" });
await shoot("fontify-katagami");

await browser.close();

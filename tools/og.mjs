// Draws the Open Graph card for every entry in build/og.json into the site's
// og/ folder, 1200 by 630, set in Katagami from the site's own web fonts.
// Run after tools/build_seo.py. Needs playwright-core and Chrome; set
// KATAGAMI_PLAYWRIGHT to playwright-core's index.mjs and CHROME to the browser.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = process.env.KATAGAMI_SITE || path.resolve(ROOT, "../Katagami-Website");
// a Next app serves the site's files from public/
const PUB = fs.existsSync(path.join(SITE, "next.config.ts")) ? path.join(SITE, "public") : SITE;
const PW = process.env.KATAGAMI_PLAYWRIGHT || "/Users/kevinliu/repos/Prototemplate/node_modules/playwright-core/index.mjs";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const { chromium } = await import(PW);

const cards = JSON.parse(fs.readFileSync(path.join(ROOT, "build/og.json"), "utf8"));
const font = (file) => `url("file://${path.join(PUB, "fonts", file)}")`;
const FACES = { sans: "KatagamiSans.woff2", round: "KatagamiRound.woff2", text: "KatagamiText.woff2", serif: "KatagamiSerif.woff2", mono: "KatagamiMono.woff2" };
const faces = Object.entries(FACES).map(([k, f]) => `@font-face{font-family:"K-${k}";src:${font(f)};font-weight:100 900}`).join("\n");
const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
// blue for the pages about facts and coverage, red for the rest
const BLUE = new Set(["map", "glyphs", "compare", "script", "language", "features"]);

const out = path.join(PUB, "og");
const tmp = path.join(ROOT, "build", "og-card.html");
fs.mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: CHROME });
const page = await b.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
for (const c of cards) {
  const face = `K-${c.member || "sans"}`;
  const accent = BLUE.has(c.slug) ? "#2457c5" : "#d92d20";
  const html = `<!doctype html><meta charset="utf-8"><style>${faces}
  html,body{margin:0;width:1200px;height:630px;background:#f1f2ef;color:#111214;font-family:"K-sans"}
  .card{position:relative;width:1200px;height:630px;display:grid;grid-template-rows:auto 1fr auto}
  .top{display:flex;align-items:center;gap:14px;padding:44px 64px 0;font-size:30px;font-weight:650;letter-spacing:-0.01em}
  .top svg{width:26px;height:26px;fill:#111214}
  .main{display:grid;align-content:center;gap:18px;padding:0 64px}
  h1{margin:0;font-family:"${face}";font-size:${c.title.length > 16 ? 104 : 128}px;line-height:0.95;letter-spacing:-0.035em;font-weight:650}
  p{margin:0;max-width:980px;font-size:34px;line-height:1.25;color:#5d6165}
  .bar{display:flex;justify-content:space-between;align-items:center;height:96px;padding:0 64px;background:${accent};color:#fff;font-family:"K-mono";font-size:24px}
  </style><div class="card"><div class="top"><svg viewBox="0 0 100 100"><path d="M0 0 L31 0 L31 100 L0 100 Z"/><path d="M38 0 L100 0 L100 30 L38 50 Z"/><path d="M38 50 L100 70 L100 100 L38 100 Z"/></svg>Katagami</div>
  <div class="main"><h1>${esc(c.title)}</h1>${c.subtitle ? `<p>${esc(c.subtitle[0].toUpperCase() + c.subtitle.slice(1))}</p>` : ""}</div>
  <div class="bar"><span>katagami.kevinliu.studio</span><span>Free, SIL Open Font License</span></div></div>`;
  // a page opened from disk may load the fonts from disk; a set-content page may not
  fs.writeFileSync(tmp, html);
  await page.goto(`file://${tmp}`);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(out, `${c.slug}.png`) });
}
await b.close();
console.log(`${cards.length} cards in ${out}`);

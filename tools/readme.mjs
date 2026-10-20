// Draws the README images of this repository (docs/readme/) and of the website
// (readme/ in the site checkout), each in a light and a dark version, from the
// site's web fonts. Serve the site checkout at BASE first (any static server).
// Needs playwright-core and Chrome; set KATAGAMI_PLAYWRIGHT and CHROME as for og.mjs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = process.env.KATAGAMI_SITE || path.resolve(ROOT, "../Katagami-Website");
// a Next app serves the site's files from public/
const PUB = fs.existsSync(path.join(SITE, "next.config.ts")) ? path.join(SITE, "public") : SITE;
const BASE = process.env.BASE || "http://localhost:3077";
const PW = process.env.KATAGAMI_PLAYWRIGHT || "/Users/kevinliu/repos/Prototemplate/node_modules/playwright-core/index.mjs";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const { chromium } = await import(PW);

const OUT = path.join(ROOT, "docs/readme"), SITE_OUT = path.join(SITE, "readme");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(SITE_OUT, { recursive: true });
const data = JSON.parse(fs.readFileSync(path.join(PUB, "data.js"), "utf8").replace(/^[^{]*/, "").replace(/;?\s*$/, ""));
const fmt = (n) => n.toLocaleString("en-US");

const THEMES = {
  light: { sheet: "#f1f2ef", panel: "#f8f8f6", ink: "#111214", ink2: "#5d6165", cut: "#d92d20", score: "#2457c5", soft: "#e6e8e3" },
  dark: { sheet: "#0e0f10", panel: "#151618", ink: "#ebece9", ink2: "#9a9ea2", cut: "#ff5246", score: "#6c94ff", soft: "#1f2124" },
};
const MEMBERS = [["sans", "Katagami Sans"], ["round", "Katagami Round"], ["text", "Katagami Text"], ["serif", "Katagami Serif"], ["mono", "Katagami Mono"]];
const range = (k) => (k === "mono" ? "100 to 700" : "100 to 900");

const page = (t, body, css = "") => `<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/fonts/katagami.css"><style>
html,body{margin:0;background:${t.panel};color:${t.ink};font-family:"Katagami Sans";-webkit-font-smoothing:antialiased}
.card{width:1000px;box-sizing:border-box;padding:40px 44px;background:${t.panel}}
.tag{font-family:"Katagami Mono";font-size:13px;color:${t.ink2};letter-spacing:0}
.cap{font-size:15px;line-height:1.4;color:${t.ink2}}
${css}</style><div class="card">${body}</div>`;

const CARDS = {
  members: (t) => page(t, MEMBERS.map(([k, name]) => `<div class="row"><div class="tag">${name}<br>${range(k)}<br>${fmt(data[k].metrics.glyphs)} glyphs</div>
    <div class="s" style="font-family:'${name}';${k === "mono" ? "font-feature-settings:'dlig'" : ""}">${{
      sans: "Squared bowls and level cuts", round: "Every corner rounded at 0.22 stems", text: "A lower x-height for long reading",
      serif: "Rectangular serifs, light contrast", mono: "0O 1lI {} => != -> fn(x)" }[k]}</div></div>`).join(""),
    `.row{display:grid;grid-template-columns:150px 1fr;align-items:center;gap:24px;padding:16px 0}.row+.row{border-top:1px solid ${t.soft}}
     .s{font-size:40px;line-height:1.1;letter-spacing:-0.01em;white-space:nowrap}`),

  weights: (t) => page(t, `<div class="grid"><div></div>${MEMBERS.map(([, n]) => `<div class="tag">${n.replace("Katagami ", "")}</div>`).join("")}
    ${[100, 200, 300, 400, 500, 600, 700, 800, 900].map((w) => `<div class="tag">${w}</div>${MEMBERS.map(([k, n]) =>
      `<div class="w" style="font-family:'${n}';font-weight:${w}">${k === "mono" && w > 700 ? "" : "Rag"}</div>`).join("")}`).join("")}</div>`,
    `.grid{display:grid;grid-template-columns:60px repeat(5,1fr);align-items:center;row-gap:2px}.w{font-size:44px;line-height:1.15}`),

  details: (t) => page(t, `<div class="tiles">
    <div><div class="g" style="font-family:'Katagami Sans';font-size:84px">cesag</div><p class="cap">c, e, s, a and g end in level cuts.</p></div>
    <div><div class="g" style="font-family:'Katagami Sans'"><span style="font-weight:100">f</span><span style="font-weight:400">f</span><span style="font-weight:900">f</span></div><p class="cap">The f's crossbar reaches the same distance past its stem at every weight.</p></div>
    <div><div class="g" style="font-family:'Katagami Sans'">g</div><p class="cap">The g's tail mirrors its bowl and ends in a level cut.</p></div>
    <div><div class="g" style="font-family:'Katagami Serif'">nE</div><p class="cap">Katagami Serif's serifs end square and meet each stroke in a short bracket.</p></div>
    <div><div class="g" style="font-weight:900"><span style="font-family:'Katagami Sans'">N</span><span style="font-family:'Katagami Round'">N</span></div><p class="cap">Katagami Round, right, rounds every corner that Sans keeps sharp.</p></div>
    <div><div class="g" style="font-family:'Katagami Mono';font-size:80px">0O1lI</div><p class="cap">Katagami Mono draws 0 and O, and 1, l and I, apart.</p></div></div>`,
    `.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.tiles>div{background:${t.sheet};padding:22px 24px 18px;border-radius:8px;overflow:hidden}
     .g{font-size:120px;line-height:1.05;letter-spacing:-0.02em;height:140px;display:flex;align-items:center;gap:12px;white-space:nowrap}.cap{margin:10px 0 0}`),

  scripts: (t) => page(t, `<div class="sc">${[
    ["Latin", "Français"], ["Greek", "Ελληνικά"], ["Cyrillic", "Русский"], ["Arabic", "العربية"], ["Hebrew", "עברית"], ["Devanagari", "हिन्दी"],
    ["Bengali", "বাংলা"], ["Gurmukhi", "ਪੰਜਾਬੀ"], ["Gujarati", "ગુજરાતી"], ["Odia", "ଓଡ଼ିଆ"], ["Tamil", "தமிழ்"], ["Telugu", "తెలుగు"],
    ["Kannada", "ಕನ್ನಡ"], ["Malayalam", "മലയാളം"], ["Sinhala", "සිංහල"], ["Thai", "ภาษาไทย"], ["Lao", "ພາສາລາວ"], ["Myanmar", "မြန်မာ"],
    ["Khmer", "ខ្មែរ"], ["Georgian", "ქართული"], ["Armenian", "Հայերեն"], ["Ethiopic", "አማርኛ"], ["CJK SC", "简体中文"], ["CJK TC", "繁體中文"],
    ["CJK JP", "日本語"], ["CJK KR", "한국어"]].map(([s, w]) => `<div><div class="tag">${s}</div><div class="x">${w}</div></div>`).join("")}</div>`,
    `.sc{display:grid;grid-template-columns:repeat(4,1fr);gap:14px 20px}.sc>div{padding:6px 0}.x{font-size:34px;line-height:1.4;white-space:nowrap}`),

  features: (t) => page(t, `<div class="ft"><div></div><div class="tag">Off</div><div class="tag">On</div>${[
    ["frac", "Fractions", "1/2 3/4 7/8", "Katagami Sans"], ["smcp", "Small capitals", "Pattern Paper", "Katagami Sans"],
    ["zero", "Slashed zero", "0 O 2050", "Katagami Sans"], ["cv11", "Single-story a", "katagami", "Katagami Sans"],
    ["ss02", "Disambiguation", "Il1 0O", "Katagami Sans"], ["ss05", "Circled characters", "1 2 3 A", "Katagami Sans"],
    ["sinf", "Scientific inferiors", "H2O CO2", "Katagami Sans"], ["dlig", "Code ligatures", "=> != -> >=", "Katagami Mono"]].map(([tag, label, s, fam]) =>
      `<div><div class="tag">${tag}</div><div class="l">${label}</div></div><div class="o" style="font-family:'${fam}'">${s}</div><div class="n" style="font-family:'${fam}';font-feature-settings:'${tag}'">${s}</div>`).join("")}</div>`,
    `.ft{display:grid;grid-template-columns:220px 1fr 1fr;align-items:center;gap:10px 28px}.l{font-size:16px;margin-top:2px}
     .o,.n{font-size:38px;line-height:1.3;white-space:nowrap}.o{color:${t.ink2}}`),
};

const b = await chromium.launch({ executablePath: CHROME });
const shrink = [];
for (const [scheme, t] of Object.entries(THEMES)) {
  const ctx = await b.newContext({ viewport: { width: 1000, height: 2400 }, deviceScaleFactor: 2, colorScheme: scheme });
  const p = await ctx.newPage();
  p.setDefaultTimeout(90000);
  for (const [name, card] of Object.entries(CARDS)) {
    const html = card(t);
    await p.route(`${BASE}/__readme`, (r) => r.fulfill({ contentType: "text/html", body: html }));
    await p.goto(`${BASE}/__readme`, { waitUntil: "networkidle" });
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(300);
    const file = path.join(OUT, `${name}-${scheme}.png`);
    // a clipped page shot; an element shot waits for the element to stop moving while fonts load
    const box = await p.locator(".card").boundingBox();
    await p.screenshot({ path: file, clip: box });
    await p.unroute(`${BASE}/__readme`);
    shrink.push(file);
  }
  // the site itself: the hero drawing and the map for this repository, the pages for the site's
  const site = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: scheme });
  const s = await site.newPage();
  s.setDefaultTimeout(90000);
  await s.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await s.waitForTimeout(800);
  await s.screenshot({ path: path.join(OUT, `hero-${scheme}.png`), clip: await s.locator("#hero").boundingBox() });
  shrink.push(path.join(OUT, `hero-${scheme}.png`));
  await s.goto(`${BASE}/map`, { waitUntil: "networkidle" });
  await s.getByRole("button", { name: "World", exact: true }).click();
  await s.waitForTimeout(5000);
  await s.screenshot({ path: path.join(OUT, `map-${scheme}.png`), clip: await s.locator("#map").boundingBox() });
  shrink.push(path.join(OUT, `map-${scheme}.png`));
  const one = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme: scheme });
  const q = await one.newPage();
  // ONLY=fonts redraws this repository's images and leaves the site's
  if (process.env.ONLY === "fonts") { await ctx.close(); await site.close(); await one.close(); continue; }
  q.setDefaultTimeout(90000);
  for (const [route, name] of [["/", "home"], ["/glyphs", "glyphs"], ["/features", "features"], ["/map", "map"], ["/convert", "convert"],
    ["/about", "about"], ["/faq", "faq"], ["/download", "download"], ["/katagami-serif", "library"]]) {
    await q.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
    await q.waitForTimeout(route === "/map" ? 4000 : 1200);
    const file = path.join(SITE_OUT, `${name}-${scheme}.png`);
    await q.screenshot({ path: file });
    shrink.push(file);
  }
  await ctx.close(); await site.close(); await one.close();
}
await b.close();
fs.writeFileSync(path.join(ROOT, "build/readme-shrink.json"), JSON.stringify(shrink));
console.log(`${shrink.length} images; shrink them with tools/readme_shrink.py`);

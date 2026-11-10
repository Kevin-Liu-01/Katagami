// Where the website checkout is, for the tools that write into it: KATAGAMI_SITE, or the
// folder beside this repository. A folder that is not a Katagami-Website checkout stops the
// run, so a git worktree or a mistyped KATAGAMI_SITE never gets a new tree written into it.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const SITE = process.env.KATAGAMI_SITE || path.resolve(ROOT, "../Katagami-Website");
const missing = ["next.config.ts", "content", "public"].filter((name) => !fs.existsSync(path.join(SITE, name)));
if (missing.length) {
  console.error(`${SITE} is not a Katagami-Website checkout. It has no ${missing.join(", ")}. Set KATAGAMI_SITE to the checkout this run should write into.`);
  process.exit(1);
}
export const PUB = path.join(SITE, "public");

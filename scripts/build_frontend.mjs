/**
 * Bundle src/app.ts to static/app.js.
 *
 * The page is an IIFE so index.html can keep a plain script tag. The
 * sourcemap sits beside the bundle. --check rebuilds in place and exits
 * non-zero when the committed bundle or map differs. esbuild is pinned
 * in package.json so the bytes stay the same on Ubuntu and Windows.
 */

import esbuild from "esbuild";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outfile = join(root, "static", "app.js");
const mapfile = `${outfile}.map`;
const check = process.argv.includes("--check");

const beforeJs = check ? readFileSync(outfile) : null;
const beforeMap = check ? readFileSync(mapfile) : null;

await esbuild.build({
  absWorkingDir: root,
  entryPoints: ["src/app.ts"],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2022",
  outfile: "static/app.js",
  sourcemap: true,
  sourcesContent: true,
  legalComments: "none",
  charset: "utf8",
  logLevel: "warning",
});

const map = JSON.parse(readFileSync(mapfile, "utf8"));
const sources = Array.isArray(map.sources) ? map.sources : [];
if (!sources.length) {
  console.error("static/app.js.map has no sources");
  process.exit(1);
}
for (const source of sources) {
  if (typeof source !== "string" || source.includes("\\") || source.startsWith("/") || /^[A-Za-z]:/.test(source)) {
    console.error(`static/app.js.map source is not a relative forward-slash path: ${source}`);
    process.exit(1);
  }
}

if (!check) {
  console.log(`Wrote ${relative(root, outfile)} and ${relative(root, mapfile)}`);
  process.exit(0);
}

const afterJs = readFileSync(outfile);
const afterMap = readFileSync(mapfile);
if (!beforeJs.equals(afterJs) || !beforeMap.equals(afterMap)) {
  console.error("static/app.js is stale. Run npm run build and commit static/app.js and static/app.js.map.");
  process.exit(1);
}

const expectedExpectError = 0;
let expectError = 0;

function countExpectErrors(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      countExpectErrors(full);
      continue;
    }
    if (!name.endsWith(".ts")) continue;
    const text = readFileSync(full, "utf8");
    expectError += (text.match(/@ts-expect-error/g) || []).length;
    if (text.includes("@ts-nocheck") || text.includes("@ts-ignore")) {
      console.error(`${full} uses @ts-nocheck or @ts-ignore. Strict checking stays on.`);
      process.exit(1);
    }
  }
}

countExpectErrors(join(root, "src"));
if (expectError !== expectedExpectError) {
  console.error(`@ts-expect-error count is ${expectError}; the tracked count is ${expectedExpectError}.`);
  process.exit(1);
}

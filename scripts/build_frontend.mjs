/**
 * Bundle the page and the first-run wizard.
 *
 * Both outputs are IIFEs so index.html can keep plain script tags. The
 * sourcemap sits beside each bundle. --check builds in memory with
 * write:false and exits non-zero when a committed bundle or map differs.
 * It does not write static/. esbuild is pinned in package.json so the
 * bytes stay the same on Ubuntu and Windows.
 */

import esbuild from "esbuild";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const check = process.argv.includes("--check");

const bundles = [
  { entry: "src/app.ts", outfile: "static/app.js" },
  { entry: "src/wizard-view.ts", outfile: "static/wizard.js", globalName: "SeratoWizard" },
];

/**
 * Build one entry.
 *
 * @param {{ entry: string, outfile: string, globalName?: string }} bundle
 * @param {boolean} write True writes the bundle and map under static/.
 * @returns {Promise<import("esbuild").BuildResult>}
 */
function buildOne(bundle, write) {
  return esbuild.build({
    absWorkingDir: root,
    entryPoints: [bundle.entry],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    outfile: bundle.outfile,
    globalName: bundle.globalName,
    sourcemap: true,
    sourcesContent: true,
    legalComments: "none",
    charset: "utf8",
    logLevel: "warning",
    write,
  });
}

/**
 * Reject a sourcemap whose sources are not relative forward-slash paths.
 *
 * @param {string} outfile Bundle path used in the error.
 * @param {string} text Sourcemap JSON.
 * @returns {void}
 */
function checkMapSources(outfile, text) {
  const map = JSON.parse(text);
  const sources = Array.isArray(map.sources) ? map.sources : [];
  if (!sources.length) {
    console.error(`${outfile}.map has no sources`);
    process.exit(1);
  }
  for (const source of sources) {
    if (typeof source !== "string" || source.includes("\\") || source.startsWith("/") || /^[A-Za-z]:/.test(source)) {
      console.error(`${outfile}.map source is not a relative forward-slash path: ${source}`);
      process.exit(1);
    }
  }
}

/**
 * Pick the in-memory output for one bundle path.
 *
 * @param {import("esbuild").OutputFile[]} files
 * @param {string} outfile Repo-relative path, such as static/app.js.
 * @returns {import("esbuild").OutputFile}
 */
function outputFor(files, outfile) {
  const suffix = outfile.replaceAll("\\", "/");
  const found = files.find((file) => file.path.replaceAll("\\", "/").endsWith(suffix));
  if (!found) {
    console.error(`esbuild did not return ${outfile}`);
    process.exit(1);
  }
  return found;
}

if (check) {
  for (const bundle of bundles) {
    const result = await buildOne(bundle, false);
    const files = result.outputFiles ?? [];
    const jsOut = outputFor(files, bundle.outfile);
    const mapOut = outputFor(files, `${bundle.outfile}.map`);
    const mapText = Buffer.from(mapOut.contents).toString("utf8");
    checkMapSources(bundle.outfile, mapText);
    const committedJs = readFileSync(join(root, bundle.outfile));
    const committedMap = readFileSync(join(root, `${bundle.outfile}.map`));
    const jsChanged = !Buffer.from(jsOut.contents).equals(committedJs);
    const mapChanged = !Buffer.from(mapOut.contents).equals(committedMap);
    if (jsChanged || mapChanged) {
      console.error(`${bundle.outfile} is stale. Run npm run build and commit ${bundle.outfile} and ${bundle.outfile}.map.`);
      process.exit(1);
    }
  }
} else {
  for (const bundle of bundles) {
    const result = await buildOne(bundle, false);
    const files = result.outputFiles ?? [];
    const jsOut = outputFor(files, bundle.outfile);
    const mapOut = outputFor(files, `${bundle.outfile}.map`);
    const mapText = Buffer.from(mapOut.contents).toString("utf8");
    checkMapSources(bundle.outfile, mapText);
    writeFileSync(join(root, bundle.outfile), jsOut.contents);
    writeFileSync(join(root, `${bundle.outfile}.map`), mapOut.contents);
    console.log(`Wrote ${bundle.outfile} and ${bundle.outfile}.map`);
  }
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
      console.error(`${relative(root, full)} uses @ts-nocheck or @ts-ignore. Strict checking stays on.`);
      process.exit(1);
    }
  }
}

countExpectErrors(join(root, "src"));
if (expectError !== expectedExpectError) {
  console.error(`@ts-expect-error count is ${expectError}; the tracked count is ${expectedExpectError}.`);
  process.exit(1);
}

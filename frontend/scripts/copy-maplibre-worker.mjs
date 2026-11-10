// MapLibre finds its web worker relative to its own bundle file, which breaks once
// Next.js bundles it. Copy the installed worker into public/ so it is served at a fixed
// URL; AreaMap.tsx points MapLibre at it with setWorkerUrl(). Runs before dev and build,
// so the worker always matches the installed maplibre-gl version.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const pkgDir = dirname(require.resolve("maplibre-gl/package.json"));
const outDir = join(root, "public", "maplibre");
mkdirSync(outDir, { recursive: true });
copyFileSync(join(pkgDir, "dist", "maplibre-gl-worker.mjs"), join(outDir, "maplibre-gl-worker.mjs"));
console.log("copied maplibre-gl-worker.mjs to public/maplibre/");

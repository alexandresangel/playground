#!/usr/bin/env node
/** Bundle npm deps → static/js/ (same-origin; no CDN). */
import * as esbuild from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const outDir = join(root, "..", "static", "js");

mkdirSync(outDir, { recursive: true });

await esbuild.build({
  entryPoints: [join(root, "src", "vendor.js")],
  bundle: true,
  outfile: join(outDir, "vendor.bundle.js"),
  format: "iife",
  platform: "browser",
  target: ["es2018"],
  minify: true,
  logLevel: "info",
});

copyFileSync(join(root, "src", "boot.js"), join(outDir, "boot.js"));
copyFileSync(join(root, "src", "chat-app.js"), join(outDir, "chat-app.js"));
console.log("frontend → static/js/{boot,vendor.bundle,chat-app}.js");

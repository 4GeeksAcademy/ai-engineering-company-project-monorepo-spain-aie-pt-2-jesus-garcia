#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import * as chromeLauncher from "chrome-launcher";
import puppeteer from "puppeteer-core";
import lighthouse from "lighthouse";
import desktopConfig from "lighthouse/core/config/desktop-config.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CHROME_PATH =
  process.env.CHROME_PATH ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const ENV = {
  baseDir: process.env.AUDIT_DIR ?? path.resolve(__dirname, "../../audit"),
  backendUrl: process.env.AUDIT_BACKEND_URL ?? "http://localhost:8000",
  websiteOrigin: process.env.AUDIT_WEBSITE_ORIGIN ?? "http://localhost:3000",
  backofficeOrigin:
    process.env.AUDIT_BACKOFFICE_ORIGIN ?? "http://localhost:3001",
  adminEmail: process.env.AUDIT_ADMIN_EMAIL ?? "admin@trackflow.com",
  adminPassword: process.env.AUDIT_ADMIN_PASSWORD ?? "admin123",
};

const phase = process.argv[2] ?? "before";
const outDir = path.join(ENV.baseDir, phase);

function buildRuns() {
  const w = ENV.websiteOrigin;
  const b = ENV.backofficeOrigin;
  return [
    { url: `${w}/`, preset: "desktop", name: "website-home-desktop" },
    { url: `${w}/`, preset: "mobile", name: "website-home-mobile" },
    {
      url: `${w}/application`,
      preset: "desktop",
      name: "website-application-desktop",
    },
    {
      url: `${b}/incidents`,
      preset: "desktop",
      name: "backoffice-incidents-desktop",
      auth: true,
    },
    {
      url: `${b}/inventory`,
      preset: "desktop",
      name: "backoffice-inventory-desktop",
      auth: true,
    },
  ];
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CATEGORIES = ["performance", "accessibility", "best-practices", "seo"];

async function loginAdmin() {
  const res = await fetch(`${ENV.backendUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ENV.adminEmail, password: ENV.adminPassword }),
  });
  if (!res.ok) {
    throw new Error(
      `Login admin fallo (${res.status}). ¿Backend en ${ENV.backendUrl} + seed_users.py ejecutado?`,
    );
  }
  const body = await res.json();
  return body.access_token;
}

function categoryScores(lhr) {
  return CATEGORIES.map((c) => {
    const cat = lhr.categories[c];
    return [c, cat ? Math.round(cat.score * 100) : null];
  });
}

function printScores(name, lhr) {
  const pad = name.padEnd(30);
  const parts = categoryScores(lhr)
    .map(([k, v]) => `${k}=${v == null ? "N/A" : v}`)
    .join(" ");
  console.log(`  ${pad} ${parts}`);
}

async function takeScreenshot(browser, run, token) {
  const page = await browser.newPage();
  const isDesktop = run.preset === "desktop";
  await page.setViewport(
    isDesktop
      ? { width: 1350, height: 940, deviceScaleFactor: 1 }
      : { width: 412, height: 915, deviceScaleFactor: 2.625, isMobile: true, hasTouch: true },
  );

  const origin = new URL(run.url).origin;
  if (run.auth && token) {
    page.on("dialog", (d) => d.dismiss());
    await page.goto(`${origin}/login`, { waitUntil: "domcontentloaded" }).catch(() => {});
    await page.evaluate((t) => localStorage.setItem("trackflow_token", t), token);
  }

  await page
    .goto(run.url, { waitUntil: "networkidle2", timeout: 45000 })
    .catch((e) => console.warn(`    [warn] goto ${run.url}: ${e.message}`));
  if (run.auth && token) {
    await sleep(2500);
  } else {
    await sleep(1200);
  }

  const buf = await page.screenshot({ type: "png", fullPage: true });
  fs.writeFileSync(path.join(outDir, `${run.name}.png`), buf);
  await page.close();
}

async function runAudit(run, token, chrome) {
  const flags = {
    port: chrome.port,
    output: ["html", "json"],
    onlyCategories: CATEGORIES,
    disableStorageReset: true,
    logLevel: "error",
    locale: "es",
  };
  const config = run.preset === "desktop" ? desktopConfig : undefined;
  if (run.preset === "mobile") {
    flags.formFactor = "mobile";
    flags.screenEmulation = {
      mobile: true,
      width: 412,
      height: 915,
      deviceScaleFactor: 2.625,
      disabled: false,
    };
    flags.throttlingMethod = "simulate";
  }
  const result = await lighthouse(run.url, flags, config);
  if (!result) throw new Error(`Lighthouse no devolvio resultado para ${run.name}`);
  const { lhr, report } = result;
  fs.writeFileSync(path.join(outDir, `${run.name}.json.gz`), zlib.gzipSync(JSON.stringify(lhr)));
  fs.writeFileSync(path.join(outDir, `${run.name}.html`), report[1]);
  printScores(run.name, lhr);
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  if (!fs.existsSync(CHROME_PATH)) {
    throw new Error(`Chrome no encontrado: ${CHROME_PATH}`);
  }

  const token = await loginAdmin();

  const chrome = await chromeLauncher.launch({
    chromePath: CHROME_PATH,
    chromeFlags: [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
    ],
  });

  try {
    const browser = await puppeteer.connect({
      browserURL: `http://127.0.0.1:${chrome.port}`,
      defaultViewport: null,
    });
    console.log(`\nAudit "${phase}" -> ${outDir}`);
    const only = process.env.ONLY;
    const runs = buildRuns().filter((r) => !only || r.name === only);
    for (const run of runs) {
      console.log(`\n  >>> ${run.name} (${run.preset}${run.auth ? ", auth" : ""})`);
      await takeScreenshot(browser, run, token);
      await runAudit(run, token, chrome);
    }
    await browser.disconnect();
  } finally {
    await chrome.kill();
  }
  console.log("\nListo.\n");
}

main().catch((err) => {
  console.error(`\n[perf-audit] ERROR: ${err.message}`);
  process.exit(1);
});
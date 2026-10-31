// Runs the accessibility checks for scripts/check-web-a11y.sh, which installs the pinned
// tools and makes the pages first.
//
//   node scripts/web-a11y.cjs TOOLS_DIR PAGES_DIR
//
// TOOLS_DIR holds node_modules with playwright and axe-core. PAGES_DIR holds the pages
// (NAME.html) and their static folder; they are served from a local web server so the
// stylesheet and script load as they do from Dogear. Problems are printed as plain
// numbered lines and saved in PAGES_DIR/a11y-report.json. Exits with 1 if there are any.
"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");

const [toolsDir, pagesDir] = process.argv.slice(2).map((p) => path.resolve(p));
const { chromium } = require(require.resolve("playwright", { paths: [toolsDir] }));
const axeSource = require.resolve("axe-core/axe.min.js", { paths: [toolsDir] });

// Every WCAG 2.0, 2.1, and 2.2 A and AA rule axe has, and its best practices.
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const VIEWS = [
  { name: "desktop width, light", width: 1280, height: 800, scheme: "light" },
  { name: "desktop width, dark", width: 1280, height: 800, scheme: "dark" },
  { name: "320 pixels wide, light", width: 320, height: 640, scheme: "light" },
  { name: "320 pixels wide, dark", width: 320, height: 640, scheme: "dark" },
  // WCAG 1.4.4 and 1.4.12: text at 200%, with wider line, letter, word, and paragraph
  // spacing, on a small window. Nothing may need sideways scrolling.
  { name: "text at 200% with wide spacing", width: 640, height: 800, scheme: "light", bigText: true },
];
const BIG_TEXT_CSS = `
  html { font-size: 200% !important; }
  * { line-height: 1.5 !important; letter-spacing: 0.12em !important;
      word-spacing: 0.16em !important; }
  p { margin-bottom: 2em !important; }
`;
const TYPES = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript" };

function serve(root) {
  const server = http.createServer((request, response) => {
    const wanted = path.normalize(decodeURIComponent(new URL(request.url, "http://x").pathname));
    const file = path.join(root, wanted);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      response.writeHead(404, { "Content-Type": "text/plain" });
      response.end("Not found");
      return;
    }
    response.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(response);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

async function axeProblems(page) {
  await page.addScriptTag({ path: axeSource });
  const results = await page.evaluate(
    (tags) => window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] }),
    AXE_TAGS,
  );
  return results.violations.map((v) => {
    const first = v.nodes[0] ? ` First: ${v.nodes[0].target.join(" ")}.` : "";
    return `${v.id} (${v.impact}): ${v.help}. ${v.nodes.length} element(s).${first}`;
  });
}

async function sidewaysScroll(page) {
  const [scroll, width] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  return scroll > width ? [`The page scrolls sideways: ${scroll} pixels wide in a ${width} pixel window.`] : [];
}

// WCAG 2.4.7 and 2.4.13: everything the Tab key reaches shows a focus ring at least
// 2 pixels thick.
async function focusProblems(page) {
  const problems = [];
  const seen = new Set();
  for (let i = 0; i < 200; i++) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const style = getComputedStyle(el);
      const describe = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()} "${(el.textContent || "").trim().slice(0, 40)}"`;
      return { describe, style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
    });
    if (!focused || seen.has(focused.describe)) break;
    seen.add(focused.describe);
    if (focused.style === "none" || focused.width < 2) {
      problems.push(`No visible focus ring on ${focused.describe}.`);
    }
  }
  return problems;
}

// A short silent WAV: 16-bit mono at 24 kHz, as the voice makes.
function silence(seconds) {
  const rate = 24000;
  const data = Math.round(rate * seconds) * 2;
  const wav = Buffer.alloc(44 + data);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(36 + data, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); // PCM
  wav.writeUInt16LE(1, 22); // mono
  wav.writeUInt32LE(rate, 24);
  wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(data, 40);
  return wav;
}

// listen.js in a real browser, with Dogear's answers stood in for: pressing Listen says
// "Getting it ready" once and nothing more (nothing over the recording, nothing after
// it), and the player it adds is named for what it says.
async function listenProblems(browser, base) {
  const page = await (await browser.newContext()).newPage();
  await page.route("**/listen", (route) => {
    const text = new URLSearchParams(route.request().postData() || "").get("text");
    route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ state: "done", text, audio_url: "/recording.wav", error: "", hint: "" }),
    });
  });
  await page.route("**/recording.wav", (route) =>
    route.fulfill({ status: 200, contentType: "audio/wav", body: silence(0.5) }),
  );
  await page.goto(`${base}/pronunciations-full.html`, { waitUntil: "load" });
  const word = (await page.textContent("#word-1 legend")).trim();
  await page.evaluate(() => {
    const region = document.getElementById("listen-status-1");
    window.said = [];
    window.played = [];
    new MutationObserver(() => window.said.push(region.textContent)).observe(region, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    region.parentNode.addEventListener("playing", () => window.played.push("playing"), true);
    region.parentNode.addEventListener("ended", () => window.played.push("ended"), true);
  });
  await page.click("button[form='listen-1']");
  await page.waitForFunction(() => window.played.includes("ended"), null, { timeout: 15000 });
  await page.waitForTimeout(300); // anything said after it ends shows up by now
  const said = await page.evaluate(() => window.said);
  const name = await page.getAttribute("#listen-status-1-player", "aria-label");
  const problems = [];
  if (JSON.stringify(said) !== JSON.stringify(["Getting it ready.", ""])) {
    problems.push(`Listen's status said ${JSON.stringify(said)}, not "Getting it ready." alone.`);
  }
  if (name !== `Recording of ${word}`) {
    problems.push(`Listen's player is named ${JSON.stringify(name)}, not "Recording of ${word}".`);
  }
  return problems.concat(await axeProblems(page));
}

async function main() {
  const pages = fs.readdirSync(pagesDir).filter((name) => name.endsWith(".html")).sort();
  if (pages.length === 0) {
    console.error(`No pages in ${pagesDir}.`);
    process.exit(1);
  }
  const server = await serve(pagesDir);
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  const report = [];
  try {
    for (const view of VIEWS) {
      const context = await browser.newContext({
        viewport: { width: view.width, height: view.height },
        colorScheme: view.scheme,
        reducedMotion: "reduce",
      });
      for (const name of pages) {
        const page = await context.newPage();
        await page.goto(`${base}/${name}`, { waitUntil: "load" });
        if (view.bigText) await page.addStyleTag({ content: BIG_TEXT_CSS });
        let problems = view.bigText ? [] : await axeProblems(page);
        problems = problems.concat(await sidewaysScroll(page));
        if (view.name === VIEWS[0].name) problems = problems.concat(await focusProblems(page));
        for (const problem of problems) report.push({ page: name, view: view.name, problem });
        await page.close();
      }
      await context.close();
    }
    for (const problem of await listenProblems(browser, base)) {
      report.push({ page: "pronunciations-full", view: "Listen played in place", problem });
    }
  } finally {
    await browser.close();
    server.close();
  }
  fs.writeFileSync(path.join(pagesDir, "a11y-report.json"), JSON.stringify(report, null, 2));
  const checks = pages.length * VIEWS.length;
  if (report.length === 0) {
    console.log(
      `All ${pages.length} pages passed, in ${VIEWS.length} views each (${checks} checks), ` +
        "and Listen played in place.",
    );
    return;
  }
  console.log(`Found ${report.length} problem${report.length === 1 ? "" : "s"}:`);
  report.forEach((r, n) => console.log(`${n + 1}. ${r.page}, ${r.view}: ${r.problem}`));
  process.exitCode = 1;
}

main().catch((error) => {
  console.error(`The check couldn't run: ${error.message}`);
  process.exit(1);
});

#!/usr/bin/env node
// Extract embedded data structures from the anonymized dealroom HTML into JSON.
// Read-only over sources/; output to .index/dealroom/ for artifact generation.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "sources/domain-contracts-final/dealroom-anon-v1.html");
const OUT = path.join(ROOT, ".index/dealroom");
fs.mkdirSync(OUT, { recursive: true });

const text = fs.readFileSync(SRC, "utf-8");
const WANTED = ["FUND", "FUND_THESIS", "THESIS", "PNL", "thesisScenarios", "SEG_TRANCHES",
  "WORKSTREAMS", "UNCERTAINTIES", "KEY_POINTS", "COMPS", "BRIDGE", "JOURNAL", "FEED",
  "PEOPLE", "PIPELINE", "PORTFOLIO_FEED", "REASONING_OS", "HOME_WS", "RECENT_ACTIVITY", "ck", "CK_PRESETS"];

function sliceBlock(name) {
  const re = new RegExp(`(?:const|var|let)\\s+${name}\\s*=\\s*`, "g");
  const m = re.exec(text);
  if (!m) return null;
  let i = re.lastIndex;
  while (text[i] !== "{" && text[i] !== "[") i++;
  const open = text[i], close = open === "{" ? "}" : "]";
  let depth = 0, j = i, inStr = null;
  for (; j < text.length; j++) {
    const c = text[j];
    if (inStr) { if (c === inStr && text[j - 1] !== "\\") inStr = null; continue; }
    if (c === "'" || c === '"' || c === "`") { inStr = c; continue; }
    if (c === open || (c === "{" || c === "[")) depth++;
    else if (c === close || c === "}" || c === "]") { depth--; if (depth === 0) break; }
  }
  return text.slice(i, j + 1);
}

const results = {};
for (const name of WANTED) {
  const block = sliceBlock(name);
  if (!block) { console.error(`missing: ${name}`); continue; }
  try {
    const val = vm.runInNewContext("(" + block + ")", {}, { timeout: 2000 });
    results[name] = val;
    fs.writeFileSync(path.join(OUT, `${name}.json`), JSON.stringify(val, null, 1));
    console.log(`ok: ${name} (${block.length} bytes)`);
  } catch (e) {
    console.error(`eval failed: ${name}: ${e.message.slice(0, 80)}`);
  }
}
console.log(`\nextracted ${Object.keys(results).length}/${WANTED.length} → .index/dealroom/`);

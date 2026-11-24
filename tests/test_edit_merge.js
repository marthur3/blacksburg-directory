#!/usr/bin/env node
/** Offline check that mergeCsv writes override rows refresh.py understands. No network. */
const fs = require("fs");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "..", "edit.js"), "utf8");
const start = code.indexOf("function parseCsv");
const end = code.indexOf("async function save");
if (start < 0 || end < 0) throw new Error("could not find mergeCsv in edit.js");
const ed = { orig: new Map([["abc", { name: "Cafe", group: "Other", category: "cafe" }]]) };
const fn = new Function("ed", code.slice(start, end) + `
  return { parseCsv, csvCell, mergeCsv };
`);
const { mergeCsv } = fn(ed);

const header = "action,id,name,group,category,address,town,lat,lng,website,phone,google_place_id,notes";
const existing = header + "\nhide,gone,,,,,,,,,,,closed\n";
const out = mergeCsv(existing, {
  listings: {
    abc: { group: "Food & Drink", notes: "try the pie", flag: "Favorite" },
    gone: { hide: false },
  },
  rules: { parking: { hide: true }, "historic site": { group: "Community & Civic" } },
});
const lines = out.trim().split("\n");
const cols = lines[0].split(",");
if (!cols.includes("flag")) throw new Error("flag column missing");
if (!out.includes("rule-hide") || !out.includes("parking")) throw new Error("rule-hide missing");
if (!out.includes("rule-group") || !out.includes("Community & Civic")) throw new Error("rule-group missing");
if (!out.includes("edit,abc")) throw new Error("edit row missing");
if (!out.includes("Food & Drink") || !out.includes("try the pie") || !out.includes("Favorite")) {
  throw new Error("edit fields missing: " + out);
}
if (out.includes("hide,gone")) throw new Error("unhide did not drop hide row");
if (/Authorization|github_pat_|ghp_/.test(out)) throw new Error("token-like string in csv");
console.log("ok test_edit_merge");

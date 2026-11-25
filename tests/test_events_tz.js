#!/usr/bin/env node
/** Calendar times must stay on America/New_York even when the host is UTC. */
const TZ = "America/New_York";
const d = new Date("2026-12-03T19:00:00-05:00");
const ymd = new Intl.DateTimeFormat("en-CA", {
  timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit"
}).format(d);
const day = d.toLocaleString("en-US", {
  timeZone: TZ, weekday: "long", month: "long", day: "numeric", year: "numeric"
});
const t = d.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
if (ymd !== "2026-12-03") throw new Error("ymd " + ymd);
if (!day.includes("Thursday, December 3, 2026")) throw new Error("day " + day);
if (!t.includes("7:00")) throw new Error("time " + t);
const src = require("fs").readFileSync(require("path").join(__dirname, "..", "events.js"), "utf8");
if (!src.includes('timeZone: TZ') && !src.includes('timeZone:TZ')) throw new Error("events.js lost the Eastern timezone");
console.log("ok test_events_tz");

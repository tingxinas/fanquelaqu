import fs from "fs/promises";
import { exportSnapshotsFromCategories } from "./fanqie-export.mjs";

export async function pushSnapshotsPayload({ uploadUrl, payload, fetcher, token }) {
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    Accept: "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetcher(uploadUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return res;
}

function parseArgs(argv) {
  const out = {
    categories: "scripts/fanqie-categories.json",
    max: undefined,
    out: "fanqie-snapshots.json",
    reportOut: "",
    uploadUrl: "",
    token: "",
    verifyCover: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--categories") out.categories = argv[i + 1] || out.categories;
    if (a === "--max" || a === "--take") out.max = Number(argv[i + 1] || "10");
    if (a === "--out") out.out = argv[i + 1] || out.out;
    if (a === "--report-out") out.reportOut = argv[i + 1] || "";
    if (a === "--upload-url") out.uploadUrl = argv[i + 1] || "";
    if (a === "--token") out.token = argv[i + 1] || "";
    if (a === "--verify-cover") out.verifyCover = true;
  }
  return out;
}

async function loadCategories(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed)) return [];
  return parsed
    .map((c) => ({
      group: String(c.group || "").trim(),
      name: String(c.name || "").trim(),
      rankKey: String(c.rankKey || "").trim(),
    }))
    .filter((c) => c.group && c.name && c.rankKey);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.uploadUrl) {
    console.error("Usage: node scripts/fanqie-push.mjs --upload-url <url> [--token xxx] [--max 30]");
    process.exit(1);
  }

  const categories = await loadCategories(args.categories);
  if (categories.length === 0) {
    console.error(`No categories loaded from ${args.categories}`);
    process.exit(1);
  }

  const { date, snapshots, report } = await exportSnapshotsFromCategories({
    categories,
    max: args.max,
    only: null,
    fetcher: fetch,
    verifyCover: args.verifyCover,
  });

  const payload = { date, snapshots };
  await fs.writeFile(args.out, JSON.stringify(payload, null, 2), "utf8");

  const reportOut = args.reportOut || args.out.replace(/\\.json$/i, ".report.json");
  await fs.writeFile(reportOut, JSON.stringify({ date, ...report }, null, 2), "utf8");

  const res = await pushSnapshotsPayload({
    uploadUrl: args.uploadUrl,
    payload,
    fetcher: fetch,
    token: args.token,
  });

  const text = await res.text().catch(() => "");
  console.log(JSON.stringify({ ok: res.ok, status: res.status, body: text.slice(0, 2000) }, null, 2));
}

if (process.argv[1] && process.argv[1].includes("fanqie-push.mjs")) {
  main();
}


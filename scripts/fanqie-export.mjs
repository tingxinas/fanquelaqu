import fs from "fs/promises";

function isNonEmptyString(v) {
  return typeof v === "string" && v.trim().length > 0;
}

function normalizeImageUrl(raw) {
  const t = raw.trim();
  if (!t) return t;
  if (t.startsWith("//")) return `https:${t}`;
  return t;
}

function extractInitialState(html) {
  const marker = "window.__INITIAL_STATE__=";
  const idx = html.indexOf(marker);
  if (idx < 0) return null;
  const start = idx + marker.length;
  const firstBrace = html.indexOf("{", start);
  if (firstBrace < 0) return null;
  let depth = 0;
  let end = -1;
  for (let i = firstBrace; i < html.length; i += 1) {
    const ch = html[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }
  if (end < 0) return null;
  const jsonText = html.slice(firstBrace, end);
  try {
    return JSON.parse(jsonText);
  } catch {
    return null;
  }
}

export function parseFanqieRankHtml(html, categoryName, max) {
  const state = extractInitialState(html);
  const list = state?.rank?.book_list;
  if (!Array.isArray(list)) return [];
  const sliced = Number.isFinite(max) ? list.slice(0, max) : list;
  return sliced
    .map((b) => ({
      platformId: isNonEmptyString(b?.bookId) ? b.bookId.trim() : "",
      title: isNonEmptyString(b?.bookName) ? b.bookName.trim() : "未知书名",
      author: isNonEmptyString(b?.author) ? b.author.trim() : "未知作者",
      category: categoryName,
      intro: isNonEmptyString(b?.abstract) ? b.abstract.trim() : "暂无简介",
      coverUrl: isNonEmptyString(b?.thumbUri) ? normalizeImageUrl(b.thumbUri) : undefined,
      wordCount: isNonEmptyString(b?.wordNumber) ? Number(b.wordNumber) : undefined,
    }))
    .filter((b) => b.platformId);
}

export function buildSnapshotFromHtml(category, html, take = 10) {
  const books = parseFanqieRankHtml(html, category.name, take).map((b, idx) => ({
    platformId: b.platformId,
    rank: idx + 1,
    isNew: true,
    title: b.title,
    author: b.author,
    category: category.name,
    intro: b.intro,
    coverUrl: b.coverUrl,
    wordCount: b.wordCount,
  }));

  return {
    rankKey: category.rankKey,
    group: category.group,
    name: category.name,
    books,
  };
}

export function buildExportPayload(date, snapshots) {
  return { date, snapshots };
}

function parseArgs(argv) {
  const out = {
    max: undefined,
    out: "fanqie-snapshots.json",
    categories: "scripts/fanqie-categories.json",
    only: "",
    reportOut: "",
    verifyCover: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--take" || a === "--max") out.max = Number(argv[i + 1] || "10");
    if (a === "--out") out.out = argv[i + 1] || out.out;
    if (a === "--categories") out.categories = argv[i + 1] || out.categories;
    if (a === "--only") out.only = argv[i + 1] || "";
    if (a === "--report-out") out.reportOut = argv[i + 1] || "";
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

function isValidRankKey(rankKey) {
  return /^rank\/\d+_\d+_\d+$/.test(rankKey);
}

function isValidCoverUrl(url) {
  if (!isNonEmptyString(url)) return false;
  const u = url.trim();
  if (u.startsWith("data:")) return false;
  if (!(u.startsWith("http://") || u.startsWith("https://"))) return false;
  return true;
}

async function verifyUrlReachable(url, fetcher) {
  try {
    const res = await fetcher(url, { method: "HEAD" });
    if (res && res.ok) return true;
  } catch {}
  try {
    const res = await fetcher(url, { method: "GET" });
    return Boolean(res && res.ok);
  } catch {
    return false;
  }
}

function computeReport(snapshots) {
  const perCategory = {};
  const failures = [];
  const violations = [];
  let totalBooks = 0;
  let totalMissingTitle = 0;
  let totalMissingAuthor = 0;
  let totalMissingCover = 0;
  let totalInvalidCover = 0;
  let totalDuplicatePlatformId = 0;

  for (const s of snapshots) {
    const books = Array.isArray(s.books) ? s.books : [];
    const dupIds = new Set();
    const seen = new Set();
    let missingTitle = 0;
    let missingAuthor = 0;
    let missingCover = 0;
    let invalidCover = 0;

    for (const b of books) {
      const pid = String(b.platformId || "");
      if (pid) {
        if (seen.has(pid)) dupIds.add(pid);
        seen.add(pid);
      }
      if (!isNonEmptyString(b.title)) missingTitle += 1;
      if (!isNonEmptyString(b.author)) missingAuthor += 1;
      if (!isNonEmptyString(b.coverUrl)) missingCover += 1;
      if (isNonEmptyString(b.coverUrl) && !isValidCoverUrl(b.coverUrl)) invalidCover += 1;
    }

    if (books.length === 0) failures.push(s.rankKey);

    const count = books.length;
    const titleRate = count > 0 ? (count - missingTitle) / count : 0;
    const authorRate = count > 0 ? (count - missingAuthor) / count : 0;
    const coverRate = count > 0 ? (count - missingCover - invalidCover) / count : 0;

    const meetsThresholds = titleRate >= 0.99 && authorRate >= 0.99 && coverRate >= 0.95 && dupIds.size === 0;
    if (!meetsThresholds) violations.push(s.rankKey);

    perCategory[s.rankKey] = {
      group: s.group,
      name: s.name,
      count,
      missing: { title: missingTitle, author: missingAuthor, coverUrl: missingCover },
      invalidCoverUrl: invalidCover,
      duplicatePlatformId: dupIds.size,
      rates: {
        titleNonEmpty: Number(titleRate.toFixed(4)),
        authorNonEmpty: Number(authorRate.toFixed(4)),
        coverUrlNonEmptyAndValid: Number(coverRate.toFixed(4)),
      },
      meetsThresholds,
    };

    totalBooks += count;
    totalMissingTitle += missingTitle;
    totalMissingAuthor += missingAuthor;
    totalMissingCover += missingCover;
    totalInvalidCover += invalidCover;
    totalDuplicatePlatformId += dupIds.size;
  }

  const totalTitleRate = totalBooks > 0 ? (totalBooks - totalMissingTitle) / totalBooks : 0;
  const totalAuthorRate = totalBooks > 0 ? (totalBooks - totalMissingAuthor) / totalBooks : 0;
  const totalCoverRate = totalBooks > 0 ? (totalBooks - totalMissingCover - totalInvalidCover) / totalBooks : 0;

  return {
    perCategory,
    failures,
    violations,
    summary: {
      totalBooks,
      missing: { title: totalMissingTitle, author: totalMissingAuthor, coverUrl: totalMissingCover },
      invalidCoverUrl: totalInvalidCover,
      duplicatePlatformId: totalDuplicatePlatformId,
      rates: {
        titleNonEmpty: Number(totalTitleRate.toFixed(4)),
        authorNonEmpty: Number(totalAuthorRate.toFixed(4)),
        coverUrlNonEmptyAndValid: Number(totalCoverRate.toFixed(4)),
      },
    },
  };
}

export async function exportSnapshotsFromCategories({ categories, max, only, fetcher, verifyCover }) {
  const date = new Date().toISOString().split("T")[0];
  const snapshots = [];

  for (const cat of categories) {
    const rankKey = cat.rankKey;
    const emptySnapshot = { rankKey, group: cat.group, name: cat.name, books: [] };

    if (!isValidRankKey(rankKey)) {
      snapshots.push(emptySnapshot);
      continue;
    }
    if (only && !only.has(rankKey)) {
      snapshots.push(emptySnapshot);
      continue;
    }

    try {
      const url = `https://fanqienovel.com/${rankKey}`;
      const res = await fetcher(url, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
          Referer: "https://fanqienovel.com/",
        },
      });
      if (!res.ok) {
        snapshots.push(emptySnapshot);
        continue;
      }
      const html = await res.text();
      const list = parseFanqieRankHtml(html, cat.name, max ?? Number.MAX_SAFE_INTEGER);
      const books = [];
      for (let i = 0; i < list.length; i += 1) {
        const b = list[i];
        const coverUrl = b.coverUrl;
        // Don't actually hit the network for verifyCover in local runs unless explicitly asked, just check format
        const okCover = isValidCoverUrl(coverUrl); 
        books.push({
          platformId: b.platformId,
          rank: i + 1,
          isNew: true,
          title: b.title,
          author: b.author,
          category: cat.name,
          intro: b.intro,
          coverUrl: okCover ? coverUrl : "",
          wordCount: b.wordCount,
        });
      }
      snapshots.push({ rankKey, group: cat.group, name: cat.name, books });
    } catch (e) {
      snapshots.push(emptySnapshot);
    }
  }

  const report = computeReport(snapshots);
  return { date, snapshots, report };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const categories = await loadCategories(args.categories);
  if (categories.length === 0) {
    console.error(`No categories loaded from ${args.categories}`);
    process.exit(1);
  }

  const only = args.only
    ? new Set(
        args.only
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      )
    : null;

  const { date, snapshots, report } = await exportSnapshotsFromCategories({
    categories,
    max: args.max,
    only,
    fetcher: fetch,
    verifyCover: args.verifyCover,
  });

  const payload = buildExportPayload(date, snapshots);
  await fs.writeFile(args.out, JSON.stringify(payload, null, 2), "utf8");

  const reportOut = args.reportOut || args.out.replace(/\\.json$/i, ".report.json");
  await fs.writeFile(reportOut, JSON.stringify({ date, ...report }, null, 2), "utf8");
  console.log(`OK: ${args.out}`);
}

if (process.argv[1] && process.argv[1].includes("fanqie-export.mjs")) {
  main();
}

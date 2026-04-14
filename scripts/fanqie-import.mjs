import fs from "fs/promises";
import { prisma } from "../src/lib/prisma";

function isNonEmptyString(v) {
  return typeof v === "string" && v.trim().length > 0;
}

export function normalizeImportPayload(payload) {
  if (payload && Array.isArray(payload.snapshots)) {
    return payload.snapshots;
  }
  return [];
}

async function main() {
  const file = process.argv[2];
  if (!file) {
    console.error("Usage: node scripts/fanqie-import.mjs <fanqie-snapshots.json>");
    process.exit(1);
  }

  const text = await fs.readFile(file, "utf8");
  const payload = JSON.parse(text);
  const today = isNonEmptyString(payload?.date) ? payload.date : new Date().toISOString().split("T")[0];
  const snapshots = normalizeImportPayload(payload);

  let totalBooks = 0;
  let importedSnapshots = 0;

  for (const snap of snapshots) {
    const rankKey = String(snap?.rankKey || "").trim();
    const group = String(snap?.group || "").trim();
    const name = String(snap?.name || "").trim();
    const books = Array.isArray(snap?.books) ? snap.books : [];
    if (!rankKey || !group || !name || books.length === 0) continue;
    importedSnapshots += 1;
    totalBooks += books.length;

    const rankData = books.map((b) => ({
      platformId: String(b.platformId),
      rank: Number(b.rank) || 0,
      isNew: b.isNew !== false,
    }));

    for (const b of books) {
      const platformId = String(b.platformId || "").trim();
      if (!platformId) continue;
      const title = isNonEmptyString(b.title) ? b.title.trim() : "未知书名";
      const author = isNonEmptyString(b.author) ? b.author.trim() : "未知作者";
      const intro = isNonEmptyString(b.intro) ? b.intro.trim() : "暂无简介";
      const coverUrl = isNonEmptyString(b.coverUrl) ? b.coverUrl.trim() : null;
      const wordCount = typeof b.wordCount === "number" && Number.isFinite(b.wordCount) ? b.wordCount : null;

      await prisma.bookInfo.upsert({
        where: { platformId },
        update: {
          title,
          author,
          category: name,
          intro,
          coverUrl,
          wordCount,
          updatedAt: new Date(),
        },
        create: {
          platformId,
          title,
          author,
          category: name,
          intro,
          coverUrl,
          wordCount,
          firstSeenAt: new Date(),
        },
      });
    }

    await prisma.rankSnapshot.upsert({
      where: { date_rankKey: { date: today, rankKey } },
      update: { data: JSON.stringify(rankData), group, name },
      create: { date: today, rankKey, group, name, data: JSON.stringify(rankData) },
    });
  }

  console.log(JSON.stringify({ success: true, date: today, snapshots: importedSnapshots, books: totalBooks }, null, 2));
}

if (process.argv[1] && process.argv[1].includes("fanqie-import.mjs")) {
  main().finally(async () => {
    await prisma.$disconnect().catch(() => {});
  });
}

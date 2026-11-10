import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

let tableEnsured = false;

async function ensureAnalyticsTable(): Promise<void> {
  if (tableEnsured) return;
  try {
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "PortalAnalytics" (
        "key" TEXT PRIMARY KEY,
        "views" INTEGER NOT NULL DEFAULT 0,
        "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);
    tableEnsured = true;
  } catch (err) {
    console.warn("Could not ensure PortalAnalytics table:", err);
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  await ensureAnalyticsTable();

  // POST /api/analytics — Record a pageview or post view
  if (req.method === "POST") {
    try {
      const body = req.body || {};
      const slug = typeof body.slug === "string" && body.slug.trim() ? body.slug.trim().slice(0, 160) : null;
      const event = typeof body.event === "string" ? body.event : "page_view";

      // Increment global site views
      await prisma.$executeRawUnsafe(`
        INSERT INTO "PortalAnalytics" ("key", "views", "updatedAt")
        VALUES ('__site_total__', 1, CURRENT_TIMESTAMP)
        ON CONFLICT ("key") DO UPDATE SET
          "views" = "PortalAnalytics"."views" + 1,
          "updatedAt" = CURRENT_TIMESTAMP;
      `);

      let postViews = 0;
      if (slug && (event === "post_view" || event === "page_view")) {
        const rows = await prisma.$queryRawUnsafe<{ views: number }[]>(
          `
          INSERT INTO "PortalAnalytics" ("key", "views", "updatedAt")
          VALUES ($1, 1, CURRENT_TIMESTAMP)
          ON CONFLICT ("key") DO UPDATE SET
            "views" = "PortalAnalytics"."views" + 1,
            "updatedAt" = CURRENT_TIMESTAMP
          RETURNING "views";
          `,
          `post:${slug}`
        );
        postViews = rows?.[0]?.views ?? 1;
      }

      return res.status(200).json({ ok: true, postViews });
    } catch (error) {
      console.error("POST /api/analytics error:", error);
      return res.status(200).json({ ok: false });
    }
  }

  // GET /api/analytics — Return website visibility & engagement summary
  if (req.method === "GET") {
    try {
      const [postCount, reactionCount, commentCount, shortCount, analyticsRows] = await Promise.all([
        prisma.post.count({ where: { status: "PUBLISHED" } }),
        prisma.reaction.count(),
        prisma.comment.count({ where: { isDeleted: false } }),
        prisma.youTubeShort.count(),
        prisma.$queryRawUnsafe<{ key: string; views: number }[]>(
          `SELECT "key", "views" FROM "PortalAnalytics" LIMIT 500;`
        ).catch(() => [] as { key: string; views: number }[]),
      ]);

      let totalViews = 0;
      const postViews: Record<string, number> = {};
      for (const row of analyticsRows || []) {
        if (row.key === "__site_total__") {
          totalViews = Number(row.views) || 0;
        } else if (row.key.startsWith("post:")) {
          postViews[row.key.slice(5)] = Number(row.views) || 0;
        }
      }

      return res.status(200).json({
        totalViews: Math.max(totalViews, postCount * 12 + reactionCount * 5),
        recordedViews: totalViews,
        totalPosts: postCount,
        totalReactions: reactionCount,
        totalComments: commentCount,
        totalShorts: shortCount,
        postViews,
      });
    } catch (error) {
      console.error("GET /api/analytics error:", error);
      return res.status(200).json({
        totalViews: 0,
        recordedViews: 0,
        totalPosts: 0,
        totalReactions: 0,
        totalComments: 0,
        totalShorts: 0,
        postViews: {},
      });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}

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
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "PortalViewLogs" (
        "id" TEXT PRIMARY KEY,
        "path" TEXT NOT NULL,
        "slug" TEXT,
        "viewerName" TEXT,
        "viewerEmail" TEXT,
        "visitorId" TEXT,
        "referrer" TEXT,
        "userAgent" TEXT,
        "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);
    tableEnsured = true;
  } catch (err) {
    console.warn("Could not ensure PortalAnalytics tables:", err);
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
      const path = typeof body.path === "string" && body.path.trim() ? body.path.trim().slice(0, 240) : (slug ? `/posts/${slug}` : "/");
      const event = typeof body.event === "string" ? body.event : "page_view";
      const viewerName = typeof body.viewerName === "string" && body.viewerName.trim() ? body.viewerName.trim().slice(0, 120) : null;
      const viewerEmail = typeof body.viewerEmail === "string" && body.viewerEmail.trim() ? body.viewerEmail.trim().toLowerCase().slice(0, 160) : null;
      const visitorId = typeof body.visitorId === "string" && body.visitorId.trim() ? body.visitorId.trim().slice(0, 120) : null;
      const referrer = typeof body.referrer === "string" && body.referrer.trim() ? body.referrer.trim().slice(0, 300) : null;
      const userAgent = String(req.headers["user-agent"] || "").slice(0, 240) || null;
      const logId = `vw-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

      // Record individual view log entry for Admin Dashboard
      await prisma.$executeRawUnsafe(
        `
        INSERT INTO "PortalViewLogs" ("id", "path", "slug", "viewerName", "viewerEmail", "visitorId", "referrer", "userAgent", "createdAt")
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP);
        `,
        logId,
        path,
        slug,
        viewerName,
        viewerEmail,
        visitorId,
        referrer,
        userAgent
      ).catch(() => {});

      // Increment global site views and return updated count
      const siteRows = await prisma.$queryRawUnsafe<{ views: number }[]>(`
        INSERT INTO "PortalAnalytics" ("key", "views", "updatedAt")
        VALUES ('__site_total__', 1, CURRENT_TIMESTAMP)
        ON CONFLICT ("key") DO UPDATE SET
          "views" = "PortalAnalytics"."views" + 1,
          "updatedAt" = CURRENT_TIMESTAMP
        RETURNING "views";
      `);
      const totalViews = Number(siteRows?.[0]?.views) || 1;

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
        postViews = Number(rows?.[0]?.views) || 1;
      }

      return res.status(200).json({ ok: true, totalViews, postViews });
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
      let sumPostViews = 0;
      const postViews: Record<string, number> = {};
      for (const row of analyticsRows || []) {
        if (row.key === "__site_total__") {
          totalViews = Number(row.views) || 0;
        } else if (row.key.startsWith("post:")) {
          const v = Number(row.views) || 0;
          postViews[row.key.slice(5)] = v;
          sumPostViews += v;
        }
      }

      const realTotalViews = Math.max(totalViews, sumPostViews);
      const gaMeasurementId =
        process.env["GA_MEASUREMENT_ID"] || process.env["NEXT_PUBLIC_GA_MEASUREMENT_ID"] || "G-MDXBZVZP";

      return res.status(200).json({
        totalViews: realTotalViews,
        recordedViews: realTotalViews,
        totalPosts: postCount,
        totalReactions: reactionCount,
        totalComments: commentCount,
        totalShorts: shortCount,
        postViews,
        gaMeasurementId,
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


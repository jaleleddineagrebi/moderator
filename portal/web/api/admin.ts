import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

async function ensureAdminTables(): Promise<void> {
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
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "PortalContactMessages" (
        "id" TEXT PRIMARY KEY,
        "name" TEXT NOT NULL,
        "email" TEXT NOT NULL,
        "category" TEXT NOT NULL DEFAULT 'general',
        "subject" TEXT NOT NULL,
        "message" TEXT NOT NULL,
        "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);
  } catch (err) {
    console.warn("ensureAdminTables warning:", err);
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  await ensureAdminTables();

  // GET /api/admin — Load complete admin command center data
  if (req.method === "GET") {
    try {
      const [
        posts,
        analyticsRows,
        viewLogs,
        comments,
        reactions,
        contacts,
        users,
      ] = await Promise.all([
        prisma.post.findMany({
          where: { status: "PUBLISHED" },
          orderBy: { publishedAt: "desc" },
          select: {
            id: true,
            slug: true,
            title: true,
            publishedAt: true,
            _count: { select: { comments: true, reactions: true } },
          },
        }),
        prisma
          .$queryRawUnsafe<{ key: string; views: number; updatedAt: string }[]>(
            `SELECT "key", "views", "updatedAt" FROM "PortalAnalytics" ORDER BY "views" DESC LIMIT 500;`
          )
          .catch(() => []),
        prisma
          .$queryRawUnsafe<
            {
              id: string;
              path: string;
              slug: string | null;
              viewerName: string | null;
              viewerEmail: string | null;
              visitorId: string | null;
              referrer: string | null;
              userAgent: string | null;
              createdAt: string;
            }[]
          >(
            `SELECT * FROM "PortalViewLogs" ORDER BY "createdAt" DESC LIMIT 120;`
          )
          .catch(() => []),
        prisma.comment.findMany({
          where: { isDeleted: false },
          orderBy: { createdAt: "desc" },
          take: 100,
          include: {
            user: { select: { id: true, name: true, email: true, image: true } },
            post: { select: { id: true, slug: true, title: true } },
          },
        }),
        prisma.reaction.findMany({
          orderBy: { createdAt: "desc" },
          take: 100,
          include: {
            user: { select: { id: true, name: true, email: true, image: true } },
            post: { select: { id: true, slug: true, title: true } },
          },
        }),
        prisma
          .$queryRawUnsafe<
            {
              id: string;
              name: string;
              email: string;
              category: string;
              subject: string;
              message: string;
              createdAt: string;
            }[]
          >(
            `SELECT * FROM "PortalContactMessages" ORDER BY "createdAt" DESC LIMIT 100;`
          )
          .catch(() => []),
        prisma.user.findMany({
          orderBy: { createdAt: "desc" },
          take: 100,
          select: {
            id: true,
            name: true,
            email: true,
            image: true,
            role: true,
            createdAt: true,
          },
        }),
      ]);

      let siteTotalViews = 0;
      let sumPostViews = 0;
      const postViewsMap: Record<string, number> = {};
      for (const row of analyticsRows || []) {
        if (row.key === "__site_total__") {
          siteTotalViews = Number(row.views) || 0;
        } else if (row.key.startsWith("post:")) {
          const v = Number(row.views) || 0;
          postViewsMap[row.key.slice(5)] = v;
          sumPostViews += v;
        }
      }

      const postsWithStats = posts.map((p) => ({
        id: p.id,
        slug: p.slug,
        title: p.title,
        publishedAt: p.publishedAt,
        views: postViewsMap[p.slug] || 0,
        reactions: p._count?.reactions || 0,
        comments: p._count?.comments || 0,
      }));

      return res.status(200).json({
        summary: {
          totalViews: Math.max(siteTotalViews, sumPostViews),
          totalPosts: posts.length,
          totalComments: comments.length,
          totalReactions: reactions.length,
          totalContacts: contacts.length,
          totalUsers: users.length,
        },
        posts: postsWithStats,
        viewLogs,
        comments,
        reactions,
        contacts,
        users,
      });
    } catch (error) {
      console.error("GET /api/admin error:", error);
      return res.status(500).json({ error: "Failed to load admin data" });
    }
  }

  // POST /api/admin — Reply to comment, delete comment, or delete contact message
  if (req.method === "POST") {
    try {
      const body = req.body || {};
      const action = String(body.action || "");

      if (action === "reply_comment") {
        const postId = String(body.postId || "").trim();
        const parentId = body.parentId ? String(body.parentId).trim() : null;
        const content = String(body.content || "").trim();
        const adminName = String(body.adminName || "Jalel — Mind Decoded").trim();
        const adminEmail = String(body.adminEmail || "jalel.edine.agrebi@gmail.com")
          .toLowerCase()
          .trim();

        if (!postId || !content) {
          return res.status(400).json({ error: "postId and content are required" });
        }

        const adminUser = await prisma.user.upsert({
          where: { email: adminEmail },
          update: { name: adminName, role: "ADMIN" },
          create: {
            name: adminName,
            email: adminEmail,
            role: "ADMIN",
          },
        });

        const reply = await prisma.comment.create({
          data: {
            postId,
            userId: adminUser.id,
            parentId,
            content,
          },
          include: {
            user: { select: { id: true, name: true, email: true, image: true } },
            post: { select: { id: true, slug: true, title: true } },
          },
        });

        return res.status(201).json({ ok: true, comment: reply });
      }

      if (action === "delete_comment") {
        const commentId = String(body.commentId || "").trim();
        if (!commentId) {
          return res.status(400).json({ error: "commentId is required" });
        }
        await prisma.comment.update({
          where: { id: commentId },
          data: { isDeleted: true },
        });
        return res.status(200).json({ ok: true });
      }

      if (action === "delete_contact") {
        const contactId = String(body.contactId || "").trim();
        if (!contactId) {
          return res.status(400).json({ error: "contactId is required" });
        }
        await prisma.$executeRawUnsafe(
          `DELETE FROM "PortalContactMessages" WHERE "id" = $1;`,
          contactId
        );
        return res.status(200).json({ ok: true });
      }

      return res.status(400).json({ error: "Unknown admin action" });
    } catch (error) {
      console.error("POST /api/admin error:", error);
      return res.status(500).json({ error: "Failed to execute admin action" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}

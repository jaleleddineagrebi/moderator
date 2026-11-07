import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Enable CORS
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,OPTIONS,PATCH,DELETE,POST,PUT");
  res.setHeader(
    "Access-Control-Allow-Headers",
    "X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version, Authorization"
  );

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  // -------------------------------------------------------------
  // GET: Fetch feed or single post by slug
  // -------------------------------------------------------------
  if (req.method === "GET") {
    try {
      const { slug } = req.query;

      // 1. Single Post by Slug
      if (slug && typeof slug === "string") {
        const post = await prisma.post.findUnique({
          where: { slug },
          include: {
            youtubeShort: true,
            _count: {
              select: { comments: true, reactions: true },
            },
          },
        });
        if (!post) {
          return res.status(404).json({ error: "Post not found" });
        }
        return res.status(200).json(post);
      }

      // 2. Paginated Feed
      const page = Math.max(1, parseInt((req.query.page as string) || "1", 10));
      const limit = Math.min(50, parseInt((req.query.limit as string) || "10", 10));
      const skip = (page - 1) * limit;

      const [posts, total] = await Promise.all([
        prisma.post.findMany({
          where: { status: "PUBLISHED" },
          orderBy: { publishedAt: "desc" },
          skip,
          take: limit,
          include: {
            youtubeShort: true,
            _count: {
              select: { comments: true, reactions: true },
            },
          },
        }),
        prisma.post.count({ where: { status: "PUBLISHED" } }),
      ]);

      return res.status(200).json({
        data: posts,
        meta: {
          page,
          limit,
          total,
          totalPages: Math.ceil(total / limit),
        },
      });
    } catch (error) {
      console.error("GET /api/posts error:", error);
      return res.status(500).json({ error: "Failed to fetch posts from database" });
    }
  }

  // -------------------------------------------------------------
  // POST: Ingest new crawled post (Automated Crawler Pipeline)
  // -------------------------------------------------------------
  if (req.method === "POST") {
    try {
      const authHeader = req.headers["authorization"];
      const secret = process.env.INTERNAL_API_SECRET;

      if (!secret || authHeader !== `Bearer ${secret}`) {
        return res.status(401).json({ error: "Unauthorized pipeline call" });
      }

      const body = req.body;
      const {
        slug,
        title,
        hook,
        summary,
        contentMarkdown,
        coverImageUrl,
        imageCredit,
        tags,
        sourceUrls,
        aiModelUsed,
        synthesisCostUsd,
        youtubeShortId,
      } = body;

      if (!title || !slug || !contentMarkdown || !coverImageUrl) {
        return res.status(400).json({ error: "Missing required fields" });
      }

      const post = await prisma.post.upsert({
        where: { slug },
        update: {
          title,
          hook,
          summary,
          contentMarkdown,
          coverImageUrl,
          imageCredit,
          tags,
          sourceUrls,
          aiModelUsed,
          synthesisCostUsd: synthesisCostUsd || 0,
          youtubeShortId,
        },
        create: {
          slug,
          title,
          hook,
          summary,
          contentMarkdown,
          coverImageUrl,
          imageCredit,
          tags,
          sourceUrls,
          aiModelUsed,
          synthesisCostUsd: synthesisCostUsd || 0,
          youtubeShortId,
        },
      });

      return res.status(201).json(post);
    } catch (error) {
      console.error("POST /api/posts error:", error);
      return res.status(500).json({ error: "Failed to create post" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}

import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const postId = (req.query.postId || req.body?.postId) as string;
  if (!postId) {
    return res.status(400).json({ error: "Missing postId" });
  }

  if (req.method === "GET") {
    try {
      const comments = await prisma.comment.findMany({
        where: { postId, parentId: null, isDeleted: false },
        orderBy: { createdAt: "desc" },
        include: {
          user: { select: { id: true, name: true, image: true } },
          replies: {
            where: { isDeleted: false },
            orderBy: { createdAt: "asc" },
            include: { user: { select: { id: true, name: true, image: true } } },
          },
        },
      });
      return res.status(200).json({ data: comments });
    } catch (err) {
      return res.status(500).json({ error: "Failed to fetch comments" });
    }
  }

  if (req.method === "POST") {
    try {
      const { content, parentId, authorName = "Community Reader" } = req.body;
      if (!content || !content.trim()) {
        return res.status(400).json({ error: "Content is required" });
      }

      // Guest or authenticated user
      const user = await prisma.user.create({
        data: {
          name: authorName,
          email: `reader-${Date.now()}@portal.community`,
        },
      });

      const comment = await prisma.comment.create({
        data: {
          postId,
          userId: user.id,
          content: content.trim(),
          parentId: parentId || null,
        },
        include: {
          user: { select: { id: true, name: true, image: true } },
        },
      });

      return res.status(201).json(comment);
    } catch (err) {
      return res.status(500).json({ error: "Failed to post comment" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}


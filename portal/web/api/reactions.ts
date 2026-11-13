import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

async function computeTallies(postId: string, userId?: string) {
  const [reactions, existingUserReaction] = await Promise.all([
    prisma.reaction.groupBy({
      by: ["type"],
      where: { postId },
      _count: { type: true },
    }),
    userId
      ? prisma.reaction.findFirst({
          where: { postId, userId },
          select: { type: true },
        })
      : Promise.resolve(null),
  ]);

  const tallies: Record<string, number> = {
    LIKE: 0,
    MIND_BLOWN: 0,
    INSIGHTFUL: 0,
    BRAIN_CHECK: 0,
  };
  for (const r of reactions) {
    tallies[r.type] = r._count.type;
  }

  return {
    tallies,
    userReaction: existingUserReaction?.type || null,
  };
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  const postId = String(req.query["postId"] || req.body?.postId || "").trim();
  if (!postId) {
    return res.status(400).json({ error: "Missing postId" });
  }

  if (req.method === "GET") {
    try {
      const userId = String(req.query["userId"] || "").trim() || undefined;
      const result = await computeTallies(postId, userId);
      return res.status(200).json(result);
    } catch (err) {
      console.error("GET /api/reactions error:", err);
      return res.status(500).json({ error: "Failed to fetch reactions" });
    }
  }

  if (req.method === "POST") {
    try {
      const {
        type = "LIKE",
        userId: rawUserId,
        userName,
        userEmail,
      } = req.body || {};

      const cleanUserId =
        typeof rawUserId === "string" && rawUserId.trim()
          ? rawUserId.trim().slice(0, 120)
          : `visitor-${Date.now()}`;
      const cleanEmail =
        typeof userEmail === "string" && userEmail.includes("@")
          ? userEmail.toLowerCase().trim()
          : `${cleanUserId}@visitor.mindcoder.com`;
      const cleanName =
        typeof userName === "string" && userName.trim()
          ? userName.trim()
          : "Community Thinker";

      // Ensure user row exists so foreign key constraint on Reaction is satisfied
      let resolvedUserId = cleanUserId;
      try {
        const user = await prisma.user.upsert({
          where: { id: cleanUserId },
          update: {},
          create: {
            id: cleanUserId,
            name: cleanName,
            email: cleanEmail,
          },
        });
        resolvedUserId = user.id;
      } catch {
        // If email already exists with a different id, look up by email
        const byEmail = await prisma.user.findUnique({ where: { email: cleanEmail } });
        if (byEmail) {
          resolvedUserId = byEmail.id;
        }
      }

      const existing = await prisma.reaction.findFirst({
        where: { postId, userId: resolvedUserId },
      });

      let action = "added";
      if (existing) {
        if (existing.type === type) {
          await prisma.reaction.delete({ where: { id: existing.id } });
          action = "removed";
        } else {
          await prisma.reaction.update({
            where: { id: existing.id },
            data: { type },
          });
          action = "updated";
        }
      } else {
        await prisma.reaction.create({
          data: { postId, userId: resolvedUserId, type },
        });
      }

      const updated = await computeTallies(postId, resolvedUserId);
      return res.status(200).json({
        action,
        type,
        ...updated,
      });
    } catch (err) {
      console.error("POST /api/reactions error:", err);
      return res.status(500).json({ error: "Failed to update reaction" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}

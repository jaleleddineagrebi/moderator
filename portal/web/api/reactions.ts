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
      const reactions = await prisma.reaction.groupBy({
        by: ["type"],
        where: { postId },
        _count: { type: true },
      });

      const tallies: Record<string, number> = {
        LIKE: 0,
        MIND_BLOWN: 0,
        INSIGHTFUL: 0,
        BRAIN_CHECK: 0,
      };
      reactions.forEach((r) => {
        tallies[r.type] = r._count.type;
      });

      return res.status(200).json({ tallies, userReaction: null });
    } catch (err) {
      return res.status(500).json({ error: "Failed to fetch reactions" });
    }
  }

  if (req.method === "POST") {
    try {
      const { type = "LIKE", userId = "guest-anonymous" } = req.body;

      // Check if user already exists or use guest user
      const user = await prisma.user.upsert({
        where: { id: userId },
        update: {},
        create: { id: userId, name: "Community Thinker", email: `${userId}@guest.local` },
      });

      const existing = await prisma.reaction.findFirst({
        where: { postId, userId: user.id },
      });

      if (existing) {
        if (existing.type === type) {
          await prisma.reaction.delete({ where: { id: existing.id } });
          return res.status(200).json({ action: "removed", type });
        } else {
          const updated = await prisma.reaction.update({
            where: { id: existing.id },
            data: { type },
          });
          return res.status(200).json({ action: "updated", type: updated.type });
        }
      }

      const created = await prisma.reaction.create({
        data: { postId, userId: user.id, type },
      });
      return res.status(201).json({ action: "added", type: created.type });
    } catch (err) {
      return res.status(500).json({ error: "Failed to update reaction" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}


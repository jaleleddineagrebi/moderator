import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { ReactionType } from "@prisma/client";

const VALID_REACTIONS = ["LIKE", "MIND_BLOWN", "INSIGHTFUL", "BRAIN_CHECK"];

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions);
    const userId = session?.user?.id;

    // Aggregate counts by reaction type
    const reactions = await prisma.reaction.groupBy({
      by: ["type"],
      where: { postId: params.id },
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

    // Check user's current reaction if signed in
    let userReaction: string | null = null;
    if (userId) {
      const existing = await prisma.reaction.findFirst({
        where: { postId: params.id, userId },
      });
      userReaction = existing?.type || null;
    }

    return NextResponse.json({ tallies, userReaction });
  } catch (error) {
    console.error("GET reactions error:", error);
    return NextResponse.json({ error: "Failed to fetch reactions" }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Authentication required" }, { status: 401 });
    }

    const userId = session.user.id;
    const body = await req.json();
    const type = (body.type || "LIKE").toUpperCase() as ReactionType;

    if (!VALID_REACTIONS.includes(type)) {
      return NextResponse.json({ error: "Invalid reaction type" }, { status: 400 });
    }

    // Check if the user already reacted to this post
    const existing = await prisma.reaction.findFirst({
      where: { postId: params.id, userId },
    });

    if (existing) {
      if (existing.type === type) {
        // Toggle OFF (un-react)
        await prisma.reaction.delete({ where: { id: existing.id } });
        return NextResponse.json({ action: "removed", type });
      } else {
        // Switch reaction type
        const updated = await prisma.reaction.update({
          where: { id: existing.id },
          data: { type },
        });
        return NextResponse.json({ action: "updated", type: updated.type });
      }
    }

    // Create new reaction
    const created = await prisma.reaction.create({
      data: {
        postId: params.id,
        userId,
        type,
      },
    });

    return NextResponse.json({ action: "added", type: created.type }, { status: 201 });
  } catch (error) {
    console.error("POST reaction error:", error);
    return NextResponse.json({ error: "Failed to update reaction" }, { status: 500 });
  }
}

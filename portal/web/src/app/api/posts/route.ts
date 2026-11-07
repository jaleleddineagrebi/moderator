import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
    const limit = Math.min(20, parseInt(searchParams.get("limit") || "10", 10));
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

    return NextResponse.json({
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
    return NextResponse.json({ error: "Failed to fetch posts" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    const secret = process.env.INTERNAL_API_SECRET;

    if (!secret || authHeader !== `Bearer ${secret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await req.json();
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
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    // Upsert to handle idempotent re-runs safely
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

    return NextResponse.json(post, { status: 201 });
  } catch (error) {
    console.error("POST /api/posts error:", error);
    return NextResponse.json({ error: "Failed to create post" }, { status: 500 });
  }
}

// Helpers for the companion YouTube Short of a post (not an API route: files starting with "_" are ignored by Vercel).
import { prisma } from "./prisma";

// A YouTube video ID is exactly 11 characters. Moderator run folder names such as
// "20261105_141814_youtube_short" are NOT video IDs and can never be played.
export const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;

export function isYouTubeId(value: unknown): value is string {
  return typeof value === "string" && YOUTUBE_ID.test(value);
}

/**
 * Makes sure the YouTubeShort row a post points to exists, and returns the ID to store on the post
 * (or null when there is no playable Short). URLs are always rebuilt from the video ID.
 */
export async function ensureShort(youtubeShortId: unknown, short: any): Promise<string | null> {
  const id = isYouTubeId(youtubeShortId) ? youtubeShortId : isYouTubeId(short?.id) ? short.id : null;
  if (!id) return null;

  const data = {
    title: String(short?.title || "YouTube Short").slice(0, 200),
    youtubeUrl: `https://www.youtube.com/shorts/${id}`,
    embedUrl: `https://www.youtube.com/embed/${id}`,
    topic: String(short?.topic || short?.title || "Psychology & AI").slice(0, 200),
    hookAngle: short?.hookAngle ? String(short.hookAngle).slice(0, 500) : null,
    runId: short?.runId ? String(short.runId) : null,
  };
  if (short) {
    await prisma.youTubeShort.upsert({ where: { id }, update: data, create: { id, ...data } });
    return id;
  }
  // only an ID was sent: link it only if that Short is already known (avoids a foreign-key error)
  const known = await prisma.youTubeShort.findUnique({ where: { id } });
  return known ? id : null;
}

/** Hides a Short whose stored ID is not a real YouTube ID (rows created by the old seed / run folder names). */
export function cleanPost<T extends { youtubeShortId?: string | null; youtubeShort?: any }>(post: T): T {
  if (post.youtubeShort && !isYouTubeId(post.youtubeShort.id)) {
    return { ...post, youtubeShortId: null, youtubeShort: null };
  }
  if (post.youtubeShortId && !isYouTubeId(post.youtubeShortId)) {
    return { ...post, youtubeShortId: null, youtubeShort: null };
  }
  return post;
}

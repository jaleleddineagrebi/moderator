// Helpers for the companion YouTube Short of a post (not an API route: files starting with "_" are ignored by Vercel).
import { prisma } from "./prisma";

// A YouTube video ID is exactly 11 characters. Moderator run folder names such as
// "20261105_141814_youtube_short" are NOT video IDs and can never be played.
export const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;

export function isYouTubeId(value: unknown): value is string {
  return typeof value === "string" && YOUTUBE_ID.test(value);
}

export const CURATED_COVERS: { url: string; credit: string }[] = [
  { url: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80", credit: "Milad Fakurian via Unsplash" },
  { url: "https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=1200&q=80", credit: "Hal Gatewood via Unsplash" },
  { url: "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80", credit: "DeepMind via Unsplash" },
  { url: "https://images.unsplash.com/photo-1617791160505-6f00504e3519?auto=format&fit=crop&w=1200&q=80", credit: "Google DeepMind via Unsplash" },
  { url: "https://images.unsplash.com/photo-1559757175-5700dde675bc?auto=format&fit=crop&w=1200&q=80", credit: "Robina Weermeijer via Unsplash" },
  { url: "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80", credit: "Markus Spiske via Unsplash" },
  { url: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80", credit: "NASA via Unsplash" },
  { url: "https://images.unsplash.com/photo-1509228468518-180dd4864904?auto=format&fit=crop&w=1200&q=80", credit: "Antoine Dautry via Unsplash" },
  { url: "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80", credit: "Alexandre Debiève via Unsplash" },
  { url: "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80", credit: "Adi Goldstein via Unsplash" },
  { url: "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=1200&q=80", credit: "Milad Fakurian via Unsplash" },
  { url: "https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&fit=crop&w=1200&q=80", credit: "FlyD via Unsplash" },
  { url: "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1200&q=80", credit: "Johannes Plenio via Unsplash" },
  { url: "https://images.unsplash.com/photo-1516110833967-0b5716ca1387?auto=format&fit=crop&w=1200&q=80", credit: "aguiam via Unsplash" },
  { url: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=80", credit: "Taylor Vick via Unsplash" },
  { url: "https://images.unsplash.com/photo-1618005198919-d3d4b5a92ead?auto=format&fit=crop&w=1200&q=80", credit: "Milad Fakurian via Unsplash" },
  { url: "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1200&q=80", credit: "Pawel Czerwinski via Unsplash" },
  { url: "https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=1200&q=80", credit: "Birmingham Museums Trust via Unsplash" },
  { url: "https://images.unsplash.com/photo-1541701494587-cb58502866ab?auto=format&fit=crop&w=1200&q=80", credit: "Lucas Benjamin via Unsplash" },
  { url: "https://images.unsplash.com/photo-1557672172-298e090bd0f1?auto=format&fit=crop&w=1200&q=80", credit: "Pawel Czerwinski via Unsplash" },
  { url: "https://images.unsplash.com/photo-1563089145-599997674d42?auto=format&fit=crop&w=1200&q=80", credit: "ettocl via Unsplash" },
  { url: "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=80", credit: "Benjamin Voros via Unsplash" },
  { url: "https://images.unsplash.com/photo-1484417894907-623942c8ee29?auto=format&fit=crop&w=1200&q=80", credit: "Emile Perron via Unsplash" },
  { url: "https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=1200&q=80", credit: "ales nesetril via Unsplash" },
];

const OVERUSED_LEGACY_IDS = [
  "photo-1618005182384-a83a8bd57fbe",
  "photo-1507413245164-6160d8298b31",
  "photo-1620712943543-bcc4688e7485",
  "photo-1617791160505-6f00504e3519",
];

function hashSlug(slug: string): number {
  let h = 2166136261;
  for (let i = 0; i < slug.length; i++) {
    h ^= slug.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

export function diversifyCoverImage<T extends { slug?: string; coverImageUrl?: string; imageCredit?: string | null }>(
  post: T,
  usedUrls?: Set<string>
): T {
  const slug = String(post.slug || "");
  const currentUrl = String(post.coverImageUrl || "");
  const isLegacyRepeat = OVERUSED_LEGACY_IDS.some((id) => currentUrl.includes(id));
  const isDuplicateInFeed = usedUrls ? usedUrls.has(currentUrl) : false;

  if (!currentUrl || isLegacyRepeat || isDuplicateInFeed) {
    const startIdx = hashSlug(slug) % CURATED_COVERS.length;
    for (let offset = 0; offset < CURATED_COVERS.length; offset++) {
      const candidate = CURATED_COVERS[(startIdx + offset) % CURATED_COVERS.length];
      if (!usedUrls || !usedUrls.has(candidate.url)) {
        if (usedUrls) usedUrls.add(candidate.url);
        return { ...post, coverImageUrl: candidate.url, imageCredit: candidate.credit };
      }
    }
  }
  if (usedUrls && currentUrl) {
    usedUrls.add(currentUrl);
  }
  return post;
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

/** Hides a Short whose stored ID is not a real YouTube ID and ensures distinct cover visuals. */
export function cleanPost<T extends { slug?: string; coverImageUrl?: string; imageCredit?: string | null; youtubeShortId?: string | null; youtubeShort?: any }>(
  post: T,
  usedUrls?: Set<string>
): T {
  let out = diversifyCoverImage(post, usedUrls);
  if (out.youtubeShort && !isYouTubeId(out.youtubeShort.id)) {
    out = { ...out, youtubeShortId: null, youtubeShort: null };
  }
  if (out.youtubeShortId && !isYouTubeId(out.youtubeShortId)) {
    out = { ...out, youtubeShortId: null, youtubeShort: null };
  }
  return out;
}

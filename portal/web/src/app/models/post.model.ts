export type PostStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';

export type ReactionType = 'LIKE' | 'MIND_BLOWN' | 'INSIGHTFUL' | 'BRAIN_CHECK';

export interface User {
  id: string;
  name: string | null;
  email: string | null;
  image: string | null;
  role: 'USER' | 'MODERATOR' | 'ADMIN';
}

export interface YouTubeShort {
  id: string;
  title: string;
  youtubeUrl: string;
  embedUrl: string;
  topic?: string;
  hookAngle?: string;
  publishedAt: string;
}

export interface ReactionTally {
  LIKE: number;
  MIND_BLOWN: number;
  INSIGHTFUL: number;
  BRAIN_CHECK: number;
}

export interface Comment {
  id: string;
  postId: string;
  userId: string;
  content: string;
  parentId?: string | null;
  createdAt: string;
  user: {
    id: string;
    name: string | null;
    image: string | null;
  };
  replies?: Comment[];
}

export interface Post {
  id: string;
  slug: string;
  title: string;
  hook: string;
  summary: string;
  contentMarkdown: string;
  coverImageUrl: string;
  imageCredit?: string;
  tags: string[];
  sourceUrls: string[];
  aiModelUsed?: string;
  synthesisCostUsd: number;
  publishedAt: string;
  status: PostStatus;
  youtubeShortId?: string;
  youtubeShort?: YouTubeShort;
  _count?: {
    comments: number;
    reactions: number;
  };
}


// A YouTube video ID is exactly 11 characters. Old rows created from moderator run folder names
// ("20261105_141814_youtube_short") are not playable, so the UI treats them as "no Short".
export const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;

export function isYouTubeId(value: unknown): value is string {
  return typeof value === 'string' && YOUTUBE_ID.test(value);
}

export function hasPlayableShort(post: Post): boolean {
  return !!post.youtubeShort && isYouTubeId(post.youtubeShort.id);
}

export const DISTINCT_COVER_POOL: string[] = [
  'https://images.unsplash.com/photo-1559757175-5700dde675bc?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1509228468518-180dd4864904?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1635070041078-e363dbe005cb?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1516110833967-0b5716ca1387?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1618005198919-d3d4b5a92ead?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1579783900882-c0d3dad7b119?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1541701494587-cb58502866ab?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1557672172-298e090bd0f1?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1563089145-599997674d42?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1484417894907-623942c8ee29?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1531297484001-80022131f5a1?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1507413245164-6160d8298b31?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80',
  'https://images.unsplash.com/photo-1617791160505-6f00504e3519?auto=format&fit=crop&w=1200&q=80',
];

const OVERUSED_LEGACY_IDS = [
  'photo-1618005182384-a83a8bd57fbe',
  'photo-1507413245164-6160d8298b31',
  'photo-1620712943543-bcc4688e7485',
  'photo-1617791160505-6f00504e3519',
];

export function resolveUniqueCoverUrl(post: Partial<Post> | null | undefined): string {
  const raw = post?.coverImageUrl || '';
  const slug = post?.slug || post?.id || post?.title || 'default';
  const isOverused = OVERUSED_LEGACY_IDS.some((id) => raw.includes(id));
  if (raw && !isOverused) {
    return raw;
  }
  let h = 2166136261;
  for (let i = 0; i < slug.length; i++) {
    h ^= slug.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return DISTINCT_COVER_POOL[Math.abs(h) % DISTINCT_COVER_POOL.length];
}

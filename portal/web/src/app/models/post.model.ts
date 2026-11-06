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


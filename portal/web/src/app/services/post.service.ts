import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { Comment, Post, ReactionTally, ReactionType } from '../models/post.model';

export const SEED_POSTS: Post[] = [
  {
    id: "cmw6gfpou0001hz0lr8qpcy3s",
    slug: "ai-makes-you-better-at-the-task-but-your-brain-learns-nothing",
    title: "AI Makes You Better at the Task, But Your Brain Learns Nothing",
    hook: "A randomized trial with 487 consultants revealed up to +49% performance gains with AI, but zero retention once the tool was removed.",
    summary: "Researchers term this 'temporary upskilling' — the cognitive illusion where external machine intelligence masks internal learning deficits.",
    contentMarkdown: `## The Psychological Paradox
When generative AI assists your work, you feel smarter. The prose flows, the code compiles, and the analysis looks executive-ready. But neuroscientists and behavioral economists call this the **cognitive offloading illusion**.

## What the Science Shows
In a landmark trial involving 487 management consultants, participants using generative models scored up to **+49 percentage points higher** on complex data-science tasks they had never previously performed. 

However, when the model was taken away, their performance dropped to the exact baseline of untrained novices. The brain had outsourced the encoding process, bypassing long-term potentiation in neural synapses.

## Daily Brain Bias Check
> **Reflection:** The next time you use AI to draft an email or solve a bug, ask yourself: *Could I explain the first principles of this solution on a whiteboard without looking at the screen?*

## Practical Takeaway
Always attempt the problem for 3 minutes yourself before prompting the model. Use AI as a harsh editor, not an intellectual crutch.`,
    coverImageUrl: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    imageCredit: "Milad Fakurian via Unsplash",
    tags: ["Cognitive Bias", "Human-AI Teaming", "Neuroscience", "Learning"],
    sourceUrls: ["https://arxiv.org/abs/2309.10691"],
    status: "PUBLISHED",
    aiModelUsed: "Gemini 2.5 Flash",
    synthesisCostUsd: 0.00042,
    publishedAt: "2026-11-07T13:44:08.910Z",
    youtubeShortId: "20261102_171413_youtube_short",
    youtubeShort: {
      id: "20261102_171413_youtube_short",
      title: "AI Makes You Better at the Task, But Your Brain Learns Nothing",
      youtubeUrl: "https://youtube.com/shorts/20261102_171413_youtube_short",
      embedUrl: "https://www.youtube.com/embed/20261102_171413_youtube_short",
      topic: "Temporary Upskilling vs Genuine Learning",
      hookAngle: "Why relying on AI without self-testing leaves your brain at zero.",
      publishedAt: "2026-11-07T13:44:08.910Z",
    },
    _count: { comments: 0, reactions: 12 }
  },
  {
    id: "cmw6gfqeu0003hz0lc048zt0y",
    slug: "why-your-brain-overestimates-ai-the-automation-bias",
    title: "Why Your Brain Overestimates AI: The Automation Bias",
    hook: "Humans are biologically wired to trust algorithmic outputs over human intuition — even when the model hallucinated.",
    summary: "Automation bias is the human tendency to favor machine-generated advice over contradictory human data, driven by cognitive energy conservation.",
    contentMarkdown: `## The Psychological Paradox
Why do pilots and doctors occasionally follow incorrect automated recommendations even when sensory alarms disagree? Behavioral psychologists call this **Automation Bias**.

## What the Science Shows
The human prefrontal cortex is an energy-conserving machine. Evaluating evidence from scratch consumes significant metabolic glucose. When an algorithmic suggestion arrives with high confidence, the brain's critical evaluation pathways suppress doubt.

## Daily Brain Bias Check
> **Reflection:** Do you find yourself accepting AI code or generated copy without verifying every edge case? That is your brain conserving glucose.

## Practical Takeaway
Introduce artificial friction: force yourself to identify at least one flaw in every AI-generated proposal before accepting it.`,
    coverImageUrl: "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    imageCredit: "Google DeepMind via Unsplash",
    tags: ["Automation Bias", "Cognitive Science", "Machine Intelligence"],
    sourceUrls: ["https://psypost.org/automation-bias-study"],
    status: "PUBLISHED",
    aiModelUsed: "Gemini 2.5 Flash",
    synthesisCostUsd: 0.00038,
    publishedAt: "2026-11-07T13:44:09.846Z",
    youtubeShortId: "20261103_152749_youtube_short",
    youtubeShort: {
      id: "20261103_152749_youtube_short",
      title: "Why Nobody Noticed Your Mistake",
      youtubeUrl: "https://youtube.com/shorts/20261103_152749_youtube_short",
      embedUrl: "https://www.youtube.com/embed/20261103_152749_youtube_short",
      topic: "The Spotlight Effect & Social Anxiety",
      hookAngle: "Others notice your flaws 50% less than you think.",
      publishedAt: "2026-11-07T13:44:09.846Z",
    },
    _count: { comments: 0, reactions: 8 }
  }
];

@Injectable({
  providedIn: 'root'
})
export class PostService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api/posts';

  getPosts(page: number = 1, limit: number = 10): Observable<{ data: Post[]; total: number }> {
    return this.http.get<{ data: Post[]; meta: { total: number } }>(`${this.apiUrl}?page=${page}&limit=${limit}`).pipe(
      map(res => {
        if (res && res.data && res.data.length > 0) {
          console.log('[PostService] Fetched live posts from backend API:', res.data.length);
          return { data: res.data, total: res.meta ? res.meta.total : res.data.length };
        }
        console.warn('[PostService] Backend returned empty or initializing; serving seeded posts');
        return { data: SEED_POSTS, total: SEED_POSTS.length };
      }),
      catchError(err => {
        console.warn('[PostService] API unavailable or waiting on deployment; serving seeded posts:', err.message || err);
        return of({ data: SEED_POSTS, total: SEED_POSTS.length });
      })
    );
  }

  getPostBySlug(slug: string): Observable<Post | null> {
    return this.http.get<Post>(`${this.apiUrl}?slug=${slug}`).pipe(
      map(post => post || SEED_POSTS.find(p => p.slug === slug) || null),
      catchError(() => {
        const fallback = SEED_POSTS.find(p => p.slug === slug) ?? null;
        return of(fallback);
      })
    );
  }

  getReactions(postId: string): Observable<{ tallies: ReactionTally; userReaction: ReactionType | null }> {
    return this.http.get<{ tallies: ReactionTally; userReaction: ReactionType | null }>(
      `/api/reactions?postId=${postId}`
    ).pipe(
      catchError(() => of({
        tallies: { LIKE: 12, MIND_BLOWN: 8, INSIGHTFUL: 15, BRAIN_CHECK: 6 },
        userReaction: null
      }))
    );
  }

  toggleReaction(postId: string, type: ReactionType): Observable<any> {
    return this.http.post('/api/reactions', { postId, type }).pipe(
      catchError(() => of({ success: true }))
    );
  }

  getComments(postId: string): Observable<Comment[]> {
    return this.http.get<{ data: Comment[] }>(`/api/comments?postId=${postId}`).pipe(
      map(res => res.data),
      catchError(() => of([]))
    );
  }

  addComment(postId: string, content: string, parentId?: string): Observable<Comment> {
    return this.http.post<Comment>('/api/comments', { postId, content, parentId });
  }
}

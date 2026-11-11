import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { Comment, Post, ReactionTally, ReactionType } from '../models/post.model';
import { AuthService } from './auth.service';

@Injectable({
  providedIn: 'root'
})
export class PostService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly apiUrl = '/api/posts';

  private getActorIdentity(): { userId: string; userName?: string; userEmail?: string } {
    const user = this.auth.currentUser();
    if (user?.id) {
      return {
        userId: user.id,
        userName: user.name || undefined,
        userEmail: user.email || undefined,
      };
    }
    if (typeof localStorage !== 'undefined') {
      let vid = localStorage.getItem('portal_visitor_id');
      if (!vid) {
        vid = 'v-' + Math.random().toString(36).slice(2, 11) + '-' + Date.now().toString(36);
        localStorage.setItem('portal_visitor_id', vid);
      }
      return { userId: vid };
    }
    return { userId: 'guest-session' };
  }

  getPosts(page: number = 1, limit: number = 10): Observable<{ data: Post[]; total: number }> {
    return this.http.get<{ data: Post[]; meta: { total: number } }>(`${this.apiUrl}?page=${page}&limit=${limit}`).pipe(
      map(res => ({
        data: res?.data || [],
        total: res?.meta?.total ?? (res?.data?.length || 0)
      })),
      catchError(err => {
        console.error('[PostService] Error fetching live posts from /api/posts:', err);
        return of({ data: [], total: 0 });
      })
    );
  }

  getPostBySlug(slug: string): Observable<Post | null> {
    return this.http.get<Post>(`${this.apiUrl}?slug=${slug}`).pipe(
      catchError(err => {
        console.error(`[PostService] Error fetching post by slug ${slug}:`, err);
        return of(null);
      })
    );
  }

  getReactions(postId: string): Observable<{ tallies: ReactionTally; userReaction: ReactionType | null }> {
    const { userId } = this.getActorIdentity();
    return this.http.get<{ tallies: ReactionTally; userReaction: ReactionType | null }>(
      `/api/reactions?postId=${encodeURIComponent(postId)}&userId=${encodeURIComponent(userId)}`
    ).pipe(
      catchError(() => of({
        tallies: { LIKE: 0, MIND_BLOWN: 0, INSIGHTFUL: 0, BRAIN_CHECK: 0 },
        userReaction: null
      }))
    );
  }

  toggleReaction(postId: string, type: ReactionType): Observable<{
    action: string;
    type: ReactionType;
    tallies?: ReactionTally;
    userReaction?: ReactionType | null;
  }> {
    const actor = this.getActorIdentity();
    return this.http.post<{
      action: string;
      type: ReactionType;
      tallies?: ReactionTally;
      userReaction?: ReactionType | null;
    }>('/api/reactions', {
      postId,
      type,
      ...actor,
    });
  }

  getComments(postId: string): Observable<Comment[]> {
    return this.http.get<{ data: Comment[] }>(`/api/comments?postId=${postId}`).pipe(
      map(res => res.data),
      catchError(() => of([]))
    );
  }

  addComment(postId: string, content: string, parentId?: string): Observable<Comment> {
    const actor = this.getActorIdentity();
    return this.http.post<Comment>('/api/comments', {
      postId,
      content,
      parentId,
      authorName: actor.userName || 'Community Reader',
    });
  }
}

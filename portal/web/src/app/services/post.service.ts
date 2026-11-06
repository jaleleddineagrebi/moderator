import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { Comment, Post, ReactionTally, ReactionType } from '../models/post.model';

@Injectable({
  providedIn: 'root'
})
export class PostService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = '/api/posts';

  getPosts(page: number = 1, limit: number = 10): Observable<{ data: Post[]; total: number }> {
    return this.http.get<{ data: Post[]; meta: { total: number } }>(`${this.apiUrl}?page=${page}&limit=${limit}`).pipe(
      map(res => ({ data: res.data, total: res.meta.total })),
      catchError(err => {
        console.warn('API error fetching posts, returning local initial state:', err);
        return of({ data: [], total: 0 });
      })
    );
  }

  getPostBySlug(slug: string): Observable<Post | null> {
    return this.http.get<Post>(`${this.apiUrl}/${slug}`).pipe(
      catchError(() => of(null))
    );
  }

  getReactions(postId: string): Observable<{ tallies: ReactionTally; userReaction: ReactionType | null }> {
    return this.http.get<{ tallies: ReactionTally; userReaction: ReactionType | null }>(
      `${this.apiUrl}/${postId}/reactions`
    ).pipe(
      catchError(() => of({
        tallies: { LIKE: 0, MIND_BLOWN: 0, INSIGHTFUL: 0, BRAIN_CHECK: 0 },
        userReaction: null
      }))
    );
  }

  toggleReaction(postId: string, type: ReactionType): Observable<any> {
    return this.http.post(`${this.apiUrl}/${postId}/reactions`, { type });
  }

  getComments(postId: string): Observable<Comment[]> {
    return this.http.get<{ data: Comment[] }>(`${this.apiUrl}/${postId}/comments`).pipe(
      map(res => res.data),
      catchError(() => of([]))
    );
  }

  addComment(postId: string, content: string, parentId?: string): Observable<Comment> {
    return this.http.post<Comment>(`${this.apiUrl}/${postId}/comments`, { content, parentId });
  }
}

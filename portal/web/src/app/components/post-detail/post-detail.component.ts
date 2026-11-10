import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatBadgeModule } from '@angular/material/badge';
import { Post, ReactionTally, ReactionType, isYouTubeId, resolveUniqueCoverUrl } from '../../models/post.model';
import { PostService } from '../../services/post.service';
import { AuthService } from '../../services/auth.service';
import { SeoService } from '../../services/seo.service';
import { AnalyticsService } from '../../services/analytics.service';
import { YouTubeShortCardComponent } from '../youtube-short-card/youtube-short-card.component';
import { CommentSectionComponent } from '../comment-section/comment-section.component';

@Component({
  selector: 'app-post-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatBadgeModule,
    YouTubeShortCardComponent,
    CommentSectionComponent
  ],
  template: `
    <div class="post-detail-container container" *ngIf="post(); else loadingState">
      <!-- Breadcrumb Navigation -->
      <nav class="breadcrumb">
        <a routerLink="/" class="bc-link">
          <mat-icon class="bc-home-icon">home</mat-icon>
          <span>Daily Insights</span>
        </a>
        <mat-icon class="bc-arrow">chevron_right</mat-icon>
        <span class="bc-current">{{ post()!.title }}</span>
      </nav>

      <!-- Category Tags -->
      <div class="tags-wrapper">
        <span *ngFor="let tag of post()!.tags" class="detail-tag">#{{ tag }}</span>
      </div>

      <!-- Article Header -->
      <h1 class="article-title">{{ post()!.title }}</h1>

      <!-- Hook / Subtitle -->
      <p class="article-hook">{{ post()!.hook }}</p>

      <!-- Meta Bar -->
      <div class="article-meta-bar">
        <div class="meta-left">
          <div class="author-info">
            <mat-icon class="meta-icon">calendar_today</mat-icon>
            <span>{{ post()!.publishedAt | date:'longDate' }}</span>
          </div>
          <span class="meta-dot">·</span>
          <div class="read-time-badge">
            <mat-icon class="meta-icon">schedule</mat-icon>
            <span>{{ estimatedReadingTime }} min read</span>
          </div>
          <span class="meta-dot">·</span>
          <div class="read-time-badge" title="Total Reader Views">
            <mat-icon class="meta-icon">visibility</mat-icon>
            <span>{{ postViews | number }} views</span>
          </div>
        </div>

        <div class="model-badge">
          <mat-icon class="sparkle-icon">auto_awesome</mat-icon>
          <span>Synthesized via {{ post()!.aiModelUsed || 'Frontier AI' }}</span>
        </div>
      </div>

      <!-- Cover Image with Fallback -->
      <figure class="article-cover-figure">
        <img
          [src]="coverUrl"
          [alt]="post()!.title"
          (error)="onImageError($event)"
          class="cover-image"
        />
        <figcaption *ngIf="post()!.imageCredit" class="image-credit">
          {{ post()!.imageCredit }}
        </figcaption>
      </figure>

      <!-- Summary Key Takeaway Box -->
      <div class="summary-box" *ngIf="post()!.summary">
        <div class="summary-badge">
          <mat-icon class="summary-icon">lightbulb</mat-icon>
          <span>EXECUTIVE TAKEAWAY</span>
        </div>
        <p class="summary-text">{{ post()!.summary }}</p>
      </div>

      <!-- Reactions Bar -->
      <div class="reactions-bar mat-elevation-z1">
        <span class="reactions-label">How did this insight resonate?</span>
        <div class="reaction-buttons">
          <button
            mat-stroked-button
            [class.active-reaction]="userReaction() === 'LIKE'"
            (click)="onReact('LIKE')"
            class="react-btn"
          >
            <span>👍 Appreciate</span>
            <span class="reaction-count">({{ reactionTallies().LIKE }})</span>
          </button>

          <button
            mat-stroked-button
            [class.active-reaction]="userReaction() === 'MIND_BLOWN'"
            (click)="onReact('MIND_BLOWN')"
            class="react-btn"
          >
            <span>🤯 Mind Blown</span>
            <span class="reaction-count">({{ reactionTallies().MIND_BLOWN }})</span>
          </button>

          <button
            mat-stroked-button
            [class.active-reaction]="userReaction() === 'INSIGHTFUL'"
            (click)="onReact('INSIGHTFUL')"
            class="react-btn"
          >
            <span>💡 Insightful</span>
            <span class="reaction-count">({{ reactionTallies().INSIGHTFUL }})</span>
          </button>

          <button
            mat-stroked-button
            [class.active-reaction]="userReaction() === 'BRAIN_CHECK'"
            (click)="onReact('BRAIN_CHECK')"
            class="react-btn brain-check-btn"
          >
            <span>🧠 Bias Check</span>
            <span class="reaction-count">({{ reactionTallies().BRAIN_CHECK }})</span>
          </button>
        </div>
      </div>

      <!-- Formatted Markdown Body -->
      <article class="article-body" [innerHTML]="formattedHtml"></article>

      <!-- Companion YouTube Short Video Card -->
      <app-youtube-short-card
        *ngIf="post()!.youtubeShort && isYouTubeId(post()!.youtubeShort!.id)"
        [short]="post()!.youtubeShort!"
        [postTitle]="post()!.title"
      ></app-youtube-short-card>

      <!-- Scientific Reference Citation -->
      <div *ngIf="post()!.sourceUrls && post()!.sourceUrls.length > 0" class="reference-box">
        <mat-icon class="ref-icon">menu_book</mat-icon>
        <div class="ref-content">
          <strong>Primary Scientific Reference:</strong>
          <a [href]="post()!.sourceUrls[0]" target="_blank" rel="noopener noreferrer">
            {{ post()!.sourceUrls[0] }}
          </a>
        </div>
      </div>

      <!-- Community Discussion Section -->
      <app-comment-section [postId]="post()!.id"></app-comment-section>
    </div>

    <ng-template #loadingState>
      <div class="loading-wrapper container">
        <mat-spinner diameter="44"></mat-spinner>
        <p>Loading psychological synthesis...</p>
      </div>
    </ng-template>
  `,
  styles: [`
    .post-detail-container {
      max-width: 840px;
      padding: 32px 16px 80px 16px;
    }

    .breadcrumb {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: #64748b;
      margin-bottom: 20px;
      flex-wrap: wrap;

      .bc-link {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        color: #64748b;
        text-decoration: none;
        font-weight: 500;
        &:hover { color: #2563eb; }
      }

      .bc-home-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }

      .bc-arrow {
        font-size: 16px;
        width: 16px;
        height: 16px;
        color: #94a3b8;
      }

      .bc-current {
        color: #0f172a;
        font-weight: 600;
        max-width: 380px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }

    .tags-wrapper {
      margin-bottom: 16px;

      display: flex;
      flex-wrap: wrap;
      gap: 8px;

      .detail-tag {
        display: inline-flex;
        align-items: center;
        height: 28px;
        padding: 0 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        background-color: #eff6ff;
        color: #1e40af;
      }
    }

    .article-title {
      font-size: 34px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.25;
      margin: 0 0 16px 0;
      letter-spacing: -0.02em;

      @media (min-width: 768px) {
        font-size: 42px;
      }
    }

    .article-hook {
      font-size: 18px;
      color: #475569;
      line-height: 1.6;
      margin: 0 0 24px 0;
      font-weight: 400;
      border-left: 3px solid #3b82f6;
      padding-left: 16px;
    }

    .article-meta-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      padding: 12px 0;
      border-top: 1px solid #f1f5f9;
      border-bottom: 1px solid #f1f5f9;
      margin-bottom: 28px;
      font-size: 13px;
      color: #64748b;
    }

    .meta-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .meta-icon {
      font-size: 16px;
      width: 16px;
      height: 16px;
      color: #94a3b8;
    }

    .author-info, .read-time-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }

    .meta-dot {
      color: #cbd5e1;
    }

    .model-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      color: #6366f1;
      background-color: #eef2ff;
      padding: 4px 12px;
      border-radius: 9999px;

      .sparkle-icon {
        font-size: 14px;
        width: 14px;
        height: 14px;
      }
    }

    .article-cover-figure {
      margin: 0 0 32px 0;
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08);
      background-color: #0f172a;

      .cover-image {
        width: 100%;
        max-height: 480px;
        object-fit: cover;
        display: block;
      }

      .image-credit {
        padding: 8px 16px;
        font-size: 12px;
        color: #94a3b8;
        background-color: #f8fafc;
        text-align: right;
      }
    }

    .summary-box {
      background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
      border: 1px solid #bbf7d0;
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 32px;

      .summary-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        color: #15803d;
        letter-spacing: 0.05em;
        margin-bottom: 8px;

        .summary-icon {
          font-size: 16px;
          width: 16px;
          height: 16px;
        }
      }

      .summary-text {
        font-size: 15px;
        color: #166534;
        line-height: 1.6;
        margin: 0;
        font-weight: 500;
      }
    }

    .reactions-bar {
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 16px 20px;
      margin-bottom: 36px;
      display: flex;
      flex-direction: column;
      gap: 12px;

      @media (min-width: 640px) {
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
      }

      .reactions-label {
        font-size: 13px;
        font-weight: 600;
        color: #64748b;
      }

      .reaction-buttons {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }

      .react-btn {
        border-radius: 9999px;
        font-size: 13px;
        font-weight: 600;
        border-color: #e2e8f0;
        padding: 4px 12px;

        .reaction-count {
          margin-left: 4px;
          font-size: 12px;
          opacity: 0.7;
        }

        &.active-reaction {
          background-color: #eff6ff;
          border-color: #2563eb;
          color: #1d4ed8;
        }

        &.brain-check-btn.active-reaction {
          background-color: #f3e8ff;
          border-color: #7c3aed;
          color: #6d28d9;
        }
      }
    }

    ::ng-deep .article-body {
      color: #1e293b;
      font-size: 17px;
      line-height: 1.8;
      margin-bottom: 40px;

      h2 {
        font-size: 24px;
        font-weight: 800;
        color: #0f172a;
        margin: 36px 0 16px 0;
        letter-spacing: -0.01em;
        padding-bottom: 8px;
        border-bottom: 2px solid #f1f5f9;
      }

      h3 {
        font-size: 20px;
        font-weight: 700;
        color: #1e293b;
        margin: 28px 0 12px 0;
      }

      p {
        margin: 0 0 20px 0;
      }

      strong {
        color: #0f172a;
        font-weight: 700;
      }

      blockquote {
        margin: 28px 0;
        padding: 18px 24px;
        background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
        border-left: 4px solid #2563eb;
        border-radius: 0 14px 14px 0;
        font-style: italic;
        color: #1e40af;
        box-shadow: 0 2px 6px rgba(37, 99, 235, 0.05);

        p {
          margin: 0;
        }
      }

      ul, ol {
        margin: 0 0 24px 20px;
        padding: 0;

        li {
          margin-bottom: 8px;
          padding-left: 4px;
        }
      }

      code {
        font-size: 14px;
        background-color: #f1f5f9;
        color: #0f172a;
        padding: 2px 6px;
        border-radius: 4px;
      }
    }

    .reference-box {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 16px 20px;
      background-color: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      margin: 32px 0;
      font-size: 13px;
      color: #64748b;

      .ref-icon {
        color: #2563eb;
        font-size: 20px;
        width: 20px;
        height: 20px;
        flex-shrink: 0;
        margin-top: 2px;
      }

      .ref-content {
        a {
          color: #2563eb;
          text-decoration: underline;
          word-break: break-all;
          display: block;
          margin-top: 2px;
        }
      }
    }

    .loading-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 50vh;
      color: #64748b;
      gap: 16px;
    }
  `]
})
export class PostDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly postService = inject(PostService);
  private readonly seo = inject(SeoService);
  readonly analytics = inject(AnalyticsService);
  readonly auth = inject(AuthService);
  readonly isYouTubeId = isYouTubeId;

  post = signal<Post | null>(null);
  reactionTallies = signal<ReactionTally>({ LIKE: 0, MIND_BLOWN: 0, INSIGHTFUL: 0, BRAIN_CHECK: 0 });
  userReaction = signal<ReactionType | null>(null);

  get coverUrl(): string {
    return resolveUniqueCoverUrl(this.post()!);
  }

  get postViews(): number {
    const p = this.post();
    if (!p) return 0;
    const totalReactions =
      (this.reactionTallies().LIKE || 0) +
      (this.reactionTallies().MIND_BLOWN || 0) +
      (this.reactionTallies().INSIGHTFUL || 0) +
      (this.reactionTallies().BRAIN_CHECK || 0);
    return this.analytics.getViewsForPost(p.slug, totalReactions || p._count?.reactions || 0, p._count?.comments || 0);
  }

  get formattedHtml(): string {
    const p = this.post();
    if (!p || !p.contentMarkdown) return '';
    return this.parseMarkdown(p.contentMarkdown);
  }

  get estimatedReadingTime(): number {
    const text = this.post()?.contentMarkdown || '';
    const wordCount = text.split(/\s+/).length;
    return Math.max(1, Math.ceil(wordCount / 200));
  }

  ngOnInit(): void {
    this.analytics.loadVisibilitySummary();
    this.route.paramMap.subscribe(params => {
      const slug = params.get('slug');
      if (slug) {
        this.loadPost(slug);
      }
    });
  }

  loadPost(slug: string): void {
    this.postService.getPostBySlug(slug).subscribe(p => {
      this.post.set(p);
      if (p) {
        this.seo.setPostSeo(p);
        this.analytics.trackPageView(`/posts/${p.slug}`, p.slug);
        this.loadReactions(p.id);
      }
    });
  }

  loadReactions(postId: string): void {
    this.postService.getReactions(postId).subscribe(res => {
      this.reactionTallies.set(res.tallies);
      this.userReaction.set(res.userReaction);
    });
  }

  onReact(type: ReactionType): void {
    const p = this.post();
    if (!p) return;

    this.analytics.trackEvent('post_reaction', { slug: p.slug, type });
    this.postService.toggleReaction(p.id, type).subscribe(() => {
      this.loadReactions(p.id);
    });
  }

  onImageError(event: Event): void {
    const target = event.target as HTMLImageElement;
    const p = this.post();
    target.src = resolveUniqueCoverUrl({ slug: (p?.slug || 'fallback') + '-alt', title: p?.title || '' });
  }

  private parseMarkdown(md: string): string {
    const lines = md.split('\n');
    const result: string[] = [];
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
      let line = lines[i].trim();

      if (!line) {
        if (inList) {
          result.push('</ul>');
          inList = false;
        }
        continue;
      }

      // Headers
      if (line.startsWith('### ')) {
        if (inList) { result.push('</ul>'); inList = false; }
        result.push(`<h3>${this.inlineFormat(line.slice(4))}</h3>`);
        continue;
      }
      if (line.startsWith('## ')) {
        if (inList) { result.push('</ul>'); inList = false; }
        result.push(`<h2>${this.inlineFormat(line.slice(3))}</h2>`);
        continue;
      }

      // Blockquotes
      if (line.startsWith('> ')) {
        if (inList) { result.push('</ul>'); inList = false; }
        result.push(`<blockquote><p>${this.inlineFormat(line.slice(2))}</p></blockquote>`);
        continue;
      }

      // Bullet lists
      if (line.startsWith('- ') || line.startsWith('* ')) {
        if (!inList) {
          result.push('<ul>');
          inList = true;
        }
        result.push(`<li>${this.inlineFormat(line.slice(2))}</li>`);
        continue;
      }

      if (inList) {
        result.push('</ul>');
        inList = false;
      }

      // Paragraphs
      result.push(`<p>${this.inlineFormat(line)}</p>`);
    }

    if (inList) {
      result.push('</ul>');
    }

    return result.join('\n');
  }

  private inlineFormat(text: string): string {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }
}

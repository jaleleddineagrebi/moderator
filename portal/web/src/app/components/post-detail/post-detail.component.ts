import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatBadgeModule } from '@angular/material/badge';
import { Post, ReactionTally, ReactionType } from '../../models/post.model';
import { PostService } from '../../services/post.service';
import { AuthService } from '../../services/auth.service';
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
    MatChipsModule,
    MatProgressSpinnerModule,
    MatBadgeModule,
    YouTubeShortCardComponent,
    CommentSectionComponent
  ],
  template: `
    <div class="post-detail-container container" *ngIf="post(); else loadingState">
      <!-- Breadcrumb -->
      <nav class="breadcrumb">
        <a routerLink="/">Home</a>
        <mat-icon class="bc-arrow">chevron_right</mat-icon>
        <span class="bc-current">Article</span>
      </nav>

      <!-- Category Tags -->
      <div class="tags-wrapper">
        <mat-chip-set>
          <mat-chip *ngFor="let tag of post()!.tags" class="detail-tag">
            #{{ tag }}
          </mat-chip>
        </mat-chip-set>
      </div>

      <!-- Article Header -->
      <h1 class="article-title">{{ post()!.title }}</h1>

      <p class="article-hook">{{ post()!.hook }}</p>

      <div class="article-meta-bar">
        <div class="author-info">
          <mat-icon class="author-icon">psychology</mat-icon>
          <span>Published on {{ post()!.publishedAt | date:'longDate' }}</span>
        </div>
        <div class="model-badge">
          <span>Synthesized with {{ post()!.aiModelUsed || 'Frontier AI' }}</span>
        </div>
      </div>

      <!-- Cover Image -->
      <figure class="article-cover-figure">
        <img [src]="post()!.coverImageUrl" [alt]="post()!.title" class="cover-image" />
        <figcaption *ngIf="post()!.imageCredit" class="image-credit">
          {{ post()!.imageCredit }}
        </figcaption>
      </figure>

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

      <!-- Markdown Body -->
      <div class="article-body" [innerHTML]="formatContent(post()!.contentMarkdown)"></div>

      <!-- Companion YouTube Short Video Card -->
      <app-youtube-short-card
        *ngIf="post()!.youtubeShort"
        [short]="post()!.youtubeShort!"
        [postTitle]="post()!.title"
      ></app-youtube-short-card>

      <!-- Scientific Reference Citation -->
      <div *ngIf="post()!.sourceUrls.length > 0" class="reference-box">
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
        <mat-spinner diameter="48"></mat-spinner>
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
      font-size: 14px;
      color: #64748b;
      margin-bottom: 20px;

      a {
        color: #64748b;
        text-decoration: none;
        &:hover { color: #2563eb; }
      }

      .bc-arrow {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }

      .bc-current {
        color: #0f172a;
        font-weight: 500;
      }
    }

    .tags-wrapper {
      margin-bottom: 16px;

      .detail-tag {
        font-size: 12px;
        font-weight: 700;
        background-color: #eff6ff;
        color: #1e40af;
      }
    }

    .article-title {
      font-size: 36px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.25;
      margin: 0 0 16px 0;

      @media (min-width: 768px) {
        font-size: 44px;
      }
    }

    .article-hook {
      font-size: 20px;
      font-weight: 500;
      color: #475569;
      line-height: 1.6;
      margin: 0 0 24px 0;
    }

    .article-meta-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 0;
      border-top: 1px solid #e2e8f0;
      border-bottom: 1px solid #e2e8f0;
      font-size: 13px;
      color: #64748b;
      margin-bottom: 32px;
    }

    .author-info {
      display: flex;
      align-items: center;
      gap: 8px;

      .author-icon {
        font-size: 20px;
        width: 20px;
        height: 20px;
        color: #3b82f6;
      }
    }

    .model-badge {
      font-size: 12px;
      color: #94a3b8;
    }

    .article-cover-figure {
      margin: 0 0 36px 0;
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.08);
      background-color: #0f172a;
    }

    .cover-image {
      width: 100%;
      max-height: 480px;
      object-fit: cover;
      display: block;
    }

    .image-credit {
      padding: 8px 16px;
      text-align: right;
      font-size: 12px;
      color: #94a3b8;
      background-color: #ffffff;
    }

    .reactions-bar {
      background-color: #ffffff;
      border-radius: 16px;
      padding: 16px 20px;
      margin-bottom: 36px;
      border: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      gap: 12px;

      @media (min-width: 600px) {
        flex-direction: row;
        align-items: center;
        justify-content: space-between;
      }
    }

    .reactions-label {
      font-size: 14px;
      font-weight: 600;
      color: #334155;
    }

    .reaction-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .react-btn {
      border-radius: 12px;
      font-size: 13px;
      font-weight: 600;

      &.active-reaction {
        background-color: #eff6ff;
        border-color: #3b82f6;
        color: #1d4ed8;
      }
    }

    .brain-check-btn.active-reaction {
      background-color: #fef2f2;
      border-color: #ef4444;
      color: #b91c1c;
    }

    .reaction-count {
      margin-left: 4px;
      font-size: 12px;
      opacity: 0.8;
    }

    .article-body {
      font-size: 18px;
      line-height: 1.75;
      color: #1e293b;
      margin-bottom: 40px;

      ::ng-deep h2 {
        font-size: 26px;
        font-weight: 700;
        color: #0f172a;
        margin-top: 36px;
        margin-bottom: 16px;
      }

      ::ng-deep p {
        margin-bottom: 20px;
      }
    }

    .reference-box {
      display: flex;
      gap: 12px;
      background-color: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 16px;
      margin: 32px 0;

      .ref-icon {
        color: #3b82f6;
      }

      .ref-content {
        font-size: 13px;
        color: #475569;

        a {
          display: block;
          color: #2563eb;
          text-decoration: underline;
          word-break: break-all;
          margin-top: 4px;
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
  readonly auth = inject(AuthService);

  post = signal<Post | null>(null);
  reactionTallies = signal<ReactionTally>({ LIKE: 0, MIND_BLOWN: 0, INSIGHTFUL: 0, BRAIN_CHECK: 0 });
  userReaction = signal<ReactionType | null>(null);

  ngOnInit(): void {
    const slug = this.route.snapshot.paramMap.get('slug');
    if (slug) {
      this.loadPost(slug);
    }
  }

  loadPost(slug: string): void {
    this.postService.getPostBySlug(slug).subscribe(p => {
      this.post.set(p);
      if (p) {
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

    this.postService.toggleReaction(p.id, type).subscribe(() => {
      this.loadReactions(p.id);
    });
  }

  formatContent(md: string): string {
    return md
      .replace(/## (.*)/g, '<h2>$1</h2>')
      .replace(/\n\n/g, '<p></p>')
      .replace(/\n/g, '<br/>');
  }
}

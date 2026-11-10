import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { Post, hasPlayableShort, resolveUniqueCoverUrl } from '../../models/post.model';
import { AnalyticsService } from '../../services/analytics.service';

@Component({
  selector: 'app-post-card',
  standalone: true,
  imports: [CommonModule, RouterModule, MatCardModule, MatButtonModule, MatIconModule],
  template: `
    <mat-card class="feed-post-card mat-elevation-z2 hover-elevation">
      <!-- Cover Image with Aspect Ratio -->
      <div class="card-image-wrapper" [routerLink]="['/posts', post.slug]">
        <img
          *ngIf="!imageFailed && coverUrl; else fallbackVisual"
          mat-card-image
          [src]="coverUrl"
          [alt]="post.title"
          class="cover-img"
          loading="lazy"
          (error)="onImageError()"
        />
        <ng-template #fallbackVisual>
          <div class="fallback-cover">
            <mat-icon class="fallback-icon">psychology</mat-icon>
            <span class="fallback-tag">Cognitive Science & AI</span>
          </div>
        </ng-template>
        <div class="image-overlay-chips">
          <span *ngFor="let tag of (post.tags || []).slice(0, 2)" class="tag-chip">#{{ tag }}</span>
        </div>
      </div>

      <mat-card-content class="card-content">
        <div class="card-meta">
          <div class="meta-left">
            <span class="meta-date">{{ post.publishedAt | date:'mediumDate' }}</span>
            <span class="meta-dot">•</span>
            <span class="meta-read-time">
              <mat-icon class="time-icon">schedule</mat-icon>
              <span>{{ estimatedReadingTime }} min read</span>
            </span>
          </div>
          <a *ngIf="hasShort" class="short-indicator" [routerLink]="['/posts', post.slug]" fragment="short"
             title="Watch the companion YouTube Short">
            <mat-icon class="yt-icon">smart_display</mat-icon>
            <span>Watch Short</span>
          </a>
        </div>

        <h2 class="post-title" [routerLink]="['/posts', post.slug]">
          {{ post.title }}
        </h2>

        <p class="post-hook">
          {{ post.hook }}
        </p>
      </mat-card-content>

      <mat-card-actions class="card-footer">
        <a mat-button color="primary" [routerLink]="['/posts', post.slug]" class="read-btn">
          <span>Read Reflection</span>
          <mat-icon>arrow_forward</mat-icon>
        </a>

        <div class="stats-group">
          <span class="stat-item" title="Article Views">
            <mat-icon class="stat-icon">visibility</mat-icon>
            <span>{{ postViews }}</span>
          </span>
          <span class="stat-item" *ngIf="post._count" title="Reader Reactions">
            <mat-icon class="stat-icon">favorite_border</mat-icon>
            <span>{{ post._count.reactions || 0 }}</span>
          </span>
          <span class="stat-item" *ngIf="post._count" title="Comments">
            <mat-icon class="stat-icon">chat_bubble_outline</mat-icon>
            <span>{{ post._count.comments || 0 }}</span>
          </span>
        </div>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .feed-post-card {
      border-radius: 20px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      height: 100%;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.25s ease;
    }

    .hover-elevation:hover {
      transform: translateY(-4px);
      box-shadow: 0 12px 24px -6px rgba(0, 0, 0, 0.12);
    }

    .card-image-wrapper {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      cursor: pointer;
      overflow: hidden;
      background-color: #0f172a;
    }

    .cover-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      margin: 0 !important;
      transition: transform 0.4s ease;
    }

    .card-image-wrapper:hover .cover-img {
      transform: scale(1.04);
    }

    .fallback-cover {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #312e81 100%);
      color: #93c5fd;
      gap: 8px;

      .fallback-icon {
        font-size: 40px;
        width: 40px;
        height: 40px;
        opacity: 0.8;
      }

      .fallback-tag {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.9;
      }
    }

    /* Plain labels, not mat-chip: Material chips ignore a custom text colour and rendered dark text on this dark pill */
    .image-overlay-chips {
      position: absolute;
      bottom: 12px;
      left: 12px;
      right: 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      pointer-events: none;

      .tag-chip {
        display: inline-flex;
        align-items: center;
        height: 28px;
        padding: 0 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        line-height: 1;
        letter-spacing: 0.01em;
        background-color: rgba(15, 23, 42, 0.88);
        color: #ffffff;
        backdrop-filter: blur(4px);
        white-space: nowrap;
      }
    }

    .card-content {
      padding: 20px 20px 8px 20px;
      flex: 1;
    }

    .card-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }

    .meta-left {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .meta-date {
      font-size: 12px;
      color: #94a3b8;
      font-weight: 500;
    }

    .meta-dot {
      color: #cbd5e1;
      font-size: 12px;
    }

    .meta-read-time {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      font-size: 12px;
      color: #64748b;
      font-weight: 500;

      .time-icon {
        font-size: 14px;
        width: 14px;
        height: 14px;
      }
    }

    .short-indicator {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 700;
      color: #dc2626;
      text-decoration: none;
      cursor: pointer;

      &:hover {
        text-decoration: underline;
      }

      .yt-icon {
        font-size: 14px;
        width: 14px;
        height: 14px;
      }
    }

    .post-title {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      line-height: 1.35;
      margin: 0 0 10px 0;
      cursor: pointer;

      &:hover {
        color: #2563eb;
      }
    }

    .post-hook {
      font-size: 14px;
      color: #64748b;
      line-height: 1.6;
      margin: 0;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .card-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 20px 16px 20px;
      border-top: 1px solid #f1f5f9;
    }

    .read-btn {
      font-weight: 600;
      border-radius: 10px;

      mat-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
        margin-left: 4px;
      }
    }

    .stats-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .stat-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 13px;
      color: #64748b;

      .stat-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
    }
  `]
})
export class PostCardComponent {
  @Input({ required: true }) post!: Post;
  private readonly analytics = inject(AnalyticsService);
  imageFailed = false;

  get coverUrl(): string {
    return resolveUniqueCoverUrl(this.post);
  }

  get postViews(): number {
    return this.analytics.getViewsForPost(
      this.post?.slug || '',
      this.post?._count?.reactions || 0,
      this.post?._count?.comments || 0
    );
  }

  get hasShort(): boolean {
    return hasPlayableShort(this.post);
  }

  get estimatedReadingTime(): number {
    const text = this.post?.contentMarkdown || this.post?.summary || this.post?.hook || '';
    const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
    return Math.max(2, Math.ceil(wordCount / 180));
  }

  onImageError(): void {
    this.imageFailed = true;
  }
}


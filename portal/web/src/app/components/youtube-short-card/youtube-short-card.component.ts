import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { YouTubeShort } from '../../models/post.model';
import { AnalyticsService } from '../../services/analytics.service';

@Component({
  selector: 'app-youtube-short-card',
  standalone: true,
  imports: [CommonModule, MatCardModule, MatButtonModule, MatIconModule, MatChipsModule],
  template: `
    <mat-card class="youtube-short-card mat-elevation-z2">
      <div class="card-top-bar">
        <div class="card-header-badge">
          <mat-icon class="pulse-icon">auto_awesome</mat-icon>
          <span>Companion 45s YouTube Short</span>
        </div>
        <div class="bias-pill">🧠 DAILY BRAIN BIAS CHECK</div>
      </div>

      <h3 class="short-title">{{ short.title }}</h3>

      <p *ngIf="short.hookAngle" class="short-subtitle">
        "{{ short.hookAngle }}"
      </p>

      <!-- 9:16 Vertical Video Container -->
      <div class="vertical-video-wrapper">
        <ng-container *ngIf="isPlaying; else thumbnailView">
          <iframe
            [src]="safeEmbedUrl"
            title="YouTube Short"
            class="video-iframe"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
          </iframe>
        </ng-container>

        <ng-template #thumbnailView>
          <div class="thumbnail-container" (click)="playVideo()">
            <!-- Thumbnail background with graceful gradient fallback -->
            <div class="fallback-gradient-bg">
              <div class="vertical-graphic">
                <mat-icon class="large-bg-icon">psychology</mat-icon>
                <div class="graphic-title">{{ short.title }}</div>
              </div>
            </div>

            <img
              *ngIf="thumbnailAvailable"
              [src]="thumbnailUrl"
              [alt]="short.title"
              (error)="onThumbnailError()"
              class="thumbnail-image"
              loading="lazy"
            />

            <div class="gradient-overlay"></div>

            <div class="play-overlay-center">
              <button mat-fab color="warn" class="play-fab" aria-label="Play Short">
                <mat-icon class="play-icon">play_arrow</mat-icon>
              </button>
              <span class="click-to-play-text">Click to Play 45s Short</span>
            </div>
          </div>
        </ng-template>
      </div>

      <mat-card-actions class="card-actions">
        <a
          mat-flat-button
          color="warn"
          [href]="short.youtubeUrl"
          target="_blank"
          rel="noopener noreferrer"
          (click)="onOpenExternal()"
          class="yt-btn"
        >
          <mat-icon>smart_display</mat-icon>
          <span>Watch on YouTube</span>
          <mat-icon class="launch-icon">open_in_new</mat-icon>
        </a>

        <span class="cta-note">
          Follow for your daily cognitive bias check
        </span>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .youtube-short-card {
      margin: 36px 0;
      padding: 24px;
      border-radius: 20px;
      background: linear-gradient(135deg, #f8fafc 0%, #ffffff 50%, #eff6ff 100%);
      border: 1px solid #e2e8f0;
      overflow: hidden;
    }

    .card-top-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }

    .card-header-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #2563eb;
      background-color: #dbeafe;
      padding: 4px 12px;
      border-radius: 9999px;

      .pulse-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
    }

    .bias-pill {
      font-size: 11px;
      font-weight: 800;
      color: #7c3aed;
      background-color: #f3e8ff;
      padding: 4px 10px;
      border-radius: 9999px;
      letter-spacing: 0.04em;
    }

    .short-title {
      font-size: 22px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.3;
      margin: 0 0 6px 0;
    }

    .short-subtitle {
      font-size: 14px;
      color: #64748b;
      font-style: italic;
      line-height: 1.5;
      margin: 0 0 20px 0;
    }

    .vertical-video-wrapper {
      position: relative;
      width: 100%;
      max-width: 340px;
      margin: 0 auto 20px auto;
      aspect-ratio: 9 / 16;
      border-radius: 16px;
      overflow: hidden;
      background-color: #0f172a;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
    }

    .video-iframe {
      width: 100%;
      height: 100%;
      border: 0;
    }

    .thumbnail-container {
      position: relative;
      width: 100%;
      height: 100%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .fallback-gradient-bg {
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      text-align: center;
    }

    .vertical-graphic {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
      z-index: 1;

      .large-bg-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        color: #3b82f6;
        opacity: 0.8;
      }

      .graphic-title {
        color: #f8fafc;
        font-size: 16px;
        font-weight: 700;
        line-height: 1.4;
      }
    }

    .thumbnail-image {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      transition: transform 0.4s ease;
      z-index: 2;
    }

    .thumbnail-container:hover .thumbnail-image {
      transform: scale(1.03);
    }

    .gradient-overlay {
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(0, 0, 0, 0.2) 0%, rgba(0, 0, 0, 0.6) 100%);
      z-index: 3;
    }

    .play-overlay-center {
      position: absolute;
      z-index: 4;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;

      .play-fab {
        width: 64px;
        height: 64px;
        box-shadow: 0 4px 16px rgba(220, 38, 38, 0.5);
        transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
        display: flex;
        align-items: center;
        justify-content: center;

        .play-icon {
          font-size: 32px;
          width: 32px;
          height: 32px;
        }
      }

      .click-to-play-text {
        color: #ffffff;
        font-size: 13px;
        font-weight: 600;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.6);
      }
    }

    .thumbnail-container:hover .play-fab {
      transform: scale(1.1);
    }

    .card-actions {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
      padding: 12px 0 0 0;
      border-top: 1px solid #f1f5f9;

      @media (min-width: 640px) {
        flex-direction: row;
        justify-content: space-between;
      }
    }

    .yt-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 18px;
      border-radius: 12px;
      font-weight: 600;
      letter-spacing: -0.01em;

      .launch-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
        opacity: 0.8;
      }
    }

    .cta-note {
      font-size: 13px;
      color: #64748b;
      font-weight: 500;
    }
  `]
})
export class YouTubeShortCardComponent {
  @Input({ required: true }) short!: YouTubeShort;
  @Input() postTitle = '';

  private readonly sanitizer = inject(DomSanitizer);
  private readonly analytics = inject(AnalyticsService);

  isPlaying = false;
  thumbnailAvailable = true;

  get safeEmbedUrl(): SafeResourceUrl {
    const base = this.short.embedUrl || `https://www.youtube.com/embed/${this.short.id}`;
    const url = `${base}?autoplay=1&mute=0&rel=0&loop=1`;
    return this.sanitizer.bypassSecurityTrustResourceUrl(url);
  }

  get thumbnailUrl(): string {
    return `https://img.youtube.com/vi/${this.short.id}/hqdefault.jpg`;
  }

  onThumbnailError(): void {
    this.thumbnailAvailable = false;
  }

  playVideo(): void {
    this.isPlaying = true;
    this.analytics.trackEvent('youtube_short_click', {
      shortId: this.short.id,
      postTitle: this.postTitle,
      action: 'play_inline'
    });
  }

  onOpenExternal(): void {
    this.analytics.trackEvent('youtube_short_click', {
      shortId: this.short.id,
      postTitle: this.postTitle,
      action: 'open_youtube_external'
    });
  }
}

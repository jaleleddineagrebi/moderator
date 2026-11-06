import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
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
    <mat-card class="youtube-short-card mat-elevation-z3">
      <div class="card-header-badge">
        <mat-icon class="pulse-icon">auto_awesome</mat-icon>
        <span>Companion 45s YouTube Short</span>
      </div>

      <mat-card-title class="short-title">{{ short.title }}</mat-card-title>
      
      <mat-card-subtitle *ngIf="short.hookAngle" class="short-subtitle">
        {{ short.hookAngle }}
      </mat-card-subtitle>

      <!-- 9:16 Vertical Video Container -->
      <div class="vertical-video-wrapper">
        <ng-container *ngIf="isPlaying; else thumbnailView">
          <iframe
            [src]="embedUrl"
            title="YouTube Short"
            class="video-iframe"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen>
          </iframe>
        </ng-container>

        <ng-template #thumbnailView>
          <div class="thumbnail-container" (click)="playVideo()">
            <img
              [src]="'https://img.youtube.com/vi/' + short.id + '/hqdefault.jpg'"
              [alt]="short.title"
              class="thumbnail-image"
              loading="lazy"
            />
            <div class="gradient-overlay"></div>
            
            <div class="bias-check-pill">
              🧠 DAILY BRAIN BIAS CHECK
            </div>

            <button mat-fab color="warn" class="play-fab" aria-label="Play Short">
              <mat-icon>play_arrow</mat-icon>
            </button>
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
          <span>Watch & Subscribe on YouTube</span>
          <mat-icon class="launch-icon">open_in_new</mat-icon>
        </a>

        <span class="cta-note">
          ⚡ Follow for your daily brain bias check
        </span>
      </mat-card-actions>
    </mat-card>
  `,
  styles: [`
    .youtube-short-card {
      margin: 32px 0;
      padding: 24px;
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(239, 246, 255, 0.7) 0%, #ffffff 50%, rgba(243, 232, 255, 0.5) 100%);
      border: 1px solid rgba(191, 219, 254, 0.6);
    }

    .card-header-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #0284c7;
      margin-bottom: 8px;

      mat-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
    }

    .short-title {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      line-height: 1.3;
    }

    .short-subtitle {
      font-size: 14px;
      color: #64748b;
      margin-top: 4px;
    }

    .vertical-video-wrapper {
      position: relative;
      margin: 16px auto;
      width: 100%;
      max-width: 280px;
      aspect-ratio: 9 / 16;
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
      background-color: #020617;
    }

    .video-iframe {
      width: 100%;
      height: 100%;
      border: none;
    }

    .thumbnail-container {
      position: relative;
      width: 100%;
      height: 100%;
      cursor: pointer;
    }

    .thumbnail-image {
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0.85;
      transition: opacity 0.2s ease;
    }

    .thumbnail-container:hover .thumbnail-image {
      opacity: 1;
    }

    .gradient-overlay {
      position: absolute;
      inset: 0;
      background: linear-gradient(to top, rgba(0, 0, 0, 0.8) 0%, transparent 50%, rgba(0, 0, 0, 0.4) 100%);
    }

    .bias-check-pill {
      position: absolute;
      top: 14px;
      left: 12px;
      right: 12px;
      padding: 6px 12px;
      border-radius: 9999px;
      background-color: rgba(220, 38, 38, 0.95);
      color: #ffffff;
      font-size: 11px;
      font-weight: 800;
      text-align: center;
      letter-spacing: 0.05em;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .play-fab {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .thumbnail-container:hover .play-fab {
      transform: translate(-50%, -50%) scale(1.1);
    }

    .card-actions {
      display: flex;
      flex-direction: column;
      gap: 12px;
      align-items: center;
      margin-top: 16px;
      padding: 0;

      @media (min-width: 600px) {
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

  private readonly analytics = inject(AnalyticsService);
  isPlaying = false;

  get embedUrl(): string {
    return `${this.short.embedUrl}?autoplay=1&mute=0&rel=0&loop=1`;
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


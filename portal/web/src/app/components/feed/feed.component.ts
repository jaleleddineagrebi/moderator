import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Post, hasPlayableShort } from '../../models/post.model';
import { PostService } from '../../services/post.service';
import { PostCardComponent } from '../post-card/post-card.component';

@Component({
  selector: 'app-feed',
  standalone: true,
  imports: [CommonModule, MatChipsModule, MatIconModule, MatProgressSpinnerModule, PostCardComponent],
  template: `
    <div class="feed-page container">
      <!-- Hero Banner -->
      <header class="hero-section">
        <div class="hero-badge">
          <mat-icon class="badge-icon">psychology_alt</mat-icon>
          <span>Daily Cognitive Science & Machine Intelligence</span>
        </div>
        <h1 class="hero-title">
          Where <span class="text-gradient">Psychology</span> Meets <span class="text-gradient">Artificial Intelligence</span>
        </h1>
        <p class="hero-description">
          Daily curated research exploring cognitive biases, mental models, and the behavioral frontier of human-AI teaming.
        </p>

        <!-- Topic Chips Filter -->
        <div class="filter-chips">
          <mat-chip-set>
            <mat-chip-option
              *ngFor="let topic of topics"
              [selected]="selectedTopic() === topic"
              (selectionChange)="onSelectTopic(topic)"
              class="topic-chip"
            >
              {{ topic }}
            </mat-chip-option>
          </mat-chip-set>
        </div>
      </header>

      <!-- Articles Grid -->
      <main class="posts-grid-section">
        <ng-container *ngIf="!isLoading(); else loadingState">
          <div *ngIf="filteredPosts().length > 0; else emptyState" class="posts-grid">
            <app-post-card
              *ngFor="let post of filteredPosts()"
              [post]="post"
            ></app-post-card>
          </div>

          <ng-template #emptyState>
            <div class="empty-feed">
              <mat-icon class="empty-icon">search_off</mat-icon>
              <h3>No articles found</h3>
              <p>Check back after today's automated daily AI publication schedule!</p>
            </div>
          </ng-template>
        </ng-container>

        <ng-template #loadingState>
          <div class="loading-container">
            <mat-spinner diameter="44"></mat-spinner>
            <p>Gathering cognitive insights...</p>
          </div>
        </ng-template>
      </main>
    </div>
  `,
  styles: [`
    .feed-page {
      padding: 40px 16px 80px 16px;
    }

    .hero-section {
      text-align: center;
      max-width: 800px;
      margin: 0 auto 48px auto;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #2563eb;
      background-color: #eff6ff;
      padding: 6px 16px;
      border-radius: 9999px;
      margin-bottom: 20px;

      .badge-icon {
        font-size: 18px;
        width: 18px;
        height: 18px;
      }
    }

    .hero-title {
      font-size: 38px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.2;
      letter-spacing: -0.02em;
      margin: 0 0 16px 0;

      @media (min-width: 768px) {
        font-size: 52px;
      }
    }

    .text-gradient {
      background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 50%, #7c3aed 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-description {
      font-size: 18px;
      color: #64748b;
      line-height: 1.6;
      margin: 0 0 32px 0;
    }

    .filter-chips {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;

      .topic-chip {
        font-weight: 600;
        font-size: 13px;
      }
    }

    .posts-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 28px;

      @media (min-width: 640px) {
        grid-template-columns: repeat(2, 1fr);
      }

      @media (min-width: 1024px) {
        grid-template-columns: repeat(3, 1fr);
      }
    }

    .empty-feed {
      text-align: center;
      padding: 60px 16px;
      color: #64748b;

      .empty-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
        color: #94a3b8;
        margin-bottom: 12px;
      }

      h3 {
        font-size: 20px;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 6px;
      }
    }

    .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 40vh;
      color: #64748b;
      gap: 16px;
    }
  `]
})
export class FeedComponent implements OnInit {
  private readonly postService = inject(PostService);
  private readonly route = inject(ActivatedRoute);

  readonly topics = ['All Insights', 'YouTube Shorts', 'Cognitive Bias', 'Human-AI Teaming', 'Neuroscience', 'Habits'];
  selectedTopic = signal<string>('All Insights');
  posts = signal<Post[]>([]);
  isLoading = signal<boolean>(true);

  ngOnInit(): void {
    if (this.route.snapshot.routeConfig?.path === 'shorts') {
      this.selectedTopic.set('YouTube Shorts');
    }
    this.route.queryParams.subscribe(params => {
      if (params['filter'] === 'shorts') {
        this.selectedTopic.set('YouTube Shorts');
      }
    });
    this.loadPosts();
  }

  loadPosts(): void {
    this.isLoading.set(true);
    this.postService.getPosts(1, 20).subscribe({
      next: (res) => {
        this.posts.set(res.data);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
      }
    });
  }

  onSelectTopic(topic: string): void {
    this.selectedTopic.set(topic);
  }

  filteredPosts(): Post[] {
    const topic = this.selectedTopic();
    if (topic === 'All Insights') {
      return this.posts();
    }
    if (topic === 'YouTube Shorts') {
      return this.posts().filter(p => hasPlayableShort(p));
    }
    return this.posts().filter(p => p.tags.some(t => t.toLowerCase().includes(topic.toLowerCase())));
  }
}


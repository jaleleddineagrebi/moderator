import { Component, Input, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog } from '@angular/material/dialog';
import { Comment } from '../../models/post.model';
import { PostService } from '../../services/post.service';
import { AuthService } from '../../services/auth.service';
import { AuthDialogComponent } from '../auth-dialog/auth-dialog.component';

@Component({
  selector: 'app-comment-section',
  standalone: true,
  imports: [CommonModule, FormsModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule],
  template: `
    <section class="comments-section">
      <div class="section-header">
        <mat-icon color="primary">forum</mat-icon>
        <h3 class="section-title">Discussion & Community Reflections</h3>
        <span class="count-badge">({{ comments().length }})</span>
      </div>

      <!-- Add Comment Box -->
      <div class="comment-input-card">
        <ng-container *ngIf="auth.isAuthenticated(); else authPrompt">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Share your psychological perspective or question...</mat-label>
            <textarea
              matInput
              [(ngModel)]="newCommentText"
              rows="3"
              maxlength="2000"
              placeholder="What cognitive bias or pattern have you observed?"
            ></textarea>
            <mat-hint align="end">{{ newCommentText.length }}/2000</mat-hint>
          </mat-form-field>

          <div class="submit-row">
            <button
              mat-flat-button
              color="primary"
              [disabled]="newCommentText.trim().length < 2 || isSubmitting"
              (click)="submitComment()"
            >
              <mat-icon>send</mat-icon>
              <span>Post Comment</span>
            </button>
          </div>
        </ng-container>

        <ng-template #authPrompt>
          <div class="guest-banner">
            <mat-icon class="guest-icon">lock</mat-icon>
            <div class="guest-text">
              <strong>Join the conversation</strong>
              <p>Sign in with Google or Facebook to share your reflection on this topic.</p>
            </div>
            <button mat-stroked-button color="primary" (click)="openAuthDialog()">
              Sign In
            </button>
          </div>
        </ng-template>
      </div>

      <!-- Comments List -->
      <div class="comments-list">
        <div *ngFor="let comment of comments()" class="comment-thread">
          <div class="comment-bubble">
            <div class="comment-avatar">
              <img
                *ngIf="comment.user.image; else defaultAvatar"
                [src]="comment.user.image"
                [alt]="comment.user.name || 'User'"
              />
              <ng-template #defaultAvatar>
                <div class="avatar-placeholder">
                  {{ (comment.user.name || 'U')[0].toUpperCase() }}
                </div>
              </ng-template>
            </div>

            <div class="comment-body">
              <div class="comment-meta">
                <span class="author-name">{{ comment.user.name || 'Anonymous Thinker' }}</span>
                <span class="comment-date">{{ comment.createdAt | date:'mediumDate' }}</span>
              </div>
              <p class="comment-text">{{ comment.content }}</p>
            </div>
          </div>

          <!-- Nested Replies (1 level) -->
          <div *ngIf="comment.replies && comment.replies.length > 0" class="replies-wrapper">
            <div *ngFor="let reply of comment.replies" class="comment-bubble reply-bubble">
              <div class="comment-avatar small-avatar">
                <div class="avatar-placeholder">
                  {{ (reply.user.name || 'U')[0].toUpperCase() }}
                </div>
              </div>
              <div class="comment-body">
                <div class="comment-meta">
                  <span class="author-name">{{ reply.user.name || 'Contributor' }}</span>
                  <span class="comment-date">{{ reply.createdAt | date:'shortDate' }}</span>
                </div>
                <p class="comment-text">{{ reply.content }}</p>
              </div>
            </div>
          </div>
        </div>

        <div *ngIf="comments().length === 0" class="empty-state">
          <mat-icon class="empty-icon">chat_bubble_outline</mat-icon>
          <p>No reflections yet. Be the first to share your thoughts!</p>
        </div>
      </div>
    </section>
  `,
  styles: [`
    .comments-section {
      margin-top: 48px;
      padding-top: 32px;
      border-top: 1px solid #e2e8f0;
    }

    .section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 24px;
    }

    .section-title {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      margin: 0;
    }

    .count-badge {
      font-size: 15px;
      color: #64748b;
      font-weight: 600;
    }

    .comment-input-card {
      background-color: #ffffff;
      border-radius: 16px;
      padding: 20px;
      border: 1px solid #e2e8f0;
      margin-bottom: 32px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }

    .full-width {
      width: 100%;
    }

    .submit-row {
      display: flex;
      justify-content: flex-end;
      margin-top: 8px;
    }

    .guest-banner {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
      text-align: center;
      padding: 12px 0;

      @media (min-width: 600px) {
        flex-direction: row;
        text-align: left;
      }
    }

    .guest-icon {
      font-size: 32px;
      width: 32px;
      height: 32px;
      color: #3b82f6;
    }

    .guest-text {
      flex: 1;

      strong {
        font-size: 16px;
        color: #0f172a;
      }

      p {
        font-size: 14px;
        color: #64748b;
        margin: 4px 0 0 0;
      }
    }

    .comment-thread {
      margin-bottom: 24px;
    }

    .comment-bubble {
      display: flex;
      gap: 14px;
      background-color: #ffffff;
      border-radius: 16px;
      padding: 16px;
      border: 1px solid #f1f5f9;
    }

    .reply-bubble {
      margin-top: 12px;
      margin-left: 40px;
      background-color: #f8fafc;
    }

    .comment-avatar {
      flex-shrink: 0;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      overflow: hidden;

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
    }

    .small-avatar {
      width: 32px;
      height: 32px;
    }

    .avatar-placeholder {
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 14px;
    }

    .comment-body {
      flex: 1;
    }

    .comment-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }

    .author-name {
      font-weight: 600;
      font-size: 14px;
      color: #1e293b;
    }

    .comment-date {
      font-size: 12px;
      color: #94a3b8;
    }

    .comment-text {
      font-size: 15px;
      line-height: 1.5;
      color: #334155;
      margin: 0;
    }

    .empty-state {
      text-align: center;
      padding: 40px 16px;
      color: #94a3b8;

      .empty-icon {
        font-size: 40px;
        width: 40px;
        height: 40px;
        margin-bottom: 8px;
      }
    }
  `]
})
export class CommentSectionComponent {
  @Input({ required: true }) postId!: string;

  private readonly postService = inject(PostService);
  readonly auth = inject(AuthService);
  private readonly dialog = inject(MatDialog);

  comments = signal<Comment[]>([]);
  newCommentText = '';
  isSubmitting = false;

  ngOnInit(): void {
    this.loadComments();
  }

  loadComments(): void {
    this.postService.getComments(this.postId).subscribe(items => {
      this.comments.set(items);
    });
  }

  submitComment(): void {
    if (!this.newCommentText.trim()) return;
    this.isSubmitting = true;
    this.postService.addComment(this.postId, this.newCommentText.trim()).subscribe({
      next: (created) => {
        this.comments.update(prev => [created, ...prev]);
        this.newCommentText = '';
        this.isSubmitting = false;
      },
      error: () => {
        this.isSubmitting = false;
      }
    });
  }

  openAuthDialog(): void {
    this.dialog.open(AuthDialogComponent, { width: '420px' });
  }
}

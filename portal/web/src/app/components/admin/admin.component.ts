import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { AuthService } from '../../services/auth.service';

interface AdminDashboardData {
  summary: {
    totalViews: number;
    totalPosts: number;
    totalComments: number;
    totalReactions: number;
    totalContacts: number;
    totalUsers: number;
  };
  posts: {
    id: string;
    slug: string;
    title: string;
    publishedAt: string;
    views: number;
    reactions: number;
    comments: number;
  }[];
  viewLogs: {
    id: string;
    path: string;
    slug: string | null;
    viewerName: string | null;
    viewerEmail: string | null;
    visitorId: string | null;
    referrer: string | null;
    userAgent: string | null;
    createdAt: string;
  }[];
  comments: {
    id: string;
    postId: string;
    parentId: string | null;
    content: string;
    createdAt: string;
    user: { id: string; name: string | null; email: string | null; image: string | null };
    post: { id: string; slug: string; title: string };
  }[];
  reactions: {
    id: string;
    type: string;
    createdAt: string;
    user: { id: string; name: string | null; email: string | null; image: string | null };
    post: { id: string; slug: string; title: string };
  }[];
  contacts: {
    id: string;
    name: string;
    email: string;
    category: string;
    subject: string;
    message: string;
    createdAt: string;
  }[];
  users: {
    id: string;
    name: string | null;
    email: string | null;
    image: string | null;
    role: string;
    createdAt: string;
  }[];
}

@Component({
  selector: 'app-admin',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <div class="admin-page container">
      <!-- Top Header -->
      <header class="admin-header">
        <div>
          <div class="admin-badge">
            <mat-icon>admin_panel_settings</mat-icon>
            <span>Mind Decoded — Admin Command Center</span>
          </div>
          <h1 class="admin-title">Portal Views, Comments & Contact Inbox</h1>
          <p class="admin-subtitle">
            All data below is live from your PostgreSQL database (Supabase): track who viewed, who commented, reply directly, and read contact messages.
          </p>
        </div>
        <button mat-flat-button color="primary" (click)="loadAdminData()" [disabled]="isLoading()" class="refresh-btn">
          <mat-icon>refresh</mat-icon>
          <span>Refresh Live Data</span>
        </button>
      </header>

      <div *ngIf="isLoading()" class="loading-box">
        <mat-spinner diameter="42"></mat-spinner>
        <p>Loading live PostgreSQL analytics, comments, and inbox...</p>
      </div>

      <ng-container *ngIf="!isLoading() && data() as d">
        <!-- KPI Summary Cards -->
        <div class="kpi-grid">
          <div class="kpi-card" (click)="activeTab.set('views')" [class.active-kpi]="activeTab() === 'views'">
            <mat-icon class="kpi-icon blue">visibility</mat-icon>
            <div>
              <div class="kpi-val">{{ d.summary.totalViews | number }}</div>
              <div class="kpi-lbl">Total Real Views</div>
            </div>
          </div>

          <div class="kpi-card" (click)="activeTab.set('viewers')" [class.active-kpi]="activeTab() === 'viewers'">
            <mat-icon class="kpi-icon indigo">group</mat-icon>
            <div>
              <div class="kpi-val">{{ d.viewLogs.length }}</div>
              <div class="kpi-lbl">Recent Visitor Logs</div>
            </div>
          </div>

          <div class="kpi-card" (click)="activeTab.set('comments')" [class.active-kpi]="activeTab() === 'comments'">
            <mat-icon class="kpi-icon purple">forum</mat-icon>
            <div>
              <div class="kpi-val">{{ d.summary.totalComments }}</div>
              <div class="kpi-lbl">Comments & Replies</div>
            </div>
          </div>

          <div class="kpi-card" (click)="activeTab.set('contacts')" [class.active-kpi]="activeTab() === 'contacts'">
            <mat-icon class="kpi-icon green">mail</mat-icon>
            <div>
              <div class="kpi-val">{{ d.summary.totalContacts }}</div>
              <div class="kpi-lbl">Contact Messages</div>
            </div>
          </div>
        </div>

        <!-- Section Navigation Tabs -->
        <div class="admin-tabs">
          <button
            class="tab-btn"
            [class.active]="activeTab() === 'contacts'"
            (click)="activeTab.set('contacts')"
          >
            <mat-icon>inbox</mat-icon>
            <span>Contact Inbox ({{ d.contacts.length }})</span>
          </button>

          <button
            class="tab-btn"
            [class.active]="activeTab() === 'comments'"
            (click)="activeTab.set('comments')"
          >
            <mat-icon>chat</mat-icon>
            <span>Who Commented & Reply ({{ d.comments.length }})</span>
          </button>

          <button
            class="tab-btn"
            [class.active]="activeTab() === 'viewers'"
            (click)="activeTab.set('viewers')"
          >
            <mat-icon>person_search</mat-icon>
            <span>Who Viewed & Reacted ({{ d.viewLogs.length }})</span>
          </button>

          <button
            class="tab-btn"
            [class.active]="activeTab() === 'views'"
            (click)="activeTab.set('views')"
          >
            <mat-icon>bar_chart</mat-icon>
            <span>Views per Article ({{ d.posts.length }})</span>
          </button>
        </div>

        <!-- TAB 1: CONTACT INBOX -->
        <section *ngIf="activeTab() === 'contacts'" class="tab-panel">
          <h2 class="section-heading">Contact Form Inbox (Stored in PostgreSQL "PortalContactMessages")</h2>
          <div *ngIf="d.contacts.length === 0" class="empty-box">
            <mat-icon>mark_email_read</mat-icon>
            <p>No contact messages yet. Test the <a routerLink="/contact">/contact</a> page to see messages appear here immediately.</p>
          </div>

          <div class="cards-stack">
            <div *ngFor="let msg of d.contacts" class="item-card">
              <div class="item-header">
                <div class="sender-info">
                  <span class="category-pill">{{ msg.category }}</span>
                  <strong>{{ msg.name }}</strong>
                  <a [href]="'mailto:' + msg.email" class="email-link">&lt;{{ msg.email }}&gt;</a>
                </div>
                <span class="time-label">{{ msg.createdAt | date:'medium' }}</span>
              </div>

              <h3 class="msg-subject">{{ msg.subject }}</h3>
              <p class="msg-body">{{ msg.message }}</p>

              <div class="item-actions">
                <a
                  mat-flat-button
                  color="primary"
                  [href]="getGmailReplyUrl(msg.email, msg.subject, msg.name)"
                  target="_blank"
                  rel="noopener"
                >
                  <mat-icon>reply</mat-icon>
                  <span>Reply in Gmail</span>
                </a>
                <a
                  mat-stroked-button
                  [href]="'mailto:' + msg.email + '?subject=' + encode('Re: ' + msg.subject)"
                >
                  <mat-icon>mail_outline</mat-icon>
                  <span>Open Mail App</span>
                </a>
                <button mat-button color="warn" (click)="deleteContact(msg.id)">
                  <mat-icon>delete_outline</mat-icon>
                  <span>Delete</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- TAB 2: WHO COMMENTED & REPLY -->
        <section *ngIf="activeTab() === 'comments'" class="tab-panel">
          <h2 class="section-heading">All Reader Comments & Direct Admin Reply</h2>
          <div *ngIf="d.comments.length === 0" class="empty-box">
            <mat-icon>chat_bubble_outline</mat-icon>
            <p>No comments posted yet.</p>
          </div>

          <div class="cards-stack">
            <div *ngFor="let c of d.comments" class="item-card">
              <div class="item-header">
                <div class="sender-info">
                  <strong>{{ c.user?.name || 'Community Reader' }}</strong>
                  <span class="email-muted" *ngIf="c.user?.email">({{ c.user.email }})</span>
                  <span class="on-article">
                    on <a [routerLink]="['/posts', c.post?.slug]">{{ c.post?.title }}</a>
                  </span>
                </div>
                <span class="time-label">{{ c.createdAt | date:'medium' }}</span>
              </div>

              <p class="msg-body">{{ c.content }}</p>

              <!-- Inline Reply Box -->
              <div class="reply-box">
                <input
                  type="text"
                  class="reply-input"
                  [(ngModel)]="replyDrafts[c.id]"
                  placeholder="Write an official reply as Jalel — Mind Decoded..."
                  (keyup.enter)="sendCommentReply(c.postId, c.id)"
                />
                <button
                  mat-flat-button
                  color="primary"
                  (click)="sendCommentReply(c.postId, c.id)"
                  [disabled]="!replyDrafts[c.id]?.trim() || sendingReplyId() === c.id"
                >
                  <mat-icon>send</mat-icon>
                  <span>{{ sendingReplyId() === c.id ? 'Posting...' : 'Reply' }}</span>
                </button>
                <button mat-button color="warn" (click)="deleteComment(c.id)">
                  <mat-icon>delete_outline</mat-icon>
                  <span>Delete</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- TAB 3: WHO VIEWED & REACTED -->
        <section *ngIf="activeTab() === 'viewers'" class="tab-panel">
          <h2 class="section-heading">Live Visitor Log — Who Viewed What & When</h2>
          <div *ngIf="d.viewLogs.length === 0" class="empty-box">
            <mat-icon>visibility</mat-icon>
            <p>Visitor logs will appear here as readers browse pages and articles.</p>
          </div>

          <div class="table-wrap" *ngIf="d.viewLogs.length > 0">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Who Viewed</th>
                  <th>Page / Article</th>
                  <th>Referrer</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let v of d.viewLogs">
                  <td class="nowrap">{{ v.createdAt | date:'short' }}</td>
                  <td>
                    <strong *ngIf="v.viewerName">{{ v.viewerName }}</strong>
                    <span *ngIf="!v.viewerName" class="guest-tag">Guest Visitor</span>
                    <div class="sub-text">{{ v.viewerEmail || v.visitorId || 'anonymous' }}</div>
                  </td>
                  <td>
                    <a [href]="v.path" target="_blank">{{ v.slug || v.path }}</a>
                  </td>
                  <td class="sub-text">{{ v.referrer || 'Direct' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h2 class="section-heading" style="margin-top: 36px;">Recent Article Reactions — Who Reacted</h2>
          <div class="table-wrap" *ngIf="d.reactions.length > 0">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Reader</th>
                  <th>Reaction</th>
                  <th>Article</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let r of d.reactions">
                  <td class="nowrap">{{ r.createdAt | date:'short' }}</td>
                  <td>
                    <strong>{{ r.user?.name || 'Visitor' }}</strong>
                    <div class="sub-text">{{ r.user?.email || r.user?.id }}</div>
                  </td>
                  <td><span class="category-pill">{{ r.type }}</span></td>
                  <td>
                    <a [routerLink]="['/posts', r.post?.slug]">{{ r.post?.title }}</a>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- TAB 4: VIEWS PER ARTICLE -->
        <section *ngIf="activeTab() === 'views'" class="tab-panel">
          <h2 class="section-heading">Article Performance (Stored in PostgreSQL "PortalAnalytics")</h2>
          <div class="table-wrap">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>Article Title</th>
                  <th>Published</th>
                  <th>Views</th>
                  <th>Reactions</th>
                  <th>Comments</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let p of d.posts">
                  <td>
                    <a [routerLink]="['/posts', p.slug]" class="post-link">{{ p.title }}</a>
                  </td>
                  <td class="nowrap">{{ p.publishedAt | date:'mediumDate' }}</td>
                  <td><strong>{{ p.views | number }}</strong></td>
                  <td>{{ p.reactions }}</td>
                  <td>{{ p.comments }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </ng-container>
    </div>
  `,
  styles: [`
    .admin-page {
      padding: 36px 16px 80px 16px;
      max-width: 1180px;
    }

    .admin-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 28px;
    }

    .admin-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #2563eb;
      background-color: #eff6ff;
      padding: 5px 14px;
      border-radius: 999px;
      margin-bottom: 10px;

      mat-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
      }
    }

    .admin-title {
      font-size: 32px;
      font-weight: 800;
      color: #0f172a;
      margin: 0 0 6px 0;
    }

    .admin-subtitle {
      font-size: 15px;
      color: #64748b;
      margin: 0;
    }

    .refresh-btn {
      border-radius: 12px;
      height: 42px;
      font-weight: 600;
    }

    .loading-box {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 14px;
      padding: 64px 16px;
      color: #64748b;
    }

    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }

    .kpi-card {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 20px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover, &.active-kpi {
        border-color: #2563eb;
        box-shadow: 0 8px 20px -6px rgba(37, 99, 235, 0.15);
      }
    }

    .kpi-icon {
      font-size: 28px;
      width: 28px;
      height: 28px;
      &.blue { color: #2563eb; }
      &.indigo { color: #4f46e5; }
      &.purple { color: #7c3aed; }
      &.green { color: #16a34a; }
    }

    .kpi-val {
      font-size: 24px;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.1;
    }

    .kpi-lbl {
      font-size: 12px;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      margin-top: 4px;
    }

    .admin-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 24px;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 12px;
    }

    .tab-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 18px;
      border-radius: 12px;
      border: 1px solid #e2e8f0;
      background: #ffffff;
      color: #475569;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;

      &.active {
        background: #2563eb;
        color: #ffffff;
        border-color: #2563eb;
      }
    }

    .section-heading {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      margin: 0 0 16px 0;
    }

    .empty-box {
      text-align: center;
      padding: 48px 16px;
      background: #ffffff;
      border: 1px dashed #cbd5e1;
      border-radius: 16px;
      color: #64748b;

      mat-icon {
        font-size: 36px;
        width: 36px;
        height: 36px;
        margin-bottom: 8px;
      }
    }

    .cards-stack {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .item-card {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      padding: 20px 24px;
    }

    .item-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 10px;
    }

    .sender-info {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      font-size: 14px;
    }

    .category-pill {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      background: #eff6ff;
      color: #1d4ed8;
    }

    .email-link {
      color: #2563eb;
      text-decoration: none;
    }

    .email-muted {
      color: #64748b;
      font-size: 13px;
    }

    .on-article {
      color: #475569;
      a {
        color: #2563eb;
        font-weight: 600;
        text-decoration: none;
      }
    }

    .time-label {
      font-size: 12px;
      color: #94a3b8;
    }

    .msg-subject {
      font-size: 17px;
      font-weight: 700;
      color: #0f172a;
      margin: 0 0 8px 0;
    }

    .msg-body {
      font-size: 15px;
      color: #334155;
      line-height: 1.6;
      margin: 0 0 16px 0;
      white-space: pre-wrap;
    }

    .item-actions, .reply-box {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
    }

    .reply-input {
      flex: 1;
      min-width: 240px;
      height: 40px;
      padding: 0 14px;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      font-size: 14px;
    }

    .table-wrap {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      overflow-x: auto;
    }

    .admin-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;

      th, td {
        padding: 14px 16px;
        text-align: left;
        border-bottom: 1px solid #f1f5f9;
      }

      th {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #64748b;
        background: #f8fafc;
      }

      a {
        color: #2563eb;
        font-weight: 600;
        text-decoration: none;
      }
    }

    .sub-text {
      font-size: 12px;
      color: #94a3b8;
    }

    .guest-tag {
      color: #475569;
      font-weight: 600;
    }

    .nowrap {
      white-space: nowrap;
    }
  `]
})
export class AdminComponent implements OnInit {
  private readonly http = inject(HttpClient);
  readonly auth = inject(AuthService);

  isLoading = signal<boolean>(true);
  activeTab = signal<'contacts' | 'comments' | 'viewers' | 'views'>('contacts');
  data = signal<AdminDashboardData | null>(null);
  replyDrafts: Record<string, string> = {};
  sendingReplyId = signal<string | null>(null);

  ngOnInit(): void {
    this.loadAdminData();
  }

  loadAdminData(): void {
    this.isLoading.set(true);
    this.http.get<AdminDashboardData>('/api/admin').subscribe({
      next: (res) => {
        this.data.set(res);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
      }
    });
  }

  sendCommentReply(postId: string, parentId: string): void {
    const content = (this.replyDrafts[parentId] || '').trim();
    if (!content) return;

    const user = this.auth.currentUser();
    this.sendingReplyId.set(parentId);
    this.http.post('/api/admin', {
      action: 'reply_comment',
      postId,
      parentId,
      content,
      adminName: user?.name || 'Jalel — Mind Decoded',
      adminEmail: user?.email || 'jalel.edine.agrebi@gmail.com',
    }).subscribe({
      next: () => {
        this.replyDrafts[parentId] = '';
        this.sendingReplyId.set(null);
        this.loadAdminData();
      },
      error: () => {
        this.sendingReplyId.set(null);
      }
    });
  }

  deleteComment(commentId: string): void {
    this.http.post('/api/admin', { action: 'delete_comment', commentId }).subscribe({
      next: () => this.loadAdminData(),
    });
  }

  deleteContact(contactId: string): void {
    this.http.post('/api/admin', { action: 'delete_contact', contactId }).subscribe({
      next: () => this.loadAdminData(),
    });
  }

  encode(val: string): string {
    return encodeURIComponent(val || '');
  }

  getGmailReplyUrl(to: string, subject: string, name: string): string {
    const su = encodeURIComponent(`Re: ${subject}`);
    const body = encodeURIComponent(`Hi ${name},\n\nThank you for reaching out to Mind Decoded.\n\nBest regards,\nJalel — Mind Decoded`);
    return `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(to)}&su=${su}&body=${body}`;
  }
}

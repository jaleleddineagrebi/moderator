import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog } from '@angular/material/dialog';
import { MatMenuModule } from '@angular/material/menu';
import { AuthService } from '../../services/auth.service';
import { AuthDialogComponent } from '../auth-dialog/auth-dialog.component';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, RouterModule, MatToolbarModule, MatButtonModule, MatIconModule, MatMenuModule],
  template: `
    <mat-toolbar class="main-toolbar mat-elevation-z1">
      <div class="toolbar-content container">
        <!-- Brand Logo & Title -->
        <a routerLink="/" class="brand-link">
          <div class="logo-circle">
            <mat-icon class="brand-icon">psychology</mat-icon>
          </div>
          <div class="brand-text">
            <span class="brand-title">MIND DECODED</span>
            <span class="brand-subtitle">Psychology & Artificial Intelligence</span>
          </div>
        </a>

        <!-- Navigation Links -->
        <nav class="nav-links">
          <a mat-button routerLink="/" routerLinkActive="active-link" [routerLinkActiveOptions]="{ exact: true }">
            <mat-icon>article</mat-icon>
            <span>Daily Insights</span>
          </a>
          <a mat-button routerLink="/shorts" routerLinkActive="active-link">
            <mat-icon>smart_display</mat-icon>
            <span>YouTube Shorts</span>
          </a>
          <a mat-button routerLink="/contact" routerLinkActive="active-link">
            <mat-icon>mail_outline</mat-icon>
            <span>Contact</span>
          </a>
        </nav>

        <!-- Right Action: User Auth -->
        <div class="auth-action">
          <ng-container *ngIf="auth.isAuthenticated(); else loginTrigger">
            <button mat-icon-button [matMenuTriggerFor]="userMenu" class="user-avatar-btn">
              <img
                *ngIf="auth.currentUser()?.image; else avatarFallback"
                [src]="auth.currentUser()?.image"
                [alt]="auth.currentUser()?.name || 'User'"
                class="avatar-img"
              />
              <ng-template #avatarFallback>
                <mat-icon>account_circle</mat-icon>
              </ng-template>
            </button>
            <mat-menu #userMenu="matMenu">
              <div class="user-menu-header">
                <strong>{{ auth.currentUser()?.name }}</strong>
                <small>{{ auth.currentUser()?.email }}</small>
              </div>
              <button mat-menu-item (click)="auth.logout()">
                <mat-icon>logout</mat-icon>
                <span>Sign Out</span>
              </button>
            </mat-menu>
          </ng-container>

          <ng-template #loginTrigger>
            <button mat-flat-button color="primary" class="signin-btn" (click)="openAuthDialog()">
              <mat-icon>login</mat-icon>
              <span>Sign In</span>
            </button>
          </ng-template>
        </div>
      </div>
    </mat-toolbar>
  `,
  styles: [`
    .main-toolbar {
      background-color: #ffffff;
      color: #0f172a;
      position: sticky;
      top: 0;
      z-index: 1000;
      border-bottom: 1px solid #e2e8f0;
      height: 72px;
    }

    .toolbar-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
    }

    .brand-link {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: inherit;
    }

    .logo-circle {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3);
    }

    .brand-icon {
      font-size: 26px;
      width: 26px;
      height: 26px;
    }

    .brand-text {
      display: flex;
      flex-direction: column;
    }

    .brand-title {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #0f172a;
    }

    .brand-subtitle {
      font-size: 11px;
      font-weight: 600;
      color: #64748b;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }

    .nav-links {
      display: none;
      align-items: center;
      gap: 8px;

      @media (min-width: 768px) {
        display: flex;
      }

      a {
        border-radius: 10px;
        font-weight: 600;
        color: #475569;

        &.active-link {
          background-color: #eff6ff;
          color: #2563eb;
        }
      }
    }

    .signin-btn {
      border-radius: 12px;
      font-weight: 600;
      padding: 0 20px;
      height: 40px;
    }

    .user-avatar-btn {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      overflow: hidden;
      padding: 0;

      .avatar-img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
    }

    .user-menu-header {
      padding: 12px 16px;
      display: flex;
      flex-direction: column;
      border-bottom: 1px solid #f1f5f9;

      strong {
        font-size: 14px;
        color: #0f172a;
      }

      small {
        font-size: 12px;
        color: #64748b;
      }
    }
  `]
})
export class HeaderComponent {
  readonly auth = inject(AuthService);
  private readonly dialog = inject(MatDialog);

  openAuthDialog(): void {
    this.dialog.open(AuthDialogComponent, { width: '420px' });
  }
}


import { Component, AfterViewInit, ElementRef, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-auth-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <div class="auth-dialog-wrapper">
      <div class="dialog-header">
        <div class="icon-badge">
          <mat-icon>psychology</mat-icon>
        </div>
        <h2 mat-dialog-title class="dialog-title">Welcome to Mind Decoded</h2>
        <p class="dialog-subtitle">
          Sign in to react, discuss cognitive science, and save your daily bias reflections.
        </p>
      </div>

      <mat-dialog-content class="dialog-content">
        <!-- Google Sign In Container -->
        <div class="google-auth-container">
          <button
            mat-stroked-button
            class="fallback-google-btn"
            (click)="loginGoogleDirect()"
          >
            <svg class="google-svg" viewBox="0 0 24 24" width="20" height="20">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            <span>Continue with Google</span>
          </button>
          <div #googleBtnContainer class="google-btn-slot"></div>
        </div>

        <div class="dialog-privacy-note">
          <mat-icon class="shield-icon">security</mat-icon>
          <span>Fast, secure sign-in via Google. We only use your name and email to identify your comments.</span>
        </div>
      </mat-dialog-content>

      <mat-dialog-actions align="end" class="dialog-actions">
        <button mat-button (click)="dialogRef.close()" class="cancel-btn">Close</button>
      </mat-dialog-actions>
    </div>
  `,
  styles: [`
    .auth-dialog-wrapper {
      padding: 12px 16px 20px 16px;
      max-width: 420px;
      text-align: center;
    }

    .dialog-header {
      display: flex;
      flex-direction: column;
      align-items: center;
      margin-bottom: 24px;
    }

    .icon-badge {
      width: 48px;
      height: 48px;
      border-radius: 14px;
      background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
      color: #2563eb;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 12px;

      mat-icon {
        font-size: 26px;
        width: 26px;
        height: 26px;
      }
    }

    .dialog-title {
      font-size: 22px;
      font-weight: 800;
      color: #0f172a;
      margin: 0 0 8px 0;
      letter-spacing: -0.02em;
    }

    .dialog-subtitle {
      font-size: 14px;
      color: #64748b;
      line-height: 1.5;
      margin: 0;
      max-width: 320px;
    }

    .dialog-content {
      padding: 0 !important;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 20px;
    }

    .google-auth-container {
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 44px;
    }

    .google-btn-slot {
      display: none;
    }

    .fallback-google-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      width: 100%;
      max-width: 320px;
      height: 44px;
      border-radius: 9999px;
      border-color: #cbd5e1;
      color: #1e293b;
      font-weight: 600;
      font-size: 14px;
      background-color: #ffffff;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

      &:hover {
        background-color: #f8fafc;
        border-color: #94a3b8;
      }

      .google-svg {
        flex-shrink: 0;
      }
    }

    .google-btn-slot:not(:empty) + .fallback-google-btn {
      display: none;
    }

    .dialog-privacy-note {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: #94a3b8;
      line-height: 1.4;
      text-align: left;
      padding: 10px 14px;
      background-color: #f8fafc;
      border-radius: 10px;

      .shield-icon {
        font-size: 16px;
        width: 16px;
        height: 16px;
        color: #64748b;
        flex-shrink: 0;
      }
    }

    .dialog-actions {
      margin-top: 8px;
      padding: 0 !important;
    }

    .cancel-btn {
      color: #64748b;
    }
  `]
})
export class AuthDialogComponent implements AfterViewInit {
  @ViewChild('googleBtnContainer') googleBtnContainer!: ElementRef<HTMLDivElement>;

  readonly dialogRef = inject(MatDialogRef<AuthDialogComponent>);
  private readonly auth = inject(AuthService);

  ngAfterViewInit(): void {
    this.tryRenderButton(0);
  }

  private tryRenderButton(attempt: number): void {
    if (!this.googleBtnContainer?.nativeElement) return;
    const ok = this.auth.renderGoogleButton(this.googleBtnContainer.nativeElement, () => {
      this.dialogRef.close();
    });
    if (!ok && attempt < 5) {
      setTimeout(() => this.tryRenderButton(attempt + 1), 350);
    }
  }

  loginGoogleDirect(): void {
    this.auth.loginWithGoogle(() => {
      this.dialogRef.close();
    });
  }
}

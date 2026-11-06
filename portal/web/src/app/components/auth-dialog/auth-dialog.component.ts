import { Component, inject } from '@angular/core';
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
      <h2 mat-dialog-title class="dialog-title">
        <mat-icon color="primary">psychology</mat-icon>
        <span>Join the Psychology & AI Community</span>
      </h2>

      <mat-dialog-content class="dialog-content">
        <p class="dialog-subtitle">
          Sign in to react, discuss cognitive science, and save your daily bias reflections.
        </p>

        <div class="oauth-buttons">
          <!-- Google OAuth Button -->
          <button mat-stroked-button class="oauth-btn google-btn" (click)="loginGoogle()">
            <svg class="oauth-icon" viewBox="0 0 24 24" width="20" height="20">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            <span>Continue with Google</span>
          </button>

          <!-- Facebook OAuth Button -->
          <button mat-flat-button class="oauth-btn facebook-btn" (click)="loginFacebook()">
            <svg class="oauth-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
            </svg>
            <span>Continue with Facebook</span>
          </button>
        </div>
      </mat-dialog-content>

      <mat-dialog-actions align="end">
        <button mat-button (click)="dialogRef.close()">Cancel</button>
      </mat-dialog-actions>
    </div>
  `,
  styles: [`
    .auth-dialog-wrapper {
      padding: 16px;
      min-width: 320px;
      max-width: 440px;
    }

    .dialog-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 8px;
    }

    .dialog-subtitle {
      font-size: 14px;
      color: #64748b;
      line-height: 1.5;
      margin-bottom: 20px;
    }

    .oauth-buttons {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .oauth-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      height: 48px;
      border-radius: 12px;
      font-size: 15px;
      font-weight: 600;
    }

    .google-btn {
      border-color: #cbd5e1;
      color: #334155;
    }

    .facebook-btn {
      background-color: #1877f2;
      color: #ffffff;
    }

    .oauth-icon {
      flex-shrink: 0;
    }
  `]
})
export class AuthDialogComponent {
  readonly dialogRef = inject(MatDialogRef<AuthDialogComponent>);
  private readonly auth = inject(AuthService);

  loginGoogle(): void {
    this.auth.loginWithGoogle();
    this.dialogRef.close();
  }

  loginFacebook(): void {
    this.auth.loginWithFacebook();
    this.dialogRef.close();
  }
}

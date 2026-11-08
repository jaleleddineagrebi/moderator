import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { User } from '../models/post.model';

declare const google: any;

export const GOOGLE_CLIENT_ID = '701586086068-v014k4trutnrdd5gob94i4bem6s3ktag.apps.googleusercontent.com';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly _currentUser = signal<User | null>(null);

  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => !!this._currentUser());

  constructor() {
    this.restoreSession();
    this.checkForOAuthCallback();
  }

  /**
   * Initializes Google Identity Services (GIS) if loaded in browser.
   */
  initGoogleClient(onSuccess?: (user: User) => void): void {
    if (typeof window === 'undefined' || typeof google === 'undefined') {
      return;
    }

    try {
      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response: any) => {
          this.handleGoogleCredential(response.credential, onSuccess);
        },
        auto_select: false,
        cancel_on_tap_outside: true,
      });
    } catch (e) {
      console.warn('[AuthService] Google Identity Services init error:', e);
    }
  }

  /**
   * Renders the official Google Sign-In button into a container element.
   */
  renderGoogleButton(element: HTMLElement, onSuccess?: (user: User) => void): void {
    this.initGoogleClient(onSuccess);
    if (typeof google !== 'undefined' && google.accounts?.id) {
      google.accounts.id.renderButton(element, {
        type: 'standard',
        shape: 'pill',
        theme: 'outline',
        text: 'signin_with',
        size: 'large',
        logo_alignment: 'left',
        width: 320,
      });
    }
  }

  /**
   * Triggers Google Sign-In (via GIS prompt or OAuth redirect).
   */
  loginWithGoogle(onSuccess?: (user: User) => void): void {
    if (typeof google !== 'undefined' && google.accounts?.id) {
      this.initGoogleClient(onSuccess);
      google.accounts.id.prompt((notification: any) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          // Fall back to direct redirect if OneTap popup is skipped/blocked
          window.location.href = '/api/auth/signin/google';
        }
      });
    } else {
      window.location.href = '/api/auth/signin/google';
    }
  }

  /**
   * Handles credential returned by Google Identity Services and syncs with Supabase.
   */
  handleGoogleCredential(credential: string, onSuccess?: (user: User) => void): void {
    this.http.post<{ success: boolean; user: User }>('/api/auth', { credential }).subscribe({
      next: (res) => {
        if (res.user) {
          this.setUserSession(res.user);
          if (onSuccess) onSuccess(res.user);
        }
      },
      error: (err) => {
        console.error('[AuthService] Backend auth failed:', err);
      }
    });
  }

  logout(): void {
    this._currentUser.set(null);
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('portal_user');
    }
    if (typeof google !== 'undefined' && google.accounts?.id) {
      google.accounts.id.disableAutoSelect();
    }
  }

  private setUserSession(user: User): void {
    this._currentUser.set(user);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('portal_user', JSON.stringify(user));
    }
  }

  private restoreSession(): void {
    if (typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem('portal_user');
      if (saved) {
        try {
          this._currentUser.set(JSON.parse(saved));
        } catch {
          // Ignore parse errors
        }
      }
    }
  }

  private checkForOAuthCallback(): void {
    if (typeof window === 'undefined') return;

    try {
      const url = new URL(window.location.href);
      const authUser = url.searchParams.get('auth_user');
      if (authUser) {
        const user = JSON.parse(decodeURIComponent(authUser));
        if (user && user.email) {
          this.setUserSession(user);
          url.searchParams.delete('auth_user');
          window.history.replaceState({}, document.title, url.pathname + (url.search || ''));
        }
      }
    } catch (e) {
      console.warn('[AuthService] Error reading OAuth callback params:', e);
    }
  }
}

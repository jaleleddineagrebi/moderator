import { Injectable, signal, computed, inject, NgZone } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { User } from '../models/post.model';

declare const google: any;

export const GOOGLE_CLIENT_ID = '701586086068-v014k4trutnrdd5gob94i4bem6s3ktag.apps.googleusercontent.com';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly zone = inject(NgZone);
  private readonly _currentUser = signal<User | null>(null);
  readonly authError = signal<string>('');

  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => !!this._currentUser());

  constructor() {
    this.restoreSession();
    this.checkForOAuthCallback();
  }

  private decodeGoogleJwt(token: string): Record<string, any> | null {
    try {
      const parts = token.split('.');
      if (parts.length < 2) return null;
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
      const binary = atob(padded);
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      const jsonStr = new TextDecoder().decode(bytes);
      return JSON.parse(jsonStr);
    } catch {
      return null;
    }
  }

  /**
   * Initializes Google Identity Services (GIS) if loaded in browser.
   */
  initGoogleClient(onSuccess?: (user: User) => void): void {
    if (typeof window === 'undefined' || typeof google === 'undefined' || !google.accounts?.id) {
      return;
    }

    try {
      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response: any) => {
          this.zone.run(() => {
            if (response?.credential) {
              this.handleGoogleCredential(response.credential, onSuccess);
            }
          });
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
  renderGoogleButton(element: HTMLElement, onSuccess?: (user: User) => void): boolean {
    if (typeof window === 'undefined' || typeof google === 'undefined' || !google.accounts?.id) {
      return false;
    }
    try {
      this.initGoogleClient(onSuccess);
      google.accounts.id.renderButton(element, {
        type: 'standard',
        shape: 'pill',
        theme: 'outline',
        text: 'signin_with',
        size: 'large',
        logo_alignment: 'left',
        width: 320,
      });
      return true;
    } catch (e) {
      console.warn('[AuthService] Could not render Google button:', e);
      return false;
    }
  }

  /**
   * Triggers Google Sign-In via OAuth2 Popup Token Client (or server redirect fallback).
   */
  loginWithGoogle(onSuccess?: (user: User) => void): void {
    this.authError.set('');

    if (typeof window !== 'undefined' && typeof google !== 'undefined' && google.accounts?.oauth2) {
      try {
        const tokenClient = google.accounts.oauth2.initTokenClient({
          client_id: GOOGLE_CLIENT_ID,
          scope: 'openid email profile',
          prompt: 'select_account',
          callback: (tokenResponse: any) => {
            this.zone.run(() => {
              if (tokenResponse?.access_token) {
                this.handleGoogleAccessToken(tokenResponse.access_token, onSuccess);
              } else if (tokenResponse?.error) {
                window.location.href = '/api/auth/signin/google';
              }
            });
          },
          error_callback: () => {
            window.location.href = '/api/auth/signin/google';
          },
        });
        tokenClient.requestAccessToken();
        return;
      } catch (e) {
        console.warn('[AuthService] OAuth2 tokenClient error, falling back to redirect:', e);
      }
    }

    window.location.href = '/api/auth/signin/google';
  }

  /**
   * Handles OAuth2 access_token returned by google.accounts.oauth2 popup.
   */
  handleGoogleAccessToken(accessToken: string, onSuccess?: (user: User) => void): void {
    this.http
      .get<any>('https://www.googleapis.com/oauth2/v3/userinfo', {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      .subscribe({
        next: (profile) => {
          if (profile?.email) {
            const immediateUser: User = {
              id: profile.sub || profile.email,
              name: profile.name || profile.email.split('@')[0],
              email: profile.email.toLowerCase(),
              image: profile.picture || undefined,
              role: 'USER',
            };
            this.setUserSession(immediateUser);
            if (onSuccess) onSuccess(immediateUser);

            // Sync with backend database
            this.http.post<{ success: boolean; user: User }>('/api/auth', { accessToken, profile }).subscribe({
              next: (res) => {
                if (res?.user) {
                  this.setUserSession(res.user);
                }
              },
              error: () => {},
            });
          }
        },
        error: () => {
          window.location.href = '/api/auth/signin/google';
        },
      });
  }

  /**
   * Handles credential JWT returned by Google Identity Services and syncs with Supabase.
   */
  handleGoogleCredential(credential: string, onSuccess?: (user: User) => void): void {
    // 1. Immediately decode JWT in browser so login feels instant even if DB cold-starts
    const payload = this.decodeGoogleJwt(credential);
    if (payload && payload['email']) {
      const immediateUser: User = {
        id: payload['sub'] || payload['email'],
        name: payload['name'] || payload['email'].split('@')[0],
        email: String(payload['email']).toLowerCase(),
        image: payload['picture'] || undefined,
        role: 'USER',
      };
      this.setUserSession(immediateUser);
      if (onSuccess) onSuccess(immediateUser);
    }

    // 2. Sync with backend /api/auth to upsert user in PostgreSQL
    this.http.post<{ success: boolean; user: User }>('/api/auth', { credential }).subscribe({
      next: (res) => {
        if (res?.user) {
          this.setUserSession(res.user);
          if (!payload && onSuccess) onSuccess(res.user);
        }
      },
      error: (err) => {
        console.warn('[AuthService] Backend sync warning (session kept locally):', err);
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
      const authErr = url.searchParams.get('auth_error');

      if (authUser) {
        const user = JSON.parse(decodeURIComponent(authUser));
        if (user && user.email) {
          this.setUserSession(user);
          url.searchParams.delete('auth_user');
          window.history.replaceState({}, document.title, url.pathname + (url.search || ''));
        }
      } else if (authErr) {
        this.authError.set(authErr);
        url.searchParams.delete('auth_error');
        window.history.replaceState({}, document.title, url.pathname + (url.search || ''));
      }
    } catch (e) {
      console.warn('[AuthService] Error reading OAuth callback params:', e);
    }
  }
}

import { Injectable, signal, computed } from '@angular/core';
import { User } from '../models/post.model';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // Modern Angular signal for user state
  private readonly _currentUser = signal<User | null>(null);

  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => !!this._currentUser());

  constructor() {
    this.restoreSession();
  }

  loginWithGoogle(): void {
    // Redirects to NextAuth / OAuth Google endpoint
    window.location.href = '/api/auth/signin/google';
  }

  loginWithFacebook(): void {
    // Redirects to NextAuth / OAuth Facebook endpoint
    window.location.href = '/api/auth/signin/facebook';
  }

  logout(): void {
    this._currentUser.set(null);
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('portal_user');
    }
    window.location.href = '/api/auth/signout';
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
}


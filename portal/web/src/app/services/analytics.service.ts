import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class AnalyticsService {
  trackEvent(name: string, properties?: Record<string, any>): void {
    if (typeof window === 'undefined') return;

    try {
      // 1. Google Analytics (gtag)
      if ((window as any).gtag) {
        (window as any).gtag('event', name, properties);
      }

      // 2. Vercel Analytics (va)
      if ((window as any).va) {
        (window as any).va('event', { name, data: properties });
      }

      // 3. Dev logger
      console.log(`[Analytics Event: ${name}]`, properties);
    } catch (err) {
      console.warn('Analytics tracking error:', err);
    }
  }
}

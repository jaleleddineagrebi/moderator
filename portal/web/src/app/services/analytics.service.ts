import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface PortalVisibilitySummary {
  totalViews: number;
  recordedViews: number;
  totalPosts: number;
  totalReactions: number;
  totalComments: number;
  totalShorts: number;
  postViews: Record<string, number>;
  gaMeasurementId?: string;
}

@Injectable({
  providedIn: 'root'
})
export class AnalyticsService {
  private readonly http = inject(HttpClient);
  private readonly sessionTrackedPaths = new Set<string>();
  private gaInitializedId = '';

  readonly summary = signal<PortalVisibilitySummary>({
    totalViews: 0,
    recordedViews: 0,
    totalPosts: 0,
    totalReactions: 0,
    totalComments: 0,
    totalShorts: 0,
    postViews: {},
  });

  loadVisibilitySummary(): void {
    this.http.get<PortalVisibilitySummary>('/api/analytics').subscribe({
      next: (res) => {
        if (res) {
          this.summary.set(res);
          if (res.gaMeasurementId) {
            this.initGoogleAnalytics(res.gaMeasurementId);
          }
        }
      },
      error: () => {}
    });
  }

  initGoogleAnalytics(measurementId: string): void {
    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    const cleanId = (measurementId || '').trim();
    if (!cleanId || this.gaInitializedId === cleanId) return;
    this.gaInitializedId = cleanId;
    (window as any).GA_MEASUREMENT_ID = cleanId;

    const existing = document.querySelector(`script[src*="googletagmanager.com/gtag/js?id=${cleanId}"]`);
    if (!existing) {
      const script = document.createElement('script');
      script.async = true;
      script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(cleanId)}`;
      document.head.appendChild(script);
    }

    if ((window as any).gtag) {
      (window as any).gtag('config', cleanId, {
        page_path: window.location.pathname + window.location.search,
        page_location: window.location.href,
        page_title: document.title,
      });
    }
  }

  trackPageView(path: string, slug?: string): void {
    if (typeof window === 'undefined') return;
    const dedupeKey = slug ? `post:${slug}` : `page:${path}`;
    this.trackEvent(slug ? 'post_view' : 'page_view', { page_path: path, slug: slug || null });

    if (this.sessionTrackedPaths.has(dedupeKey)) {
      return;
    }
    this.sessionTrackedPaths.add(dedupeKey);

    this.http.post<{ ok: boolean; postViews?: number }>('/api/analytics', {
      event: slug ? 'post_view' : 'page_view',
      path,
      slug: slug || null,
      referrer: typeof document !== 'undefined' ? document.referrer || null : null,
    }).subscribe({
      next: (res) => {
        const cur = this.summary();
        const nextPostViews = { ...cur.postViews };
        if (slug) {
          nextPostViews[slug] = res?.postViews || (nextPostViews[slug] || 0) + 1;
        }
        this.summary.set({
          ...cur,
          totalViews: cur.totalViews + 1,
          recordedViews: cur.recordedViews + 1,
          postViews: nextPostViews,
        });
      },
      error: () => {}
    });
  }

  getViewsForPost(slug: string, reactionCount: number = 0, commentCount: number = 0): number {
    const recorded = this.summary().postViews?.[slug] || 0;
    // Baseline organic estimate from slug hash + interactions + recorded views
    let hash = 0;
    for (let i = 0; i < slug.length; i++) {
      hash = (hash * 31 + slug.charCodeAt(i)) & 0x7fffffff;
    }
    const base = 18 + (hash % 45) + reactionCount * 6 + commentCount * 9;
    return base + recorded;
  }

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
    } catch (err) {
      console.warn('Analytics tracking error:', err);
    }
  }
}


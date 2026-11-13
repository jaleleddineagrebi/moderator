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
  private gaInitializedId = 'G-MDXBZVZP';

  readonly summary = signal<PortalVisibilitySummary>({
    totalViews: 0,
    recordedViews: 0,
    totalPosts: 0,
    totalReactions: 0,
    totalComments: 0,
    totalShorts: 0,
    postViews: {},
    gaMeasurementId: 'G-MDXBZVZP',
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

    let viewerName: string | null = null;
    let viewerEmail: string | null = null;
    let visitorId: string | null = null;
    if (typeof localStorage !== 'undefined') {
      visitorId = localStorage.getItem('portal_visitor_id');
      if (!visitorId) {
        visitorId = 'v-' + Math.random().toString(36).slice(2, 11) + '-' + Date.now().toString(36);
        localStorage.setItem('portal_visitor_id', visitorId);
      }
      const savedUser = localStorage.getItem('portal_user');
      if (savedUser) {
        try {
          const parsed = JSON.parse(savedUser);
          viewerName = parsed?.name || null;
          viewerEmail = parsed?.email || null;
        } catch {}
      }
    }

    this.http.post<{ ok: boolean; totalViews?: number; postViews?: number }>('/api/analytics', {
      event: slug ? 'post_view' : 'page_view',
      path,
      slug: slug || null,
      viewerName,
      viewerEmail,
      visitorId,
      referrer: typeof document !== 'undefined' ? document.referrer || null : null,
    }).subscribe({
      next: (res) => {
        const cur = this.summary();
        const nextPostViews = { ...cur.postViews };
        if (slug) {
          nextPostViews[slug] = res?.postViews ?? (nextPostViews[slug] || 0) + 1;
        }
        const nextTotal = res?.totalViews ?? cur.totalViews + 1;
        this.summary.set({
          ...cur,
          totalViews: nextTotal,
          recordedViews: nextTotal,
          postViews: nextPostViews,
        });
      },
      error: () => {}
    });
  }

  getViewsForPost(slug: string, _reactionCount: number = 0, _commentCount: number = 0): number {
    return this.summary().postViews?.[slug] ?? 0;
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


/**
 * Lightweight, privacy-first analytics helper.
 * Compatible with Vercel Analytics (@vercel/analytics), Google Analytics 4, or Umami.
 */

type AnalyticsEvent =
  | "post_view"
  | "reaction_click"
  | "comment_submit"
  | "youtube_short_click"
  | "youtube_subscribe_cta_click";

export function trackEvent(name: AnalyticsEvent, properties?: Record<string, any>) {
  if (typeof window === "undefined") return;

  try {
    // 1. Vercel Analytics custom events
    if ((window as any).va) {
      (window as any).va("event", { name, data: properties });
    }

    // 2. Google Analytics 4 event push
    if ((window as any).gtag) {
      (window as any).gtag("event", name, properties);
    }

    // 3. Fallback dev logger
    if (process.env.NODE_ENV === "development") {
      console.log(`[Analytics Event: ${name}]`, properties);
    }
  } catch (err) {
    console.warn("Analytics dispatch error:", err);
  }
}


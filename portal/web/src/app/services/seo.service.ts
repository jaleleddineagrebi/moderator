import { Injectable, inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Meta, Title } from '@angular/platform-browser';
import { Post, hasPlayableShort } from '../models/post.model';

@Injectable({
  providedIn: 'root'
})
export class SeoService {
  private readonly titleService = inject(Title);
  private readonly metaService = inject(Meta);
  private readonly doc = inject(DOCUMENT);

  private get origin(): string {
    return typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin
      : 'https://moderator-portal.vercel.app';
  }

  setFeedSeo(posts: Post[], selectedTopic: string = 'All Insights'): void {
    const isTopic = selectedTopic && selectedTopic !== 'All Insights';
    const pageTitle = isTopic
      ? `${selectedTopic} — Mind Decoded | Psychology & AI Insights`
      : 'Mind Decoded — Psychology, Cognitive Biases & AI Research Portal';
    const description =
      'Daily scientifically grounded articles and viral YouTube Shorts decoding human psychology, cognitive biases, dark psychology defense, mental models, and artificial intelligence.';
    const url = `${this.origin}/`;

    this.titleService.setTitle(pageTitle);
    this.updateTags({
      description,
      keywords: 'psychology, cognitive biases, artificial intelligence, human behavior, mental models, neuroscience, dark psychology, Mind Decoded',
      image: posts[0]?.coverImageUrl || 'https://images.unsplash.com/photo-1559757175-5700dde675bc?auto=format&fit=crop&w=1200&q=80',
      url,
      type: 'website',
      title: pageTitle,
    });
    this.setCanonical(url);

    // Build ItemList + WebSite JSON-LD schema for Google Search & Discover
    const itemListElements = posts.slice(0, 10).map((p, idx) => ({
      '@type': 'ListItem',
      position: idx + 1,
      url: `${this.origin}/posts/${encodeURIComponent(p.slug)}`,
      name: p.title,
    }));

    this.setJsonLd({
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'WebSite',
          name: 'Mind Decoded — Psychology & AI Portal',
          url: `${this.origin}/`,
          description,
          publisher: {
            '@type': 'Organization',
            name: 'Mind Decoded',
            sameAs: ['https://www.youtube.com/channel/UCzjz2ArvjE4RgR_2k2o53mg'],
          },
        },
        {
          '@type': 'ItemList',
          itemListElement: itemListElements,
        },
      ],
    });
  }

  setPostSeo(post: Post): void {
    const pageTitle = `${post.title} | Mind Decoded`;
    const description = (post.summary || post.hook || post.title).slice(0, 160);
    const url = `${this.origin}/posts/${encodeURIComponent(post.slug)}`;
    const keywords = (post.tags || []).concat(['Psychology', 'Artificial Intelligence', 'Mind Decoded']).join(', ');

    this.titleService.setTitle(pageTitle);
    this.updateTags({
      title: pageTitle,
      description,
      keywords,
      image: post.coverImageUrl,
      url,
      type: 'article',
      publishedTime: post.publishedAt,
    });
    this.setCanonical(url);

    const schema: Record<string, any> = {
      '@context': 'https://schema.org',
      '@type': 'BlogPosting',
      headline: post.title,
      description,
      image: [post.coverImageUrl],
      datePublished: post.publishedAt,
      dateModified: post.publishedAt,
      mainEntityOfPage: {
        '@type': 'WebPage',
        '@id': url,
      },
      author: {
        '@type': 'Organization',
        name: 'Mind Decoded Research',
        url: `${this.origin}/`,
      },
      publisher: {
        '@type': 'Organization',
        name: 'Mind Decoded',
        sameAs: ['https://www.youtube.com/channel/UCzjz2ArvjE4RgR_2k2o53mg'],
      },
      keywords,
    };

    if (hasPlayableShort(post) && post.youtubeShort) {
      schema['video'] = {
        '@type': 'VideoObject',
        name: post.youtubeShort.title || post.title,
        description: post.youtubeShort.hookAngle || description,
        thumbnailUrl: [`https://i.ytimg.com/vi/${post.youtubeShort.id}/hqdefault.jpg`],
        uploadDate: post.youtubeShort.publishedAt || post.publishedAt,
        contentUrl: `https://www.youtube.com/shorts/${post.youtubeShort.id}`,
        embedUrl: `https://www.youtube.com/embed/${post.youtubeShort.id}`,
      };
    }

    this.setJsonLd(schema);
  }

  private updateTags(opts: {
    title: string;
    description: string;
    keywords: string;
    image: string;
    url: string;
    type: 'website' | 'article';
    publishedTime?: string;
  }): void {
    this.metaService.updateTag({ name: 'description', content: opts.description });
    this.metaService.updateTag({ name: 'keywords', content: opts.keywords });
    this.metaService.updateTag({ property: 'og:title', content: opts.title });
    this.metaService.updateTag({ property: 'og:description', content: opts.description });
    this.metaService.updateTag({ property: 'og:image', content: opts.image });
    this.metaService.updateTag({ property: 'og:url', content: opts.url });
    this.metaService.updateTag({ property: 'og:type', content: opts.type });
    this.metaService.updateTag({ name: 'twitter:title', content: opts.title });
    this.metaService.updateTag({ name: 'twitter:description', content: opts.description });
    this.metaService.updateTag({ name: 'twitter:image', content: opts.image });
    if (opts.publishedTime) {
      this.metaService.updateTag({ property: 'article:published_time', content: opts.publishedTime });
    }
  }

  private setCanonical(url: string): void {
    let link: HTMLLinkElement | null = this.doc.querySelector('link[rel="canonical"]');
    if (!link) {
      link = this.doc.createElement('link');
      link.setAttribute('rel', 'canonical');
      this.doc.head.appendChild(link);
    }
    link.setAttribute('href', url);
  }

  private setJsonLd(data: Record<string, any>): void {
    let script = this.doc.getElementById('json-ld-schema') as HTMLScriptElement | null;
    if (!script) {
      script = this.doc.createElement('script');
      script.id = 'json-ld-schema';
      script.type = 'application/ld+json';
      this.doc.head.appendChild(script);
    }
    script.textContent = JSON.stringify(data);
  }
}


import React from "react";
import { Metadata } from "next";
import { notFound } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { YouTubeShortCard } from "@/components/YouTubeShortCard";

interface PostPageProps {
  params: {
    slug: string;
  };
}

// -------------------------------------------------------------
// Dynamic SEO Metadata Generator (App Router)
// -------------------------------------------------------------
export async function generateMetadata({ params }: PostPageProps): Promise<Metadata> {
  const post = await prisma.post.findUnique({
    where: { slug: params.slug },
    include: { youtubeShort: true },
  });

  if (!post) {
    return {
      title: "Article Not Found | Psychology & AI Portal",
    };
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://psychology-ai-portal.vercel.app";
  const canonicalUrl = `${siteUrl}/posts/${post.slug}`;
  const keywords = [...post.tags, "Psychology and AI", "Cognitive Science", "Brain Bias Check"];

  return {
    title: `${post.title} | Psychology & AI`,
    description: post.summary,
    keywords,
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      type: "article",
      url: canonicalUrl,
      title: post.title,
      description: post.summary,
      publishedTime: post.publishedAt.toISOString(),
      modifiedTime: post.updatedAt.toISOString(),
      images: [
        {
          url: post.coverImageUrl,
          width: 1200,
          height: 630,
          alt: post.title,
        },
      ],
      tags: post.tags,
    },
    twitter: {
      card: "summary_large_image",
      title: post.title,
      description: post.summary,
      images: [post.coverImageUrl],
      creator: "@MindDecodedAI",
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-video-preview": -1,
        "max-image-preview": "large",
        "max-snippet": -1,
      },
    },
  };
}

// -------------------------------------------------------------
// Page Renderer with JSON-LD Structured Data
// -------------------------------------------------------------
export default async function PostPage({ params }: PostPageProps) {
  const post = await prisma.post.findUnique({
    where: { slug: params.slug },
    include: {
      youtubeShort: true,
      _count: {
        select: { comments: true, reactions: true },
      },
    },
  });

  if (!post || post.status !== "PUBLISHED") {
    notFound();
  }

  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://psychology-ai-portal.vercel.app";
  const articleUrl = `${siteUrl}/posts/${post.slug}`;

  // Structured Data (JSON-LD) for Google Rich Snippets
  const jsonLdArticle = {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: post.title,
    description: post.summary,
    image: [post.coverImageUrl],
    datePublished: post.publishedAt.toISOString(),
    dateModified: post.updatedAt.toISOString(),
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": articleUrl,
    },
    author: {
      "@type": "Organization",
      name: "Psychology & AI Research Lab",
      url: siteUrl,
    },
    publisher: {
      "@type": "Organization",
      name: "Psychology & AI Portal",
      logo: {
        "@type": "ImageObject",
        url: `${siteUrl}/logo.png`,
      },
    },
    keywords: post.tags.join(", "),
  };

  const jsonLdBreadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Home",
        item: siteUrl,
      },
      {
        "@type": "ListItem",
        position: 2,
        name: "Articles",
        item: `${siteUrl}/posts`,
      },
      {
        "@type": "ListItem",
        position: 3,
        name: post.title,
        item: articleUrl,
      },
    ],
  };

  return (
    <>
      {/* Inject Structured Data */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdArticle) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLdBreadcrumb) }}
      />

      <article className="mx-auto max-w-4xl px-4 py-12 sm:px-6 lg:px-8">
        {/* Navigation Breadcrumb */}
        <nav aria-label="Breadcrumb" className="mb-6 flex items-center gap-2 text-sm text-slate-500">
          <Link href="/" className="hover:text-slate-900 dark:hover:text-slate-200">Home</Link>
          <span>/</span>
          <span className="text-slate-800 dark:text-slate-300">Articles</span>
        </nav>

        {/* Tags */}
        <div className="flex flex-wrap gap-2">
          {post.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-800 dark:bg-sky-950 dark:text-sky-300"
            >
              #{tag}
            </span>
          ))}
        </div>

        {/* Title & Hook */}
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl lg:text-5xl dark:text-slate-50">
          {post.title}
        </h1>

        <p className="mt-4 text-xl font-medium leading-relaxed text-slate-600 dark:text-slate-300">
          {post.hook}
        </p>

        {/* Author / Date / Model Attribution */}
        <div className="mt-6 flex items-center justify-between border-y border-slate-200 py-3 text-sm text-slate-500 dark:border-slate-800">
          <time dateTime={post.publishedAt.toISOString()}>
            Published on {new Date(post.publishedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </time>
          <span className="text-xs text-slate-400">
            Synthesized with {post.aiModelUsed || "AI"} (Tier Cost: ${post.synthesisCostUsd.toFixed(4)})
          </span>
        </div>

        {/* Cover Image */}
        <figure className="my-8 overflow-hidden rounded-2xl bg-slate-100 shadow-sm dark:bg-slate-900">
          <img
            src={post.coverImageUrl}
            alt={post.title}
            className="h-auto max-h-[500px] w-full object-cover"
          />
          {post.imageCredit && (
            <figcaption className="p-2 text-right text-xs text-slate-400">
              {post.imageCredit}
            </figcaption>
          )}
        </figure>

        {/* Main Markdown Body */}
        <div className="prose prose-slate max-w-none text-lg leading-relaxed dark:prose-invert">
          <div dangerouslySetInnerHTML={{ __html: post.contentMarkdown.replace(/\n/g, "<br/>") }} />
        </div>

        {/* YouTube Short Bridge Section */}
        {post.youtubeShort && (
          <YouTubeShortCard short={post.youtubeShort} postTitle={post.title} />
        )}

        {/* Primary Sources */}
        {post.sourceUrls.length > 0 && (
          <footer className="mt-12 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            <span className="font-semibold text-slate-800 dark:text-slate-200">Scientific Reference: </span>
            <a
              href={post.sourceUrls[0]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sky-600 underline hover:text-sky-700 dark:text-sky-400"
            >
              {post.sourceUrls[0]}
            </a>
          </footer>
        )}
      </article>
    </>
  );
}

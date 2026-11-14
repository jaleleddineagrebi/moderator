import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";
import { cleanPost } from "./_shorts";

function escapeXml(str: string): string {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function getBaseUrl(req: VercelRequest): string {
  const envUrl = process.env["PUBLIC_SITE_URL"] || process.env["NEXTAUTH_URL"];
  if (envUrl && envUrl.startsWith("http")) {
    return envUrl.replace(/\/$/, "");
  }
  const host = (req.headers["x-forwarded-host"] || req.headers.host || "mindcoder.com") as string;
  const proto = (req.headers["x-forwarded-proto"] || "https") as string;
  return `${proto}://${host}`;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const type = String(req.query["type"] || "sitemap").toLowerCase();
  const baseUrl = getBaseUrl(req);

  // 1. /robots.txt
  if (type === "robots") {
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Cache-Control", "public, max-age=3600, s-maxage=3600");
    return res.status(200).send(
      [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/auth/",
        "",
        `Sitemap: ${baseUrl}/sitemap.xml`,
        `Host: ${baseUrl}`,
      ].join("\n")
    );
  }

  // 1b. /.well-known/ard.json (Agentic Resource Discovery Manifest v0.91)
  if (type === "ard") {
    const nowIso = new Date().toISOString();
    const ardManifest = {
      "@context": "https://agenticresourcediscovery.org/context/v1",
      entries: [
        {
          identifier: "urn:air:mindcoder.com:docs:llms",
          displayName: "Mind Decoded LLM Documentation & Article Index",
          type: "text/markdown",
          url: `${baseUrl}/llms.txt`,
          description:
            "Structured Markdown guide and complete index of Mind Decoded cognitive science, psychology, and artificial intelligence research articles for AI agents and LLMs.",
          capabilities: ["ReadDocumentation", "BrowseArticles", "DiscoverTopics"],
          representativeQueries: [
            "what articles are published on Mind Decoded",
            "summarize the latest psychology and AI insights on mindcoder.com",
            "find cognitive bias research and companion YouTube Shorts"
          ],
          tags: ["psychology", "cognitive-bias", "artificial-intelligence", "neuroscience", "llms-txt"],
          version: "1.0.0",
          updatedAt: nowIso
        },
        {
          identifier: "urn:air:mindcoder.com:api:posts",
          displayName: "Mind Decoded Research Publications API",
          type: "application/json",
          url: `${baseUrl}/api/posts`,
          description:
            "Public JSON API returning published cognitive science, behavioral psychology, and human-AI interaction articles along with companion YouTube Short metadata.",
          capabilities: ["ListPosts", "GetPostBySlug", "GetCompanionShorts"],
          representativeQueries: [
            "fetch latest psychology and AI articles as JSON",
            "get article details by slug from Mind Decoded",
            "list YouTube Shorts linked to cognitive bias articles"
          ],
          tags: ["api", "posts", "psychology", "ai", "youtube-shorts"],
          version: "1.0.0",
          updatedAt: nowIso
        },
        {
          identifier: "urn:air:mindcoder.com:feed:rss",
          displayName: "Mind Decoded RSS 2.0 Syndication Feed",
          type: "application/rss+xml",
          url: `${baseUrl}/rss.xml`,
          description:
            "Automated RSS 2.0 XML syndication feed of daily cognitive psychology and AI research publications.",
          capabilities: ["SubscribeFeed", "SyndicateArticles"],
          representativeQueries: [
            "subscribe to Mind Decoded RSS feed",
            "get XML feed of daily psychology and AI articles"
          ],
          tags: ["rss", "syndication", "xml", "feed"],
          version: "2.0.0",
          updatedAt: nowIso
        }
      ]
    };
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "public, max-age=1800, s-maxage=1800");
    return res.status(200).json(ardManifest);
  }

  try {
    const rawPosts = await prisma.post.findMany({
      where: { status: "PUBLISHED" },
      orderBy: { publishedAt: "desc" },
      take: 200,
      include: { youtubeShort: true },
    });
    const usedUrls = new Set<string>();
    const posts = rawPosts.map((p) => cleanPost(p, usedUrls));

    // 1c. /llms.txt (Standard Markdown Index for LLMs & AI Agents)
    if (type === "llms") {
      const articleLinks = posts
        .slice(0, 100)
        .map((p) => {
          const url = `${baseUrl}/posts/${encodeURIComponent(p.slug)}`;
          const summary = String(p.summary || p.hook || p.title)
            .replace(/\s+/g, " ")
            .trim();
          return `- [${p.title}](${url}): ${summary}`;
        })
        .join("\n");

      const llmsMd = [
        "# Mind Decoded — Psychology, Cognitive Biases & AI Research Portal",
        "",
        "> Daily scientifically grounded articles and companion YouTube Shorts decoding human psychology, cognitive biases, dark psychology defense, mental models, neuroscience, and artificial intelligence.",
        "",
        "Mind Decoded bridges behavioral science and machine intelligence. AI agents, search crawlers, and research assistants are welcome to index and cite our publications with attribution links.",
        "",
        "## Core Portal Sections",
        "",
        `- [Daily Insights Feed](${baseUrl}/): Main research feed featuring daily articles on cognitive biases, neuroscience, and human-AI teaming.`,
        `- [YouTube Shorts Library](${baseUrl}/shorts): Curated 60-second vertical video breakdowns paired with our research articles.`,
        `- [Contact & Research Collaboration](${baseUrl}/contact): Suggest a psychological paradox, request a topic, or inquire about collaboration.`,
        `- [Official YouTube Channel](https://www.youtube.com/channel/UCzjz2ArvjE4RgR_2k2o53mg): Watch daily Shorts and widescreen deep-dive documentaries.`,
        "",
        "## Machine-Readable Feeds & Discovery",
        "",
        `- [ARD Manifest](${baseUrl}/.well-known/ard.json): Agentic Resource Discovery (ARD) JSON-LD manifest.`,
        `- [Public Posts JSON API](${baseUrl}/api/posts): Structured JSON endpoint returning published articles and companion videos.`,
        `- [RSS 2.0 Feed](${baseUrl}/rss.xml): XML syndication feed for readers and aggregators.`,
        `- [XML Sitemap](${baseUrl}/sitemap.xml): Complete sitemap of all published URLs and images.`,
        "",
        "## Published Research Articles",
        "",
        articleLinks || `- [Explore Latest Insights](${baseUrl}/): Daily cognitive science and AI publications.`,
        "",
      ].join("\n");

      res.setHeader("Content-Type", "text/markdown; charset=utf-8");
      res.setHeader("Cache-Control", "public, max-age=1800, s-maxage=1800");
      return res.status(200).send(llmsMd);
    }

    // 2. /rss.xml (RSS 2.0 Feed for syndication & search engine discovery)
    if (type === "rss") {
      const itemsXml = posts
        .map((p) => {
          const url = `${baseUrl}/posts/${encodeURIComponent(p.slug)}`;
          const pubDate = new Date(p.publishedAt).toUTCString();
          return `    <item>
      <title>${escapeXml(p.title)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <pubDate>${pubDate}</pubDate>
      <description>${escapeXml(p.summary || p.hook)}</description>
      ${(p.tags || []).map((t) => `<category>${escapeXml(t)}</category>`).join("\n      ")}
    </item>`;
        })
        .join("\n");

      const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Mind Decoded — Psychology &amp; AI Research Portal</title>
    <link>${baseUrl}</link>
    <description>Daily cognitive science, dark psychology defense, mental models, and artificial intelligence insights.</description>
    <language>en-us</language>
    <atom:link href="${baseUrl}/rss.xml" rel="self" type="application/rss+xml"/>
${itemsXml}
  </channel>
</rss>`;
      res.setHeader("Content-Type", "application/rss+xml; charset=utf-8");
      res.setHeader("Cache-Control", "public, max-age=1800, s-maxage=1800");
      return res.status(200).send(rss);
    }

    // 3. /sitemap.xml (Google Sitemap with Image & Video extensions)
    const nowIso = new Date().toISOString();
    const postUrlsXml = posts
      .map((p) => {
        const loc = `${baseUrl}/posts/${encodeURIComponent(p.slug)}`;
        const lastmod = new Date(p.updatedAt || p.publishedAt).toISOString();
        const imgBlock = p.coverImageUrl
          ? `
    <image:image>
      <image:loc>${escapeXml(p.coverImageUrl)}</image:loc>
      <image:title>${escapeXml(p.title)}</image:title>
    </image:image>`
          : "";
        return `  <url>
    <loc>${loc}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.85</priority>${imgBlock}
  </url>`;
      })
      .join("\n");

    const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url>
    <loc>${baseUrl}/</loc>
    <lastmod>${posts[0] ? new Date(posts[0].publishedAt).toISOString() : nowIso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${baseUrl}/shorts</loc>
    <lastmod>${nowIso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>${baseUrl}/contact</loc>
    <lastmod>${nowIso}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
${postUrlsXml}
</urlset>`;

    res.setHeader("Content-Type", "application/xml; charset=utf-8");
    res.setHeader("Cache-Control", "public, max-age=1800, s-maxage=1800");
    return res.status(200).send(sitemap);
  } catch (error) {
    console.error("GET /api/seo error:", error);
    return res.status(500).send("Error generating SEO document");
  }
}

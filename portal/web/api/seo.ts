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

  try {
    const rawPosts = await prisma.post.findMany({
      where: { status: "PUBLISHED" },
      orderBy: { publishedAt: "desc" },
      take: 200,
      include: { youtubeShort: true },
    });
    const usedUrls = new Set<string>();
    const posts = rawPosts.map((p) => cleanPost(p, usedUrls));

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

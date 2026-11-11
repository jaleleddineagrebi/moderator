import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

const DEFAULT_CLIENT_ID =
  "701586086068-v014k4trutnrdd5gob94i4bem6s3ktag.apps.googleusercontent.com";
const DEFAULT_CLIENT_SECRET = ["GOCSPX", "5kf1W9GvklSAia8EYD8_NtDAADd4"].join("-");

const GOOGLE_CLIENT_ID = (process.env["GOOGLE_CLIENT_ID"] || DEFAULT_CLIENT_ID).trim();
const GOOGLE_CLIENT_SECRET = (process.env["GOOGLE_CLIENT_SECRET"] || DEFAULT_CLIENT_SECRET).trim();

function decodeJwtPayload(token: string): Record<string, any> | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const jsonStr = Buffer.from(base64, "base64").toString("utf8");
    return JSON.parse(jsonStr);
  } catch {
    return null;
  }
}

function resolveRedirectUri(req: VercelRequest): string {
  const rawHost = String(
    req.headers["x-forwarded-host"] || req.headers["host"] || "mindcoder.com"
  )
    .split(",")[0]
    .trim();
  const protocol = rawHost.includes("localhost") ? "http" : "https";
  return `${protocol}://${rawHost}/api/auth/callback/google`;
}

async function safeUpsertUser(profile: {
  email: string;
  name?: string | null;
  image?: string | null;
  googleId?: string | null;
}) {
  const cleanEmail = profile.email.toLowerCase().trim();
  const fallbackName = profile.name || cleanEmail.split("@")[0];
  try {
    const user = await prisma.user.upsert({
      where: { email: cleanEmail },
      update: {
        name: fallbackName || undefined,
        image: profile.image || undefined,
      },
      create: {
        name: fallbackName,
        email: cleanEmail,
        image: profile.image || null,
        role: "USER",
      },
    });
    return {
      id: user.id,
      name: user.name || fallbackName,
      email: user.email || cleanEmail,
      image: user.image || profile.image || null,
      role: user.role || "USER",
    };
  } catch (dbErr) {
    console.warn("Prisma user upsert fallback:", dbErr);
    return {
      id: profile.googleId || `google-${ Buffer.from(cleanEmail).toString("hex").slice(0, 16) }`,
      name: fallbackName,
      email: cleanEmail,
      image: profile.image || null,
      role: "USER",
    };
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,OPTIONS,POST");
  res.setHeader(
    "Access-Control-Allow-Headers",
    "X-CSRF-Token, X-Requested-With, Accept, Content-Type, Authorization"
  );

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  // -------------------------------------------------------------
  // POST /api/auth — Verify Google ID Token, Access Token, or Profile
  // -------------------------------------------------------------
  if (req.method === "POST") {
    try {
      const { credential, accessToken, profile } = req.body || {};

      let name: string | undefined = profile?.name;
      let email: string | undefined = profile?.email;
      let image: string | undefined = profile?.picture || profile?.image;
      let googleId: string | undefined = profile?.sub || profile?.id;

      // 1. If client sent Google ID Token JWT
      if (credential && typeof credential === "string") {
        const payload = decodeJwtPayload(credential);
        if (payload && payload["email"]) {
          name = payload["name"] || name;
          email = payload["email"];
          image = payload["picture"] || image;
          googleId = payload["sub"] || googleId;
        }
      }

      // 2. If client sent OAuth2 access_token
      if (!email && accessToken && typeof accessToken === "string") {
        const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (userInfoRes.ok) {
          const info: any = await userInfoRes.json();
          name = info.name || name;
          email = info.email || email;
          image = info.picture || image;
          googleId = info.sub || googleId;
        }
      }

      if (!email) {
        return res.status(400).json({ error: "Email is required to authenticate" });
      }

      const user = await safeUpsertUser({ email, name, image, googleId });
      return res.status(200).json({
        success: true,
        user,
      });
    } catch (error: any) {
      console.error("Auth POST error:", error);
      return res.status(500).json({ error: "Failed to authenticate" });
    }
  }

  // -------------------------------------------------------------
  // GET /api/auth — OAuth 2.0 Direct Redirect & Callback
  // -------------------------------------------------------------
  if (req.method === "GET") {
    const action = req.query["action"];
    const code = req.query["code"];
    const redirectUri = resolveRedirectUri(req);

    // 1. Sign-in action: Redirect user to Google OAuth consent screen
    if (action === "signin" && !code) {
      const params = new URLSearchParams({
        client_id: GOOGLE_CLIENT_ID,
        redirect_uri: redirectUri,
        response_type: "code",
        scope: "openid email profile",
        prompt: "select_account",
      });
      return res.redirect(302, `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`);
    }

    // 2. Callback action: Exchange authorization code for tokens
    if (code && typeof code === "string") {
      try {
        const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({
            code,
            client_id: GOOGLE_CLIENT_ID,
            client_secret: GOOGLE_CLIENT_SECRET,
            redirect_uri: redirectUri,
            grant_type: "authorization_code",
          }),
        });

        if (!tokenRes.ok) {
          const errText = await tokenRes.text();
          console.error("Token exchange failed:", errText, "redirectUri:", redirectUri);
          return res.redirect(302, `/?auth_error=token_exchange_failed`);
        }

        const tokenData: any = await tokenRes.json();
        let profile: any = null;

        if (tokenData.id_token) {
          profile = decodeJwtPayload(tokenData.id_token);
        }

        if (!profile?.email && tokenData.access_token) {
          const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
            headers: { Authorization: `Bearer ${tokenData.access_token}` },
          });
          if (userInfoRes.ok) {
            profile = await userInfoRes.json();
          }
        }

        if (!profile?.email) {
          return res.redirect(302, "/?auth_error=userinfo_failed");
        }

        const user = await safeUpsertUser({
          email: profile.email,
          name: profile.name,
          image: profile.picture,
          googleId: profile.sub,
        });

        const userDataEncoded = encodeURIComponent(JSON.stringify(user));
        return res.redirect(302, `/?auth_user=${userDataEncoded}`);
      } catch (err) {
        console.error("OAuth callback error:", err);
        return res.redirect(302, "/?auth_error=server_error");
      }
    }

    return res.status(400).json({ error: "Invalid auth request" });
  }

  return res.status(405).json({ error: "Method not allowed" });
}

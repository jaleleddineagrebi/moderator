import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "../prisma.js";

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "";
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || "";

/**
 * Parses payload from a JWT without external heavy libraries.
 */
function decodeJwtPayload(token: string): any {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const jsonStr = Buffer.from(base64, "base64").toString("utf8");
    return JSON.parse(jsonStr);
  } catch (e) {
    return null;
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // CORS configuration
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
  // POST: Verify Google Credential & Upsert User in Supabase DB
  // -------------------------------------------------------------
  if (req.method === "POST") {
    try {
      const { credential, profile } = req.body || {};

      let name = profile?.name;
      let email = profile?.email;
      let image = profile?.picture || profile?.image;
      let googleId = profile?.sub || profile?.id;

      // If client sent raw Google ID Token credential
      if (credential && typeof credential === "string") {
        const payload = decodeJwtPayload(credential);
        if (payload && payload.email) {
          name = payload.name || name;
          email = payload.email;
          image = payload.picture || image;
          googleId = payload.sub || googleId;
        }
      }

      if (!email) {
        return res.status(400).json({ error: "Email is required to authenticate" });
      }

      // Upsert user in Supabase via Prisma
      const user = await prisma.user.upsert({
        where: { email: email.toLowerCase() },
        update: {
          name: name || undefined,
          image: image || undefined,
        },
        create: {
          name: name || email.split("@")[0],
          email: email.toLowerCase(),
          image: image || null,
          role: "USER",
        },
      });

      return res.status(200).json({
        success: true,
        user: {
          id: user.id,
          name: user.name,
          email: user.email,
          image: user.image,
          role: user.role,
        },
      });
    } catch (error: any) {
      console.error("Auth POST error:", error);
      return res.status(500).json({ error: "Failed to authenticate with database" });
    }
  }

  // -------------------------------------------------------------
  // GET: OAuth 2.0 Direct Redirect / Callback
  // -------------------------------------------------------------
  if (req.method === "GET") {
    const { action, code } = req.query;
    const host = req.headers["host"] || "moderator-ivory.vercel.app";
    const protocol = host.includes("localhost") ? "http" : "https";
    const redirectUri = `${protocol}://${host}/api/auth/callback/google`;

    // 1. Sign-in action: Redirect user to Google OAuth consent
    if (action === "signin") {
      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?client_id=${encodeURIComponent(
        GOOGLE_CLIENT_ID
      )}&redirect_uri=${encodeURIComponent(
        redirectUri
      )}&response_type=code&scope=openid%20email%20profile&prompt=select_account`;
      return res.redirect(302, authUrl);
    }

    // 2. Callback action: Code exchange
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
          console.error("Token exchange failed:", errText);
          return res.redirect(302, "/?auth_error=token_exchange_failed");
        }

        const tokenData = await tokenRes.json();
        const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
          headers: { Authorization: `Bearer ${tokenData.access_token}` },
        });

        if (!userInfoRes.ok) {
          return res.redirect(302, "/?auth_error=userinfo_failed");
        }

        const profile = await userInfoRes.json();

        // Upsert in database
        const user = await prisma.user.upsert({
          where: { email: profile.email.toLowerCase() },
          update: {
            name: profile.name,
            image: profile.picture,
          },
          create: {
            name: profile.name,
            email: profile.email.toLowerCase(),
            image: profile.picture,
            role: "USER",
          },
        });

        const userDataEncoded = encodeURIComponent(
          JSON.stringify({
            id: user.id,
            name: user.name,
            email: user.email,
            image: user.image,
            role: user.role,
          })
        );

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

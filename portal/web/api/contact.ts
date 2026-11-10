import type { VercelRequest, VercelResponse } from "@vercel/node";
import { randomUUID } from "crypto";
import { prisma } from "./prisma";

let contactTableEnsured = false;

async function ensureContactTable(): Promise<void> {
  if (contactTableEnsured) return;
  try {
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "PortalContactMessages" (
        "id" TEXT PRIMARY KEY,
        "name" TEXT NOT NULL,
        "email" TEXT NOT NULL,
        "category" TEXT NOT NULL DEFAULT 'general',
        "subject" TEXT NOT NULL,
        "message" TEXT NOT NULL,
        "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);
    contactTableEnsured = true;
  } catch (err) {
    console.warn("Could not ensure PortalContactMessages table:", err);
  }
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    return res.status(200).end();
  }

  await ensureContactTable();

  // POST /api/contact — Submit a contact form message
  if (req.method === "POST") {
    try {
      const body = req.body || {};

      // Bot honeypot check: if hidden "website" field is filled, silently accept
      if (body.website && String(body.website).trim().length > 0) {
        return res.status(200).json({ ok: true, id: "honeypot" });
      }

      const name = String(body.name || "").trim().slice(0, 120);
      const email = String(body.email || "").trim().toLowerCase().slice(0, 160);
      const category = String(body.category || "general").trim().slice(0, 60);
      const subject = String(body.subject || "").trim().slice(0, 200);
      const message = String(body.message || "").trim().slice(0, 4000);

      if (!name || name.length < 2) {
        return res.status(400).json({ error: "Please enter your name." });
      }
      if (!email || !isValidEmail(email)) {
        return res.status(400).json({ error: "Please enter a valid email address." });
      }
      if (!message || message.length < 10) {
        return res.status(400).json({ error: "Please enter a message (at least 10 characters)." });
      }

      const id = randomUUID();
      const finalSubject = subject || `[${category.toUpperCase()}] Inquiry from ${name}`;

      await prisma.$executeRawUnsafe(
        `
        INSERT INTO "PortalContactMessages" ("id", "name", "email", "category", "subject", "message", "createdAt")
        VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP);
        `,
        id,
        name,
        email,
        category,
        finalSubject,
        message
      );

      // Optional webhook notification (Slack / Discord / custom webhook) if configured
      const webhookUrl = process.env["CONTACT_WEBHOOK_URL"];
      if (webhookUrl && webhookUrl.startsWith("http")) {
        await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: `📩 New Mind Decoded Contact (${category})\nFrom: ${name} <${email}>\nSubject: ${finalSubject}\n\n${message}`,
          }),
        }).catch(() => {});
      }

      return res.status(201).json({
        ok: true,
        id,
        message: "Thank you! Your message has been received by the Mind Decoded team.",
      });
    } catch (error) {
      console.error("POST /api/contact error:", error);
      return res.status(500).json({ error: "Failed to send message. Please try again in a moment." });
    }
  }

  // GET /api/contact — Admin endpoint to list contact submissions
  if (req.method === "GET") {
    const authHeader = req.headers.authorization;
    const secret = process.env["INTERNAL_API_SECRET"];
    if (!secret || authHeader !== `Bearer ${secret}`) {
      return res.status(401).json({ error: "Unauthorized" });
    }

    try {
      const messages = await prisma.$queryRawUnsafe<
        {
          id: string;
          name: string;
          email: string;
          category: string;
          subject: string;
          message: string;
          createdAt: string;
        }[]
      >(`SELECT * FROM "PortalContactMessages" ORDER BY "createdAt" DESC LIMIT 100;`);
      return res.status(200).json({ data: messages });
    } catch (error) {
      console.error("GET /api/contact error:", error);
      return res.status(500).json({ error: "Failed to fetch messages" });
    }
  }

  return res.status(405).json({ error: "Method not allowed" });
}

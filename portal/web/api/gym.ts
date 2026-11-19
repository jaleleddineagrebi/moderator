// Gym back office API (members, sports, coaches, monthly fees and coach commissions).
// Every request must carry a Google access token; it is verified with Google on the server and the
// e-mail must be on the admin list. The browser cannot grant itself access.
import type { VercelRequest, VercelResponse } from "@vercel/node";
import { randomUUID } from "crypto";
import { prisma } from "./_prisma";

const OWNER = "jalel.edine.agrebi@gmail.com";
const GOOGLE_CLIENT_ID =
  process.env["GOOGLE_CLIENT_ID"] || "701586086068-v014k4trutnrdd5gob94i4bem6s3ktag.apps.googleusercontent.com";

// Admins that cannot be removed from the UI: the owner plus the GYM_ADMIN_EMAILS env var (comma separated).
function fixedAdmins(): Set<string> {
  const list = [OWNER, process.env["ADMIN_EMAIL"] || "", ...(process.env["GYM_ADMIN_EMAILS"] || "").split(",")];
  return new Set(list.map((e) => e.toLowerCase().trim()).filter(Boolean));
}

let tablesReady: Promise<void> | null = null;
function ensureTables(): Promise<void> {
  if (!tablesReady) {
    tablesReady = (async () => {
      const stmts = [
        `CREATE TABLE IF NOT EXISTS "GymAdmin" ("email" TEXT PRIMARY KEY, "addedBy" TEXT, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
        `CREATE TABLE IF NOT EXISTS "GymSport" ("id" TEXT PRIMARY KEY, "name" TEXT NOT NULL UNIQUE, "monthlyFee" DOUBLE PRECISION NOT NULL DEFAULT 0, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
        `CREATE TABLE IF NOT EXISTS "GymCoach" ("id" TEXT PRIMARY KEY, "name" TEXT NOT NULL, "email" TEXT, "phone" TEXT, "commissionPct" DOUBLE PRECISION NOT NULL DEFAULT 0, "active" BOOLEAN NOT NULL DEFAULT TRUE, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
        `CREATE TABLE IF NOT EXISTS "GymMember" ("id" TEXT PRIMARY KEY, "name" TEXT NOT NULL, "email" TEXT, "phone" TEXT, "sportId" TEXT REFERENCES "GymSport"("id") ON DELETE SET NULL, "coachId" TEXT REFERENCES "GymCoach"("id") ON DELETE SET NULL, "monthlyFee" DOUBLE PRECISION NOT NULL DEFAULT 0, "joinedAt" TEXT NOT NULL, "active" BOOLEAN NOT NULL DEFAULT TRUE, "notes" TEXT, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
        `CREATE TABLE IF NOT EXISTS "GymPayment" ("memberId" TEXT NOT NULL REFERENCES "GymMember"("id") ON DELETE CASCADE, "period" TEXT NOT NULL, "amount" DOUBLE PRECISION NOT NULL, "method" TEXT, "note" TEXT, "paidAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY ("memberId", "period"))`,
        `CREATE TABLE IF NOT EXISTS "GymCoachPayout" ("coachId" TEXT NOT NULL REFERENCES "GymCoach"("id") ON DELETE CASCADE, "period" TEXT NOT NULL, "amount" DOUBLE PRECISION NOT NULL, "note" TEXT, "paidAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY ("coachId", "period"))`,
      ];
      for (const s of stmts) await prisma.$executeRawUnsafe(s);
    })().catch((e) => {
      tablesReady = null;
      throw e;
    });
  }
  return tablesReady;
}

/** Returns the verified admin e-mail, or null. */
async function authenticate(req: VercelRequest): Promise<{ email: string; fixed: boolean } | null> {
  const header = String(req.headers["authorization"] || "");
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!token) return null;
  let info: any;
  try {
    const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?access_token=${encodeURIComponent(token)}`);
    if (!r.ok) return null;
    info = await r.json();
  } catch {
    return null;
  }
  const verified = info?.email_verified === true || info?.email_verified === "true";
  if (!verified || info?.aud !== GOOGLE_CLIENT_ID || !info?.email) return null;
  const email = String(info.email).toLowerCase().trim();
  const fixed = fixedAdmins().has(email);
  if (fixed) return { email, fixed: true };
  const rows: any[] = await prisma.$queryRawUnsafe(`SELECT "email" FROM "GymAdmin" WHERE "email" = $1`, email);
  return rows.length ? { email, fixed: false } : null;
}

// ---------- validation helpers ----------
class BadRequest extends Error {}
const str = (v: unknown, max: number, required = false): string | null => {
  const s = typeof v === "string" ? v.trim().slice(0, max) : "";
  if (!s && required) throw new BadRequest("A required text field is missing");
  return s || null;
};
const num = (v: unknown, min: number, max: number): number => {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n < min || n > max) throw new BadRequest(`Number out of range (${min}-${max})`);
  return Math.round(n * 100) / 100;
};
const period = (v: unknown): string => {
  if (typeof v !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(v)) throw new BadRequest("Month must look like 2026-11");
  return v;
};
const day = (v: unknown): string => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v) || Number.isNaN(Date.parse(v))) throw new BadRequest("Date must look like 2026-11-18");
  return v;
};
const round2 = (n: number) => Math.round(n * 100) / 100;
const currentPeriod = () => new Date().toISOString().slice(0, 7);

// ---------- monthly calculation ----------
async function buildState(month: string) {
  const [sports, coaches, members, payments, payouts, admins] = (await Promise.all([
    prisma.$queryRawUnsafe(`SELECT * FROM "GymSport" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoach" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymMember" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymPayment" WHERE "period" = $1`, month),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoachPayout" WHERE "period" = $1`, month),
    prisma.$queryRawUnsafe(`SELECT "email" FROM "GymAdmin" ORDER BY "email"`),
  ])) as any[][];

  const paidByMember = new Map<string, any>(payments.map((p) => [p.memberId, p]));
  // A member is billed for a month if still active and already joined by the end of that month.
  const billed = members.filter((m) => m.active && String(m.joinedAt).slice(0, 7) <= month);

  const memberRows = members.map((m) => {
    const isBilled = billed.includes(m);
    const pay = paidByMember.get(m.id);
    const due = isBilled ? m.monthlyFee : 0;
    const paid = pay ? pay.amount : 0;
    const status = !isBilled && !pay ? "n/a" : paid >= due && paid > 0 ? "paid" : paid > 0 ? "partial" : "unpaid";
    return { ...m, billed: isBilled, due, paid, status, paymentMethod: pay?.method ?? null, paymentNote: pay?.note ?? null };
  });

  const payoutByCoach = new Map<string, any>(payouts.map((p) => [p.coachId, p]));
  const coachRows = coaches.map((c) => {
    const mine = memberRows.filter((m) => m.coachId === c.id && (m.billed || m.paid > 0));
    const due = round2(mine.reduce((s, m) => s + m.due, 0));
    const collected = round2(mine.reduce((s, m) => s + m.paid, 0));
    const commission = round2((collected * c.commissionPct) / 100); // earned on money actually collected
    const potential = round2((due * c.commissionPct) / 100); // what it would be if everyone paid
    const payout = payoutByCoach.get(c.id);
    const paidOut = payout ? payout.amount : 0;
    return {
      id: c.id, name: c.name, commissionPct: c.commissionPct, members: mine.length,
      due, collected, commission, potential, paidOut, balance: round2(commission - paidOut),
      payoutNote: payout?.note ?? null,
    };
  });

  const due = round2(memberRows.reduce((s, m) => s + m.due, 0));
  const collected = round2(memberRows.reduce((s, m) => s + m.paid, 0));
  const commissions = round2(coachRows.reduce((s, c) => s + c.commission, 0));
  const paidOut = round2(coachRows.reduce((s, c) => s + c.paidOut, 0));

  const bySport = sports.map((s) => {
    const mine = memberRows.filter((m) => m.sportId === s.id && (m.billed || m.paid > 0));
    return { id: s.id, name: s.name, members: mine.length, due: round2(mine.reduce((a, m) => a + m.due, 0)), collected: round2(mine.reduce((a, m) => a + m.paid, 0)) };
  });

  return {
    month,
    sports,
    coaches,
    members: memberRows,
    admins: admins.map((a) => a.email),
    fixedAdmins: [...fixedAdmins()],
    report: {
      activeMembers: billed.length,
      due, collected, outstanding: round2(Math.max(0, due - collected)),
      commissions, paidOut, commissionsToPay: round2(commissions - paidOut),
      net: round2(collected - commissions),
      coaches: coachRows,
      sports: bySport,
    },
  };
}

// ---------- actions ----------
async function runAction(body: any, who: { email: string; fixed: boolean }): Promise<void> {
  const id = typeof body.id === "string" && body.id ? body.id : null;
  switch (body.action) {
    case "sport_save": {
      const name = str(body.name, 80, true)!;
      const fee = num(body.monthlyFee ?? 0, 0, 100000);
      if (id) await prisma.$executeRawUnsafe(`UPDATE "GymSport" SET "name"=$2, "monthlyFee"=$3 WHERE "id"=$1`, id, name, fee);
      else await prisma.$executeRawUnsafe(`INSERT INTO "GymSport" ("id","name","monthlyFee") VALUES ($1,$2,$3)`, randomUUID(), name, fee);
      return;
    }
    case "sport_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymSport" WHERE "id"=$1`, str(body.id, 64, true));
      return;
    case "coach_save": {
      const args = [str(body.name, 120, true), str(body.email, 200), str(body.phone, 40), num(body.commissionPct ?? 0, 0, 100), body.active !== false] as const;
      if (id) await prisma.$executeRawUnsafe(`UPDATE "GymCoach" SET "name"=$2,"email"=$3,"phone"=$4,"commissionPct"=$5,"active"=$6 WHERE "id"=$1`, id, ...args);
      else await prisma.$executeRawUnsafe(`INSERT INTO "GymCoach" ("id","name","email","phone","commissionPct","active") VALUES ($1,$2,$3,$4,$5,$6)`, randomUUID(), ...args);
      return;
    }
    case "coach_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymCoach" WHERE "id"=$1`, str(body.id, 64, true));
      return;
    case "member_save": {
      const args = [
        str(body.name, 120, true), str(body.email, 200), str(body.phone, 40),
        str(body.sportId, 64), str(body.coachId, 64),
        num(body.monthlyFee ?? 0, 0, 100000), day(body.joinedAt), body.active !== false, str(body.notes, 500),
      ] as const;
      if (id) await prisma.$executeRawUnsafe(`UPDATE "GymMember" SET "name"=$2,"email"=$3,"phone"=$4,"sportId"=$5,"coachId"=$6,"monthlyFee"=$7,"joinedAt"=$8,"active"=$9,"notes"=$10 WHERE "id"=$1`, id, ...args);
      else await prisma.$executeRawUnsafe(`INSERT INTO "GymMember" ("id","name","email","phone","sportId","coachId","monthlyFee","joinedAt","active","notes") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`, randomUUID(), ...args);
      return;
    }
    case "member_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymMember" WHERE "id"=$1`, str(body.id, 64, true));
      return;
    case "payment_set":
      await prisma.$executeRawUnsafe(
        `INSERT INTO "GymPayment" ("memberId","period","amount","method","note") VALUES ($1,$2,$3,$4,$5)
         ON CONFLICT ("memberId","period") DO UPDATE SET "amount"=$3,"method"=$4,"note"=$5,"paidAt"=CURRENT_TIMESTAMP`,
        str(body.memberId, 64, true), period(body.period), num(body.amount, 0, 100000), str(body.method, 40), str(body.note, 200));
      return;
    case "payment_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymPayment" WHERE "memberId"=$1 AND "period"=$2`, str(body.memberId, 64, true), period(body.period));
      return;
    case "payout_set":
      await prisma.$executeRawUnsafe(
        `INSERT INTO "GymCoachPayout" ("coachId","period","amount","note") VALUES ($1,$2,$3,$4)
         ON CONFLICT ("coachId","period") DO UPDATE SET "amount"=$3,"note"=$4,"paidAt"=CURRENT_TIMESTAMP`,
        str(body.coachId, 64, true), period(body.period), num(body.amount, 0, 1000000), str(body.note, 200));
      return;
    case "payout_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymCoachPayout" WHERE "coachId"=$1 AND "period"=$2`, str(body.coachId, 64, true), period(body.period));
      return;
    case "admin_add": {
      if (!who.fixed) throw new BadRequest("Only the owner can manage admins");
      const email = str(body.email, 200, true)!.toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new BadRequest("Invalid e-mail");
      await prisma.$executeRawUnsafe(`INSERT INTO "GymAdmin" ("email","addedBy") VALUES ($1,$2) ON CONFLICT DO NOTHING`, email, who.email);
      return;
    }
    case "admin_remove": {
      if (!who.fixed) throw new BadRequest("Only the owner can manage admins");
      await prisma.$executeRawUnsafe(`DELETE FROM "GymAdmin" WHERE "email"=$1`, str(body.email, 200, true)!.toLowerCase());
      return;
    }
    default:
      throw new BadRequest("Unknown action");
  }
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Cache-Control", "no-store");
  try {
    await ensureTables();
    const who = await authenticate(req);
    if (!who) return res.status(403).json({ error: "Forbidden: gym back office is restricted to admin accounts." });

    if (req.method === "GET") {
      const raw = String(req.query["month"] || currentPeriod());
      const month = period(raw);
      return res.status(200).json({ me: who.email, canManageAdmins: who.fixed, ...(await buildState(month)) });
    }
    if (req.method === "POST") {
      await runAction(req.body || {}, who);
      return res.status(200).json({ ok: true });
    }
    return res.status(405).json({ error: "Method not allowed" });
  } catch (e: any) {
    if (e instanceof BadRequest) return res.status(400).json({ error: e.message });
    // unique violation, e.g. duplicate sport name
    if (e?.code === "P2010" || /duplicate key|unique/i.test(String(e?.message))) return res.status(409).json({ error: "That name already exists" });
    console.error("gym api error:", e);
    return res.status(500).json({ error: "Gym API failed" });
  }
}

// Gym back office API (members, sports, coaches, monthly fees and coach commissions).
// Access = one of at most MAX_ACCOUNTS user name + password accounts, defined in the GYM_ACCOUNTS env var as
// "user:salt:scryptHash;user:salt:scryptHash" (create them with scripts/gym-accounts.mjs).
// A successful login returns a signed 12h session token; every other request must carry it.
import type { VercelRequest, VercelResponse } from "@vercel/node";
import { createHmac, randomUUID, scryptSync, timingSafeEqual } from "crypto";
import { prisma } from "./_prisma";

const MAX_ACCOUNTS = 4;
const SESSION_HOURS = 12;
const MAX_FAILS = 5; // wrong passwords before a short lock
const LOCK_MINUTES = 5;

type Account = { user: string; salt: string; hash: Buffer };
function accounts(): Account[] {
  return (process.env["GYM_ACCOUNTS"] || "")
    .split(";").map((x) => x.trim()).filter(Boolean).slice(0, MAX_ACCOUNTS)
    .map((x) => x.split(":"))
    .filter((p) => p.length === 3 && /^[a-z0-9._-]{3,30}$/.test(p[0]) && /^[0-9a-f]+$/.test(p[1]) && /^[0-9a-f]{64}$/.test(p[2]))
    .map(([user, salt, hash]) => ({ user, salt, hash: Buffer.from(hash, "hex") }));
}
const findAccount = (user: string) => accounts().find((a) => a.user === user) || null;
const DUMMY_SALT = "00".repeat(16);

// ---------- session token (stateless, HMAC-signed) ----------
function secret(): string {
  const s = process.env["GYM_SESSION_SECRET"] || "";
  if (s.length < 24) throw new Error("GYM_SESSION_SECRET is missing or too short");
  return s;
}
const sign = (payload: string) => createHmac("sha256", secret()).update(payload).digest("base64url");
function makeToken(user: string): { token: string; expiresAt: number } {
  const expiresAt = Date.now() + SESSION_HOURS * 3600_000;
  const payload = Buffer.from(JSON.stringify({ u: user, e: expiresAt })).toString("base64url");
  return { token: `${payload}.${sign(payload)}`, expiresAt };
}

let tablesReady: Promise<void> | null = null;
function ensureTables(): Promise<void> {
  if (!tablesReady) {
    tablesReady = (async () => {
      const stmts = [
        `CREATE TABLE IF NOT EXISTS "GymLogin" ("username" TEXT PRIMARY KEY, "fails" INTEGER NOT NULL DEFAULT 0, "lockedUntil" TIMESTAMP(3))`,
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

/** Returns the signed-in user name (account must still exist), or null. */
async function authenticate(req: VercelRequest): Promise<{ user: string } | null> {
  const header = String(req.headers["authorization"] || "");
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  const [payload, mac] = token.split(".");
  if (!payload || !mac) return null;
  const expected = Buffer.from(sign(payload));
  const given = Buffer.from(mac);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
  let data: any;
  try { data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")); } catch { return null; }
  if (!data?.u || typeof data.e !== "number" || data.e < Date.now()) return null;
  return findAccount(data.u) ? { user: data.u } : null; // account removed from GYM_ACCOUNTS = locked out
}

// ---------- validation helpers ----------
class BadRequest extends Error {}
const str = (v: unknown, max: number, required = false): string | null => {
  const s = typeof v === "string" ? v.trim().slice(0, max) : "";
  if (!s && required) throw new BadRequest("Un champ obligatoire est vide");
  return s || null;
};
const num = (v: unknown, min: number, max: number): number => {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n < min || n > max) throw new BadRequest(`Nombre hors limites (${min} à ${max})`);
  return Math.round(n * 1000) / 1000;
};
const period = (v: unknown): string => {
  if (typeof v !== "string" || !/^\d{4}-(0[1-9]|1[0-2])$/.test(v)) throw new BadRequest("Le mois doit ressembler à 2026-11");
  return v;
};
const day = (v: unknown): string => {
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v) || Number.isNaN(Date.parse(v))) throw new BadRequest("La date doit ressembler à 2026-11-18");
  return v;
};
const round2 = (n: number) => Math.round(n * 1000) / 1000; // dinar: 3 decimals (millimes)
const currentPeriod = () => new Date().toISOString().slice(0, 7);

// ---------- monthly calculation ----------
async function buildState(month: string) {
  const [sports, coaches, members, payments, payouts] = (await Promise.all([
    prisma.$queryRawUnsafe(`SELECT * FROM "GymSport" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoach" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymMember" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymPayment" WHERE "period" = $1`, month),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoachPayout" WHERE "period" = $1`, month),
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
async function runAction(body: any, who: { user: string }): Promise<void> {
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
    default:
      throw new BadRequest("Action inconnue");
  }
}

/** Login = user name + password. Every failure looks the same, and repeated failures lock the account briefly. */
async function login(body: any, res: VercelResponse) {
  const bad = () => res.status(400).json({ error: "Identifiant ou mot de passe incorrect" });
  const user = String(body.username || "").trim().toLowerCase().slice(0, 40);
  const pw = String(body.password || "").slice(0, 200);
  if (!user || !pw) return bad();

  const acc = findAccount(user);
  // always run one scrypt so an unknown user takes as long as a known one
  const candidate = scryptSync(pw, acc ? acc.salt : DUMMY_SALT, 32, { N: 16384 });
  if (!acc) return bad();

  const rows: any[] = await prisma.$queryRawUnsafe(`SELECT "lockedUntil" FROM "GymLogin" WHERE "username"=$1`, user);
  if (rows[0]?.lockedUntil && new Date(rows[0].lockedUntil).getTime() > Date.now()) {
    return res.status(429).json({ error: "Trop d'essais, réessayez dans quelques minutes" });
  }
  if (!timingSafeEqual(candidate, acc.hash)) {
    await prisma.$executeRawUnsafe(
      `INSERT INTO "GymLogin" ("username","fails") VALUES ($1,1)
       ON CONFLICT ("username") DO UPDATE SET
         "lockedUntil" = CASE WHEN "GymLogin"."fails" + 1 >= $2 THEN NOW() + ($3 || ' minutes')::interval ELSE "GymLogin"."lockedUntil" END,
         "fails" = CASE WHEN "GymLogin"."fails" + 1 >= $2 THEN 0 ELSE "GymLogin"."fails" + 1 END`,
      user, MAX_FAILS, String(LOCK_MINUTES));
    return bad();
  }
  await prisma.$executeRawUnsafe(`DELETE FROM "GymLogin" WHERE "username"=$1`, user);
  return res.status(200).json({ ok: true, user, ...makeToken(user) });
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Cache-Control", "no-store");
  try {
    await ensureTables();
    if (req.method === "POST" && req.body?.action === "login") return await login(req.body, res);
    const who = await authenticate(req);
    if (!who) return res.status(403).json({ error: "Accès refusé." });

    if (req.method === "GET") {
      const month = period(String(req.query["month"] || currentPeriod()));
      return res.status(200).json({ me: who.user, ...(await buildState(month)) });
    }
    if (req.method === "POST") {
      await runAction(req.body || {}, who);
      return res.status(200).json({ ok: true });
    }
    return res.status(405).json({ error: "Méthode non autorisée" });
  } catch (e: any) {
    if (e instanceof BadRequest) return res.status(400).json({ error: e.message });
    if (/duplicate key|unique/i.test(String(e?.message))) return res.status(409).json({ error: "Ce nom existe déjà" });
    console.error("gym api error:", e);
    return res.status(500).json({ error: "Erreur du serveur" });
  }
}

// Gym back office API (members, sports, coaches, monthly fees and coach commissions).
// Access = phone number on a list of at most MAX_PHONES people + the 6-digit code of an authenticator app (TOTP, RFC 6238).
// Nothing is sent anywhere: each person scans a QR code once (Google Authenticator etc.).
// After the code is accepted the server hands out a signed 12h session token; every other request must carry it.
import type { VercelRequest, VercelResponse } from "@vercel/node";
import { createCipheriv, createDecipheriv, createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from "crypto";
import { prisma } from "./_prisma";

const MAX_PHONES = 4; // owner included
const SESSION_HOURS = 12;
const MAX_FAILS = 5; // wrong codes before a short lock
const LOCK_MINUTES = 5;
const ISSUER = "Gym Mind Decoded";

/** Normalises a phone number to E.164. 8 digits are taken as Tunisian (+216). */
function normalizePhone(v: unknown): string | null {
  let p = String(v ?? "").replace(/[\s.\-()]/g, "");
  if (p.startsWith("00")) p = "+" + p.slice(2);
  if (/^\d{8}$/.test(p)) p = "+216" + p;
  return /^\+[1-9]\d{7,14}$/.test(p) ? p : null;
}

const ownerPhone = (): string | null => normalizePhone(process.env["GYM_OWNER_PHONE"]);

async function isAllowed(phone: string): Promise<boolean> {
  const rows: any[] = await prisma.$queryRawUnsafe(`SELECT "phone" FROM "GymPhone" WHERE "phone" = $1`, phone);
  return rows.length > 0;
}

// ---------- session token (stateless, HMAC-signed) ----------
function secret(): string {
  const s = process.env["GYM_SESSION_SECRET"] || "";
  if (s.length < 24) throw new Error("GYM_SESSION_SECRET is missing or too short");
  return s;
}
const sign = (payload: string) => createHmac("sha256", secret()).update(payload).digest("base64url");
function makeToken(phone: string): { token: string; expiresAt: number } {
  const expiresAt = Date.now() + SESSION_HOURS * 3600_000;
  const payload = Buffer.from(JSON.stringify({ p: phone, e: expiresAt })).toString("base64url");
  return { token: `${payload}.${sign(payload)}`, expiresAt };
}

// ---------- TOTP (RFC 6238: HMAC-SHA1, 6 digits, 30 s) ----------
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
function base32(buf: Buffer): string {
  let bits = 0, value = 0, out = "";
  for (const byte of buf) {
    value = (value << 8) | byte; bits += 8;
    while (bits >= 5) { out += B32[(value >>> (bits - 5)) & 31]; bits -= 5; }
  }
  if (bits > 0) out += B32[(value << (5 - bits)) & 31];
  return out;
}
function unbase32(str: string): Buffer {
  let bits = 0, value = 0; const out: number[] = [];
  for (const ch of str) {
    value = (value << 5) | B32.indexOf(ch); bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 255); bits -= 8; }
  }
  return Buffer.from(out);
}
function hotp(secret: string, counter: number): string {
  const msg = Buffer.alloc(8);
  msg.writeUInt32BE(Math.floor(counter / 2 ** 32), 0);
  msg.writeUInt32BE(counter >>> 0, 4);
  const h = createHmac("sha1", unbase32(secret)).update(msg).digest();
  const o = h[h.length - 1] & 15;
  const n = ((h[o] & 127) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3];
  return String(n % 1_000_000).padStart(6, "0");
}
/** Returns the matching 30 s step (so it can be used only once), or null. Accepts one step of clock drift. */
function checkTotp(secret: string, code: string, now = Date.now()): number | null {
  const step = Math.floor(now / 30_000);
  for (const s of [step, step - 1, step + 1]) {
    const expected = Buffer.from(hotp(secret, s));
    const given = Buffer.from(code);
    if (expected.length === given.length && timingSafeEqual(expected, given)) return s;
  }
  return null;
}

// secrets are encrypted at rest with a key derived from GYM_SESSION_SECRET
const dataKey = () => createHash("sha256").update("gym-totp:" + secret()).digest();
function seal(plain: string): string {
  const iv = randomBytes(12);
  const c = createCipheriv("aes-256-gcm", dataKey(), iv);
  const enc = Buffer.concat([c.update(plain, "utf8"), c.final()]);
  return [iv, c.getAuthTag(), enc].map((b) => b.toString("base64")).join(".");
}
function unseal(blob: string): string {
  const [iv, tag, enc] = blob.split(".").map((x) => Buffer.from(x, "base64"));
  const d = createDecipheriv("aes-256-gcm", dataKey(), iv);
  d.setAuthTag(tag);
  return Buffer.concat([d.update(enc), d.final()]).toString("utf8");
}

/** Creates (or replaces) the authenticator secret of a person and returns what to show ONCE for enrolment. */
async function enroll(phone: string): Promise<{ secret: string; uri: string }> {
  const sec = base32(randomBytes(20));
  await prisma.$executeRawUnsafe(`UPDATE "GymPhone" SET "secret"=$2, "lastStep"=0, "fails"=0, "lockedUntil"=NULL WHERE "phone"=$1`, phone, seal(sec));
  const uri = `otpauth://totp/${encodeURIComponent(ISSUER)}:${encodeURIComponent(phone)}?secret=${sec}&issuer=${encodeURIComponent(ISSUER)}&algorithm=SHA1&digits=6&period=30`;
  return { secret: sec, uri };
}

let tablesReady: Promise<void> | null = null;
function ensureTables(): Promise<void> {
  if (!tablesReady) {
    tablesReady = (async () => {
      const stmts = [
        `CREATE TABLE IF NOT EXISTS "GymPhone" ("phone" TEXT PRIMARY KEY, "name" TEXT, "addedBy" TEXT, "secret" TEXT, "lastStep" INTEGER NOT NULL DEFAULT 0, "fails" INTEGER NOT NULL DEFAULT 0, "lockedUntil" TIMESTAMP(3), "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
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

/** Returns the phone of the signed-in person (still on the list), or null. */
async function authenticate(req: VercelRequest): Promise<{ phone: string; owner: boolean } | null> {
  const header = String(req.headers["authorization"] || "");
  const token = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  const [payload, mac] = token.split(".");
  if (!payload || !mac) return null;
  const expected = Buffer.from(sign(payload));
  const given = Buffer.from(mac);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
  let data: any;
  try { data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")); } catch { return null; }
  if (!data?.p || typeof data.e !== "number" || data.e < Date.now()) return null;
  if (!(await isAllowed(data.p))) return null; // removed from the list = locked out immediately
  return { phone: data.p, owner: data.p === ownerPhone() };
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
  const [sports, coaches, members, payments, payouts, phones] = (await Promise.all([
    prisma.$queryRawUnsafe(`SELECT * FROM "GymSport" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoach" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymMember" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymPayment" WHERE "period" = $1`, month),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoachPayout" WHERE "period" = $1`, month),
    prisma.$queryRawUnsafe(`SELECT "phone","name" FROM "GymPhone" ORDER BY "createdAt"`),
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
    phones,
    ownerPhone: ownerPhone(),
    maxPhones: MAX_PHONES,
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
async function runAction(body: any, who: { phone: string; owner: boolean }): Promise<{ enrollment: { secret: string; uri: string } } | void> {
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
    case "phone_add": {
      if (!who.owner) throw new BadRequest("Seul le propriétaire peut gérer les accès");
      const phone = normalizePhone(body.phone);
      if (!phone) throw new BadRequest("Numéro invalide (exemple : +21620123456)");
      // the cap is checked inside the INSERT so two concurrent requests cannot exceed it
      const added = await prisma.$executeRawUnsafe(
        `INSERT INTO "GymPhone" ("phone","name","addedBy") SELECT $1,$2,$3 WHERE (SELECT COUNT(*) FROM "GymPhone") < $4 ON CONFLICT DO NOTHING`,
        phone, str(body.name, 80), who.phone, MAX_PHONES);
      if (!added) {
        const exists: any[] = await prisma.$queryRawUnsafe(`SELECT 1 FROM "GymPhone" WHERE "phone"=$1`, phone);
        throw new BadRequest(exists.length ? "Ce numéro est déjà dans la liste" : `Maximum ${MAX_PHONES} personnes (propriétaire inclus)`);
      }
      return { enrollment: await enroll(phone) };
    }
    case "phone_reset": { // lost phone: new QR code, the old one stops working
      if (!who.owner) throw new BadRequest("Seul le propriétaire peut gérer les accès");
      const phone = normalizePhone(body.phone);
      const exists: any[] = phone ? await prisma.$queryRawUnsafe(`SELECT 1 FROM "GymPhone" WHERE "phone"=$1`, phone) : [];
      if (!phone || !exists.length) throw new BadRequest("Numéro inconnu");
      return { enrollment: await enroll(phone) };
    }
    case "phone_remove": {
      if (!who.owner) throw new BadRequest("Seul le propriétaire peut gérer les accès");
      const phone = normalizePhone(body.phone);
      if (phone === ownerPhone()) throw new BadRequest("Le propriétaire ne peut pas être retiré");
      if (phone) await prisma.$executeRawUnsafe(`DELETE FROM "GymPhone" WHERE "phone"=$1`, phone);
      return;
    }
    default:
      throw new BadRequest("Action inconnue");
  }
}

const sameText = (a: string, b: string) => {
  const x = Buffer.from(a), y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
};

/** One-time first setup of the owner: needs GYM_SETUP_KEY and only works while the owner has no authenticator yet. */
async function ownerSetup(body: any, res: VercelResponse) {
  const key = process.env["GYM_SETUP_KEY"] || "";
  const owner = ownerPhone();
  if (key.length < 16 || !owner || !sameText(String(body.setupKey || ""), key)) return res.status(403).json({ error: "Clé de configuration invalide" });
  const rows: any[] = await prisma.$queryRawUnsafe(`SELECT "secret" FROM "GymPhone" WHERE "phone"=$1`, owner);
  if (rows.length && rows[0].secret) return res.status(409).json({ error: "Déjà configuré" });
  await prisma.$executeRawUnsafe(`INSERT INTO "GymPhone" ("phone","name","addedBy") VALUES ($1,'Propriétaire',$1) ON CONFLICT DO NOTHING`, owner);
  return res.status(200).json({ ok: true, enrollment: await enroll(owner) });
}

/** Login = phone number + current authenticator code. Every failure looks the same. */
async function login(body: any, res: VercelResponse) {
  const bad = () => res.status(400).json({ error: "Numéro ou code invalide" });
  const phone = normalizePhone(body.phone);
  const code = String(body.code || "").replace(/\s/g, "");
  if (!phone || !/^\d{6}$/.test(code)) return bad();
  const rows: any[] = await prisma.$queryRawUnsafe(`SELECT * FROM "GymPhone" WHERE "phone"=$1`, phone);
  const row = rows[0];
  if (!row || !row.secret) return bad();
  if (row.lockedUntil && new Date(row.lockedUntil).getTime() > Date.now()) {
    return res.status(429).json({ error: `Trop d'essais, réessayez dans quelques minutes` });
  }
  const step = checkTotp(unseal(row.secret), code);
  if (step === null || step <= row.lastStep) { // wrong code, or the same code used twice
    await prisma.$executeRawUnsafe(
      `UPDATE "GymPhone" SET "fails" = "fails" + 1,
         "lockedUntil" = CASE WHEN "fails" + 1 >= $2 THEN NOW() + ($3 || ' minutes')::interval ELSE "lockedUntil" END,
         "fails" = CASE WHEN "fails" + 1 >= $2 THEN 0 ELSE "fails" + 1 END
       WHERE "phone"=$1`, phone, MAX_FAILS, String(LOCK_MINUTES));
    return bad();
  }
  await prisma.$executeRawUnsafe(`UPDATE "GymPhone" SET "lastStep"=$2, "fails"=0, "lockedUntil"=NULL WHERE "phone"=$1`, phone, step);
  return res.status(200).json({ ok: true, ...makeToken(phone) });
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  res.setHeader("Cache-Control", "no-store");
  try {
    await ensureTables();
    if (req.method === "POST" && req.body?.action === "login") return await login(req.body, res);
    if (req.method === "POST" && req.body?.action === "owner_setup") return await ownerSetup(req.body, res);
    const who = await authenticate(req);
    if (!who) return res.status(403).json({ error: "Accès refusé." });

    if (req.method === "GET") {
      const month = period(String(req.query["month"] || currentPeriod()));
      return res.status(200).json({ me: who.phone, canManage: who.owner, ...(await buildState(month)) });
    }
    if (req.method === "POST") {
      const result = await runAction(req.body || {}, who);
      return res.status(200).json({ ok: true, ...(result || {}) });
    }
    return res.status(405).json({ error: "Méthode non autorisée" });
  } catch (e: any) {
    if (e instanceof BadRequest) return res.status(400).json({ error: e.message });
    if (/duplicate key|unique/i.test(String(e?.message))) return res.status(409).json({ error: "Ce nom existe déjà" });
    console.error("gym api error:", e);
    return res.status(500).json({ error: "Erreur du serveur" });
  }
}

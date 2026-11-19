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

class ConfigError extends Error {}

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
  if (s.length < 24) throw new ConfigError("Configuration manquante : GYM_SESSION_SECRET (32 caractères minimum) n'est pas définie sur le serveur");
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
        `CREATE TABLE IF NOT EXISTS "GymExpense" ("id" TEXT PRIMARY KEY, "period" TEXT NOT NULL, "endPeriod" TEXT, "recurring" BOOLEAN NOT NULL DEFAULT FALSE, "category" TEXT NOT NULL, "label" TEXT, "amount" DOUBLE PRECISION NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
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

// ---------- monthly / yearly calculation ----------
type Dataset = { sports: any[]; coaches: any[]; members: any[]; payments: Map<string, Map<string, any>>; payouts: Map<string, Map<string, any>>; expenses: any[] };

const expenseApplies = (e: any, month: string) =>
  e.recurring ? e.period <= month && (!e.endPeriod || e.endPeriod >= month) : e.period === month;

function monthCalc(month: string, d: Dataset, detail: boolean) {
  const paidByMember = d.payments.get(month) ?? new Map<string, any>();
  const payoutByCoach = d.payouts.get(month) ?? new Map<string, any>();
  // A member is billed for a month if still active and already joined by the end of that month.
  const memberRows = d.members.map((m) => {
    const billed = !!m.active && String(m.joinedAt).slice(0, 7) <= month;
    const pay = paidByMember.get(m.id);
    const due = billed ? m.monthlyFee : 0;
    const paid = pay ? pay.amount : 0;
    const status = !billed && !pay ? "n/a" : paid >= due && paid > 0 ? "paid" : paid > 0 ? "partial" : "unpaid";
    return { ...m, billed, due, paid, status, paymentMethod: pay?.method ?? null, paymentNote: pay?.note ?? null };
  });

  const coachRows = d.coaches.map((c) => {
    const mine = memberRows.filter((m) => m.coachId === c.id && (m.billed || m.paid > 0));
    const due = round2(mine.reduce((a, m) => a + m.due, 0));
    const collected = round2(mine.reduce((a, m) => a + m.paid, 0));
    const commission = round2((collected * c.commissionPct) / 100); // earned on money actually collected
    const payout = payoutByCoach.get(c.id);
    const paidOut = payout ? payout.amount : 0;
    return {
      id: c.id, name: c.name, commissionPct: c.commissionPct, members: mine.length,
      due, collected, commission, potential: round2((due * c.commissionPct) / 100),
      paidOut, balance: round2(commission - paidOut), payoutNote: payout?.note ?? null,
    };
  });

  const expenseRows = d.expenses.filter((e) => expenseApplies(e, month));
  const expenses = round2(expenseRows.reduce((a, e) => a + e.amount, 0));
  const due = round2(memberRows.reduce((a, m) => a + m.due, 0));
  const collected = round2(memberRows.reduce((a, m) => a + m.paid, 0));
  const commissions = round2(coachRows.reduce((a, c) => a + c.commission, 0));
  const paidOut = round2(coachRows.reduce((a, c) => a + c.paidOut, 0));
  const summary = {
    month,
    activeMembers: memberRows.filter((m) => m.billed).length,
    due, collected, outstanding: round2(Math.max(0, due - collected)),
    commissions, paidOut, commissionsToPay: round2(commissions - paidOut),
    expenses, net: round2(collected - commissions - expenses), // net = collected - coach commissions - other expenses
  };
  if (!detail) return { summary, expenseRows };

  const byCategory: Record<string, number> = {};
  for (const e of expenseRows) byCategory[e.category] = round2((byCategory[e.category] || 0) + e.amount);
  const bySport = d.sports.map((sp) => {
    const mine = memberRows.filter((m) => m.sportId === sp.id && (m.billed || m.paid > 0));
    return { id: sp.id, name: sp.name, members: mine.length, due: round2(mine.reduce((a, m) => a + m.due, 0)), collected: round2(mine.reduce((a, m) => a + m.paid, 0)) };
  });
  return { summary, members: memberRows, coaches: coachRows, sports: bySport, expenseRows, expensesByCategory: byCategory };
}

async function loadDataset(year: string): Promise<Dataset> {
  const [sports, coaches, members, payments, payouts, expenses] = (await Promise.all([
    prisma.$queryRawUnsafe(`SELECT * FROM "GymSport" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoach" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymMember" ORDER BY "name"`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymPayment" WHERE "period" LIKE $1`, `${year}-%`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymCoachPayout" WHERE "period" LIKE $1`, `${year}-%`),
    prisma.$queryRawUnsafe(`SELECT * FROM "GymExpense" ORDER BY "period", "category"`),
  ])) as any[][];
  const group = (rows: any[], key: string) => {
    const m = new Map<string, Map<string, any>>();
    for (const r of rows) { if (!m.has(r.period)) m.set(r.period, new Map()); m.get(r.period)!.set(r[key], r); }
    return m;
  };
  return { sports, coaches, members, payments: group(payments, "memberId"), payouts: group(payouts, "coachId"), expenses };
}

async function buildState(month: string) {
  const year = month.slice(0, 4);
  const d = await loadDataset(year);
  const cur = monthCalc(month, d, true) as any;
  const months = Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`);
  const series = months.map((m) => monthCalc(m, d, false));
  const sum = (k: string) => round2(series.reduce((a, x: any) => a + x.summary[k], 0));
  const yearCategories: Record<string, number> = {};
  for (const x of series) for (const e of x.expenseRows) yearCategories[e.category] = round2((yearCategories[e.category] || 0) + e.amount);
  return {
    month, year,
    sports: d.sports, coaches: d.coaches, members: cur.members,
    expenses: d.expenses,
    payments: [...d.payments.values()].flatMap((m) => [...m.values()]).map((x) => ({ memberId: x.memberId, period: x.period, amount: x.amount, method: x.method, note: x.note })),
    report: {
      ...cur.summary, coaches: cur.coaches, sports: cur.sports,
      expenseRows: cur.expenseRows, expensesByCategory: cur.expensesByCategory,
    },
    yearReport: {
      months: series.map((x) => x.summary),
      totals: { due: sum("due"), collected: sum("collected"), commissions: sum("commissions"), expenses: sum("expenses"), net: sum("net") },
      expensesByCategory: yearCategories,
    },
  };
}

// ---------- Excel import (rows already parsed in the browser) ----------
const MAX_IMPORT_ROWS = 2000;
const key = (v: unknown) => String(v ?? "").trim().toLowerCase();

/** Applies sheets Sports / Coachs / Membres / Paiements / Charges. All-or-nothing; sports and coaches are matched by name. */
async function importData(data: any): Promise<Record<string, number>> {
  const list = (x: unknown): any[] => (Array.isArray(x) ? x : []);
  const d = { sports: list(data?.sports), coaches: list(data?.coaches), members: list(data?.members), payments: list(data?.payments), expenses: list(data?.expenses) };
  const total = Object.values(d).reduce((a, x) => a + x.length, 0);
  if (!total) throw new BadRequest("Le fichier ne contient aucune ligne à importer");
  if (total > MAX_IMPORT_ROWS) throw new BadRequest(`Trop de lignes (maximum ${MAX_IMPORT_ROWS})`);

  const [dbSports, dbCoaches, dbMembers] = (await Promise.all([
    prisma.$queryRawUnsafe(`SELECT "id","name" FROM "GymSport"`),
    prisma.$queryRawUnsafe(`SELECT "id","name" FROM "GymCoach"`),
    prisma.$queryRawUnsafe(`SELECT "id","name" FROM "GymMember"`),
  ])) as any[][];
  const sportId = new Map<string, string>(dbSports.map((r) => [key(r.name), r.id]));
  const coachId = new Map<string, string>(dbCoaches.map((r) => [key(r.name), r.id]));
  const memberId = new Map<string, string>(dbMembers.map((r) => [key(r.name), r.id]));
  const ops: any[] = [];
  const run = (sql: string, ...a: any[]) => ops.push(prisma.$executeRawUnsafe(sql, ...a));
  const where = (sheet: string, i: number) => `${sheet}, ligne ${i + 2}`;
  const wrap = <T,>(sheet: string, i: number, fn: () => T): T => {
    try { return fn(); } catch (e: any) { throw new BadRequest(`${where(sheet, i)} : ${e instanceof BadRequest ? e.message : "valeur invalide"}`); }
  };
  const ensureSport = (name: string) => {
    if (!sportId.has(key(name))) { const id = randomUUID(); sportId.set(key(name), id); run(`INSERT INTO "GymSport" ("id","name","monthlyFee") VALUES ($1,$2,0)`, id, name); }
    return sportId.get(key(name))!;
  };
  const ensureCoach = (name: string) => {
    if (!coachId.has(key(name))) { const id = randomUUID(); coachId.set(key(name), id); run(`INSERT INTO "GymCoach" ("id","name","commissionPct") VALUES ($1,$2,0)`, id, name); }
    return coachId.get(key(name))!;
  };
  const count: Record<string, number> = { sports: 0, coaches: 0, members: 0, payments: 0, expenses: 0 };

  d.sports.forEach((r, i) => wrap("Sports", i, () => {
    const name = str(r.name, 80, true)!, fee = num(r.monthlyFee ?? 0, 0, 100000);
    const id = sportId.get(key(name));
    if (id) run(`UPDATE "GymSport" SET "monthlyFee"=$2 WHERE "id"=$1`, id, fee);
    else { const nid = randomUUID(); sportId.set(key(name), nid); run(`INSERT INTO "GymSport" ("id","name","monthlyFee") VALUES ($1,$2,$3)`, nid, name, fee); }
    count["sports"]++;
  }));
  d.coaches.forEach((r, i) => wrap("Coachs", i, () => {
    const name = str(r.name, 120, true)!, pct = num(r.commissionPct ?? 0, 0, 100);
    const id = coachId.get(key(name));
    if (id) run(`UPDATE "GymCoach" SET "email"=$2,"phone"=$3,"commissionPct"=$4 WHERE "id"=$1`, id, str(r.email, 200), str(r.phone, 40), pct);
    else { const nid = randomUUID(); coachId.set(key(name), nid); run(`INSERT INTO "GymCoach" ("id","name","email","phone","commissionPct") VALUES ($1,$2,$3,$4,$5)`, nid, name, str(r.email, 200), str(r.phone, 40), pct); }
    count["coaches"]++;
  }));
  d.members.forEach((r, i) => wrap("Membres", i, () => {
    const name = str(r.name, 120, true)!;
    const sport = str(r.sport, 80), coach = str(r.coach, 120);
    const args = [
      str(r.email, 200), str(r.phone, 40), sport ? ensureSport(sport) : null, coach ? ensureCoach(coach) : null,
      num(r.monthlyFee ?? 0, 0, 100000), day(r.joinedAt), r.active !== false, str(r.notes, 500),
    ] as const;
    const id = memberId.get(key(name));
    if (id) run(`UPDATE "GymMember" SET "email"=$2,"phone"=$3,"sportId"=$4,"coachId"=$5,"monthlyFee"=$6,"joinedAt"=$7,"active"=$8,"notes"=$9 WHERE "id"=$1`, id, ...args);
    else { const nid = randomUUID(); memberId.set(key(name), nid); run(`INSERT INTO "GymMember" ("id","name","email","phone","sportId","coachId","monthlyFee","joinedAt","active","notes") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`, nid, name, ...args); }
    count["members"]++;
  }));
  d.payments.forEach((r, i) => wrap("Paiements", i, () => {
    const id = memberId.get(key(r.member));
    if (!id) throw new BadRequest(`membre inconnu « ${String(r.member ?? "")} » (ajoutez-le dans la feuille Membres)`);
    run(`INSERT INTO "GymPayment" ("memberId","period","amount","method","note") VALUES ($1,$2,$3,$4,$5)
         ON CONFLICT ("memberId","period") DO UPDATE SET "amount"=$3,"method"=$4,"note"=$5`,
        id, period(r.month), num(r.amount, 0, 100000), str(r.method, 40), str(r.note, 200));
    count["payments"]++;
  }));
  d.expenses.forEach((r, i) => wrap("Charges", i, () => {
    const recurring = /^(oui|yes|true|1|vrai|mensuel)$/i.test(String(r.recurring ?? ""));
    const start = period(r.month);
    const end = recurring && r.endMonth ? period(r.endMonth) : null;
    run(`INSERT INTO "GymExpense" ("id","period","endPeriod","recurring","category","label","amount") VALUES ($1,$2,$3,$4,$5,$6,$7)`,
        randomUUID(), start, end, recurring, str(r.category, 40, true), str(r.label, 120), num(r.amount, 0, 10_000_000));
    count["expenses"]++;
  }));

  await prisma.$transaction(ops);
  return count;
}

// ---------- actions ----------
async function runAction(body: any, who: { user: string }): Promise<{ imported: Record<string, number> } | void> {
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
    case "expense_save": {
      const recurring = body.recurring === true;
      const start = period(body.period);
      const end = recurring && body.endPeriod ? period(body.endPeriod) : null;
      if (end && end < start) throw new BadRequest("La fin doit être après le début");
      const args = [start, end, recurring, str(body.category, 40, true), str(body.label, 120), num(body.amount, 0, 10_000_000)] as const;
      if (id) await prisma.$executeRawUnsafe(`UPDATE "GymExpense" SET "period"=$2,"endPeriod"=$3,"recurring"=$4,"category"=$5,"label"=$6,"amount"=$7 WHERE "id"=$1`, id, ...args);
      else await prisma.$executeRawUnsafe(`INSERT INTO "GymExpense" ("id","period","endPeriod","recurring","category","label","amount") VALUES ($1,$2,$3,$4,$5,$6,$7)`, randomUUID(), ...args);
      return;
    }
    case "expense_delete":
      await prisma.$executeRawUnsafe(`DELETE FROM "GymExpense" WHERE "id"=$1`, str(body.id, 64, true));
      return;
    case "import_data":
      return { imported: await importData(body.data) };
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
    try {
      await ensureTables();
    } catch (e) {
      console.error("gym ensureTables failed:", e);
      return res.status(500).json({ error: "Base de données indisponible (voir les logs Vercel)" });
    }
    if (req.method === "POST" && req.body?.action === "login") return await login(req.body, res);
    const who = await authenticate(req);
    if (!who) return res.status(403).json({ error: "Accès refusé." });

    if (req.method === "GET") {
      const month = period(String(req.query["month"] || currentPeriod()));
      return res.status(200).json({ me: who.user, ...(await buildState(month)) });
    }
    if (req.method === "POST") {
      const result = await runAction(req.body || {}, who);
      return res.status(200).json({ ok: true, ...(result || {}) });
    }
    return res.status(405).json({ error: "Méthode non autorisée" });
  } catch (e: any) {
    if (e instanceof ConfigError) { console.error("gym config error:", e.message); return res.status(500).json({ error: e.message }); }
    if (e instanceof BadRequest) return res.status(400).json({ error: e.message });
    if (/duplicate key|unique/i.test(String(e?.message))) return res.status(409).json({ error: "Ce nom existe déjà" });
    console.error("gym api error:", e);
    return res.status(500).json({ error: "Erreur du serveur" });
  }
}

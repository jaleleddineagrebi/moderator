#!/usr/bin/env node
// Creates the gym back-office accounts (max 4).
//   node scripts/gym-accounts.mjs                -> admin1..admin4
//   node scripts/gym-accounts.mjs jalel sami ... -> your own user names (1 to 4)
//
// Random passwords are generated and written ONLY to ../../tokens/gym-accounts.txt (git-ignored).
// The same file holds the line to paste into Vercel as the environment variable GYM_ACCOUNTS
// (it contains salted password hashes, never the passwords). Re-run the script to reset every password.
import { randomBytes, scryptSync } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX = 4;
const names = process.argv.slice(2);
const users = names.length ? names : ["admin1", "admin2", "admin3", "admin4"];
if (users.length > MAX) throw new Error(`At most ${MAX} accounts`);
for (const u of users) if (!/^[a-z0-9._-]{3,30}$/.test(u)) throw new Error(`Bad user name "${u}" (3-30 chars: a-z 0-9 . _ -)`);
if (new Set(users).size !== users.length) throw new Error("User names must be different");

const ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no look-alike characters
function password(len = 16) {
  let out = "";
  while (out.length < len) for (const b of randomBytes(32)) if (b < 256 - (256 % ALPHABET.length) && out.length < len) out += ALPHABET[b % ALPHABET.length];
  return out;
}

const rows = users.map((u) => {
  const pw = password();
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(pw, salt, 32, { N: 16384 }).toString("hex");
  return { u, pw, entry: `${u}:${salt}:${hash}` };
});

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tokens", "gym-accounts.txt");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(
  out,
  [
    "GYM BACK OFFICE ACCOUNTS (private, never commit or share this file in chat)",
    "",
    ...rows.map((r) => `user: ${r.u}    password: ${r.pw}`),
    "",
    "Vercel environment variable to set (Project -> Settings -> Environment Variables):",
    "GYM_ACCOUNTS=" + rows.map((r) => r.entry).join(";"),
    "",
  ].join("\n"),
  { mode: 0o600 },
);
console.log(`Created ${rows.length} accounts: ${users.join(", ")}`);
console.log(`Passwords and the GYM_ACCOUNTS value are in: ${out}`);

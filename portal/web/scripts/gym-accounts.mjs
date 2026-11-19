#!/usr/bin/env node
// Creates the gym back-office accounts (max 4).
//   node scripts/gym-accounts.mjs --choose jalel sami   -> YOU type each password (hidden, asked twice)
//   node scripts/gym-accounts.mjs jalel sami            -> random passwords, saved in tokens/gym-accounts.txt
//   node scripts/gym-accounts.mjs                       -> random passwords for admin1..admin4
//
// Output goes ONLY to ../../tokens/gym-accounts.txt (git-ignored). It contains the line to paste into Vercel as the
// environment variable GYM_ACCOUNTS (salted password hashes, never the passwords). With --choose the passwords are
// not saved anywhere. Re-run the script to reset every password.
import { randomBytes, scryptSync } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline";

const MAX = 4;
const MIN_LEN = 10;
const args = process.argv.slice(2);
const choose = args.includes("--choose");
const names = args.filter((a) => a !== "--choose");
const users = names.length ? names : ["admin1", "admin2", "admin3", "admin4"];
if (users.length > MAX) throw new Error(`At most ${MAX} accounts`);
for (const u of users) if (!/^[a-z0-9._-]{3,30}$/.test(u)) throw new Error(`Bad user name "${u}" (3-30 chars: a-z 0-9 . _ -)`);
if (new Set(users).size !== users.length) throw new Error("User names must be different");

const ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no look-alike characters
function randomPassword(len = 16) {
  let out = "";
  while (out.length < len) for (const b of randomBytes(32)) if (b < 256 - (256 % ALPHABET.length) && out.length < len) out += ALPHABET[b % ALPHABET.length];
  return out;
}

/** Reads one line without echoing it to the terminal. */
function askHidden(question) {
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl._writeToOutput = (s) => { if (s.includes(question)) process.stdout.write(s); };
    rl.question(question, (answer) => { rl.close(); process.stdout.write("\n"); resolve(answer); });
  });
}

async function chosenPassword(user) {
  for (;;) {
    const a = await askHidden(`Password for ${user} (min ${MIN_LEN} characters): `);
    if (a.length < MIN_LEN) { console.log(`Too short, use at least ${MIN_LEN} characters.`); continue; }
    if (a.toLowerCase().includes(user)) { console.log("The password must not contain the user name."); continue; }
    const b = await askHidden("Type it again: ");
    if (a !== b) { console.log("They do not match, try again."); continue; }
    return a;
  }
}

if (choose && !process.stdin.isTTY) throw new Error("--choose needs an interactive terminal (run it yourself in the VS Code terminal)");

const rows = [];
for (const u of users) {
  const pw = choose ? await chosenPassword(u) : randomPassword();
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(pw, salt, 32, { N: 16384 }).toString("hex");
  rows.push({ u, pw: choose ? null : pw, entry: `${u}:${salt}:${hash}` });
}

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tokens", "gym-accounts.txt");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(
  out,
  [
    "GYM BACK OFFICE ACCOUNTS (private, never commit or share this file in chat)",
    "",
    ...rows.map((r) => (r.pw ? `user: ${r.u}    password: ${r.pw}` : `user: ${r.u}    password: (the one you chose)`)),
    "",
    "Vercel environment variable to set (Project -> Settings -> Environment Variables):",
    "GYM_ACCOUNTS=" + rows.map((r) => r.entry).join(";"),
    "",
  ].join("\n"),
  { mode: 0o600 },
);
console.log(`Created ${rows.length} accounts: ${users.join(", ")}`);
console.log(`The GYM_ACCOUNTS value to paste into Vercel is in: ${out}`);

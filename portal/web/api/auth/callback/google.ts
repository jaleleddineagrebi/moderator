import type { VercelRequest, VercelResponse } from "@vercel/node";
import authHandler from "../index.js";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Delegate to main auth handler
  return authHandler(req, res);
}

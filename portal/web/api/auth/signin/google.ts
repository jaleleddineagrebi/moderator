import type { VercelRequest, VercelResponse } from "@vercel/node";
import authHandler from "../index.js";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  req.query.action = "signin";
  req.query.provider = "google";
  return authHandler(req, res);
}

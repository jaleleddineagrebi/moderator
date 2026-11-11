import type { VercelRequest, VercelResponse } from "@vercel/node";
import authHandler from "../auth";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  return authHandler(req, res);
}

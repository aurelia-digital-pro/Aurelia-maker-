import { Router, type IRouter } from "express";
import { HealthCheckResponse } from "@workspace/api-zod";

const router: IRouter = Router();
const canonicalApiUrl = (
  process.env.AURELIA_CANONICAL_API_URL ?? "http://127.0.0.1:8765"
).replace(/\/+$/, "");

router.get("/healthz", async (_req, res) => {
  try {
    const upstream = await fetch(`${canonicalApiUrl}/api/health`, {
      signal: AbortSignal.timeout(2_000),
    });
    if (!upstream.ok) {
      res.status(503).json({
        status: "canonical_unhealthy",
        canonical_api: canonicalApiUrl,
        upstream_status: upstream.status,
      });
      return;
    }
  } catch (error) {
    res.status(503).json({
      status: "canonical_unavailable",
      canonical_api: canonicalApiUrl,
      error: error instanceof Error ? error.message : String(error),
    });
    return;
  }

  const data = HealthCheckResponse.parse({ status: "ok" });
  res.json(data);
});

export default router;

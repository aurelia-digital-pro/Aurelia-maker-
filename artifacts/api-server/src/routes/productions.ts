import { Readable } from "node:stream";
import { Router, type IRouter, type Request, type Response as ExpressResponse } from "express";
import {
  CreateProductionBody,
  GetProductionParams,
  GetProductionVideoParams,
} from "@workspace/api-zod";

/**
 * Compatibility surface for clients that still call /api/productions.
 *
 * Production state and execution belong exclusively to the canonical Python
 * API (`aurelia.server`). This router deliberately has no process, job map,
 * FactoryRunner, engine root, or independent status machine.
 */
const canonicalApiUrl = (
  process.env.AURELIA_CANONICAL_API_URL ?? "http://127.0.0.1:8765"
).replace(/\/+$/, "");

function canonicalUrl(path: string): string {
  return `${canonicalApiUrl}${path}`;
}

async function requestCanonical(
  path: string,
  init?: RequestInit,
): Promise<{ response: globalThis.Response; body: unknown }> {
  let response: globalThis.Response;
  try {
    response = await fetch(canonicalUrl(path), {
      ...init,
      headers: {
        accept: "application/json",
        ...(init?.body ? { "content-type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(
      `Canonical AURELIA API unavailable at ${canonicalApiUrl}: ${reason}`,
    );
  }

  const text = await response.text();
  let body: unknown = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: text };
    }
  }
  return { response, body };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? value as Record<string, unknown>
    : {};
}

function compatibilityStatus(value: unknown):
  "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "STOPPED" | "BLOCKED" | "VALIDATED" {
  switch (value) {
    case "QUEUED":
    case "RUNNING":
    case "COMPLETED":
    case "FAILED":
    case "STOPPED":
    case "BLOCKED":
    case "VALIDATED":
      return value;
    default:
      return "RUNNING";
  }
}

function toCompatibilityJob(value: unknown): Record<string, unknown> {
  const source = asRecord(value);
  const status = compatibilityStatus(source.status);
  const metadata = asRecord(source.metadata);
  const finalMp4 = status === "COMPLETED" && typeof source.final_mp4 === "string"
    ? source.final_mp4
    : null;
  return {
    jobId: String(source.job_id ?? ""),
    episodeId: String(source.episode_id ?? ""),
    status,
    stage: String(source.stage ?? ""),
    progress: Number(source.progress ?? 0),
    title: typeof source.title === "string" ? source.title : undefined,
    language: typeof source.language === "string" ? source.language : undefined,
    profile: String(source.profile ?? metadata.profile ?? "both"),
    request: String(source.request ?? metadata.original_message ?? ""),
    source: "chat",
    createdAt: String(source.created_at ?? ""),
    finalMp4,
    downloadUrl: finalMp4 ? `/api/productions/${String(source.job_id)}/video` : null,
    error: typeof source.error === "string" ? source.error : null,
    logs: Array.isArray(source.logs) ? source.logs : [],
    metadata,
  };
}

function sendJson(res: ExpressResponse, status: number, body: unknown): void {
  res.status(status).json(body);
}

async function handleCanonicalError(res: ExpressResponse, error: unknown): Promise<void> {
  const message = error instanceof Error ? error.message : String(error);
  sendJson(res, 503, {
    error: message,
    canonical_api: canonicalApiUrl,
  });
}

const router: IRouter = Router();

router.get("/productions", async (_req: Request, res: ExpressResponse) => {
  try {
    const { response, body } = await requestCanonical("/api/jobs");
    const payload = asRecord(body);
    const jobs = Array.isArray(payload.jobs)
      ? payload.jobs.map(toCompatibilityJob)
      : [];
    sendJson(res, response.status, jobs);
  } catch (error) {
    await handleCanonicalError(res, error);
  }
});

router.post("/productions", async (req: Request, res: ExpressResponse) => {
  const parsed = CreateProductionBody.safeParse(req.body);
  if (!parsed.success) {
    sendJson(res, 400, {
      error: "Request must include non-empty production text.",
    });
    return;
  }

  const request = parsed.data.request.trim();
  const profile = parsed.data.profile ?? "both";
  const episodeHeader = parsed.data.episodeId
    ? `Create Episode ${parsed.data.episodeId}`
    : "Create Episode";
  const message = `${episodeHeader}\nProfile: ${profile}\n${request}`;

  try {
    const { response, body } = await requestCanonical("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, language: "auto", profile }),
    });
    const source = asRecord(body);
    if (!response.ok) {
      sendJson(res, response.status, body);
      return;
    }
    sendJson(res, response.status, {
      jobId: String(source.job_id ?? ""),
      episodeId: String(source.episode_id ?? parsed.data.episodeId ?? ""),
      status: "QUEUED",
      stage: "QUEUED",
      progress: 0,
      profile,
      request,
      source: "chat",
      finalMp4: null,
      downloadUrl: null,
      error: null,
      metadata: {
        source: "chat",
        canonical_api: canonicalApiUrl,
        chat_reply: source.reply ?? "",
      },
    });
  } catch (error) {
    await handleCanonicalError(res, error);
  }
});

router.get("/productions/:jobId", async (req: Request, res: ExpressResponse) => {
  const parsed = GetProductionParams.safeParse(req.params);
  if (!parsed.success) {
    sendJson(res, 400, { error: "Invalid production job id." });
    return;
  }
  try {
    const { response, body } = await requestCanonical(
      `/api/jobs/${encodeURIComponent(parsed.data.jobId)}`,
    );
    if (!response.ok) {
      sendJson(res, response.status, body);
      return;
    }
    sendJson(res, response.status, toCompatibilityJob(body));
  } catch (error) {
    await handleCanonicalError(res, error);
  }
});

router.get("/productions/:jobId/video", async (req: Request, res: ExpressResponse) => {
  const parsed = GetProductionVideoParams.safeParse(req.params);
  if (!parsed.success) {
    sendJson(res, 400, { error: "Invalid production job id." });
    return;
  }

  let upstream: globalThis.Response;
  try {
    upstream = await fetch(canonicalUrl(
      `/api/jobs/${encodeURIComponent(parsed.data.jobId)}/video`,
    ));
  } catch (error) {
    await handleCanonicalError(res, error);
    return;
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    sendJson(res, upstream.status || 503, {
      error: text || "A validated final MP4 is not available yet.",
    });
    return;
  }

  res.status(upstream.status);
  const contentType = upstream.headers.get("content-type");
  const contentLength = upstream.headers.get("content-length");
  const contentDisposition = upstream.headers.get("content-disposition");
  if (contentType) res.setHeader("content-type", contentType);
  if (contentLength) res.setHeader("content-length", contentLength);
  if (contentDisposition) res.setHeader("content-disposition", contentDisposition);
  Readable.fromWeb(upstream.body as any).pipe(res);
});

export default router;

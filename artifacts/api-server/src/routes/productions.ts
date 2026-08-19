import { Router, type IRouter } from "express";
import { spawn, type ChildProcess } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import {
  CreateProductionBody,
  GetProductionParams,
  GetProductionVideoParams,
} from "@workspace/api-zod";
import { logger } from "../lib/logger";

type Status = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "BLOCKED" | "VALIDATED";
type Production = {
  jobId: string;
  episodeId: string;
  status: Status;
  stage: string;
  progress: number;
  title?: string;
  language?: string;
  profile: string;
  request: string;
  source: "chat";
  createdAt: string;
  finalMp4: string | null;
  downloadUrl: string | null;
  error: string | null;
  logs: string[];
  metadata: Record<string, unknown>;
};

const jobs = new Map<string, Production>();
const processes = new Map<string, ChildProcess>();
const engineRootCandidates = [
  resolve(process.cwd(), "aurelia-engine"),
  resolve(process.cwd(), "../../aurelia-engine"),
  resolve(import.meta.dirname, "../../../aurelia-engine"),
];
const engineRoot = engineRootCandidates.find((candidate) => existsSync(candidate)) ?? engineRootCandidates[0];

function publicJob(job: Production): Production {
  return { ...job, metadata: { ...job.metadata } };
}

function parseEngineLine(job: Production, line: string): void {
  job.logs = [...job.logs.slice(-149), line];
  const stage = line.match(/\[FACTORY\]\s+([A-Z_]+)\s+stage/i)?.[1];
  if (stage) {
    job.stage = stage;
  } else if (line.includes("FINAL MP4")) {
    job.stage = "DELIVERY";
    job.progress = 100;
  }
  const jsonStart = line.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const event = JSON.parse(line.slice(jsonStart)) as { status?: Status; job?: Record<string, unknown>; error?: string };
      if (event.status) job.status = event.status;
      if (event.error) job.error = event.error;
      if (event.job) {
        const data = event.job;
        job.finalMp4 = typeof data.final_mp4 === "string" ? data.final_mp4 : job.finalMp4;
        job.metadata = typeof data.metadata === "object" && data.metadata ? data.metadata as Record<string, unknown> : job.metadata;
        const result = job.metadata.result;
        if (result && typeof result === "object" && "final_mp4" in result) {
          job.finalMp4 = String((result as { final_mp4: string }).final_mp4);
        }
      }
    } catch {
      // Regular factory output is intentionally kept as a log line.
    }
  }
}

function startProcess(job: Production): void {
  const episodeId = job.episodeId;
  const pythonCandidates = [
    resolve(engineRoot, "../.pythonlibs/bin/python"),
    resolve(process.cwd(), ".pythonlibs/bin/python"),
    resolve(process.cwd(), "../../.pythonlibs/bin/python"),
    resolve(import.meta.dirname, "../../../.pythonlibs/bin/python"),
  ];
  const python = pythonCandidates.find((candidate) => existsSync(candidate));
  if (!python) {
    job.status = "FAILED";
    job.error = "Python runtime is not available for the local production engine.";
    job.logs.push("[engine] " + job.error);
    return;
  }
  const child = spawn(python, [
    "run_job.py",
    "--job-id", job.jobId,
    "--episode-id", episodeId,
    "--profile", job.profile,
    "--request", job.request,
  ], { cwd: engineRoot, env: { ...process.env, PYTHONPATH: engineRoot }, stdio: ["ignore", "pipe", "pipe"] });
  processes.set(job.jobId, child);
  job.status = "RUNNING";
  job.stage = "UNDERSTANDING";
  child.stdout.on("data", (chunk: Buffer) => {
    for (const line of chunk.toString().split(/\r?\n/).filter(Boolean)) parseEngineLine(job, line);
  });
  child.stderr.on("data", (chunk: Buffer) => {
    for (const line of chunk.toString().split(/\r?\n/).filter(Boolean)) parseEngineLine(job, `[engine] ${line}`);
  });
  child.on("error", (error) => {
    job.status = "FAILED";
    job.error = error.message;
    job.logs.push(`[engine] ${error.message}`);
  });
  child.on("close", (code) => {
    processes.delete(job.jobId);
    if (code === 0) {
      job.status = "VALIDATED";
      job.stage = "DELIVERY";
      job.progress = 100;
      job.downloadUrl = `/api/productions/${job.jobId}/video`;
    } else if (job.status !== "FAILED") {
      job.status = "FAILED";
      job.error ||= `Production process exited with code ${code ?? "unknown"}`;
    }
  });
}

const router: IRouter = Router();

router.get("/productions", (_req, res) => {
  res.json([...jobs.values()].reverse().map(publicJob));
});

router.post("/productions", (req, res) => {
  const parsed = CreateProductionBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Request must include production text. Add Title: and Language: lines." });
    return;
  }
  const request = parsed.data.request.trim();
  const episodeId = parsed.data.episodeId?.trim() || `chat-${randomUUID().slice(0, 8)}`;
  const profile = parsed.data.profile ?? "both";
  const titleMatch = request.match(/^\s*(?:Title|#)\s*[:#]?\s*(.+)$/im);
  const languageMatch = request.match(/^\s*Language\s*[:=]\s*(.+)$/im);
  if (!titleMatch || !languageMatch) {
    res.status(400).json({ error: "Include a real Title: and Language: in the current request so production has no hidden content source." });
    return;
  }
  const job: Production = {
    jobId: randomUUID().replaceAll("-", ""),
    episodeId,
    status: "QUEUED",
    stage: "QUEUED",
    progress: 0,
    title: titleMatch[1].trim(),
    language: languageMatch[1].trim(),
    profile,
    request,
    source: "chat",
    createdAt: new Date().toISOString(),
    finalMp4: null,
    downloadUrl: null,
    error: null,
    logs: ["[AURELIA] Request accepted from current Chat input.", "[AURELIA] Isolated production workspace reserved."],
    metadata: { source: "chat", inputBound: true },
  };
  jobs.set(job.jobId, job);
  startProcess(job);
  res.status(202).json(publicJob(job));
});

router.get("/productions/:jobId", (req, res) => {
  const parsed = GetProductionParams.safeParse(req.params);
  const job = parsed.success ? jobs.get(parsed.data.jobId) : undefined;
  if (!job) {
    res.status(404).json({ error: "Production not found in this server session." });
    return;
  }
  res.json(publicJob(job));
});

router.get("/productions/:jobId/video", (req, res) => {
  const parsed = GetProductionVideoParams.safeParse(req.params);
  const job = parsed.success ? jobs.get(parsed.data.jobId) : undefined;
  if (!job || job.status !== "VALIDATED" || !job.finalMp4 || !existsSync(job.finalMp4)) {
    res.status(404).json({ error: "A validated final MP4 is not available yet." });
    return;
  }
  res.download(job.finalMp4, `aurelia-${job.episodeId}-FINAL.mp4`);
});

export default router;
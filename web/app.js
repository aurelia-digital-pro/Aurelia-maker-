/* =============================================================
   AURELIA Maker — Production Factory Frontend
   All buttons are wired to real backend endpoints.
   No mock state. No placeholder actions.
   ============================================================= */

const API = "";

let activeJobId = null;
let pollTimer   = null;
let wsTerminal  = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────

const chatMessages    = document.getElementById("chat-messages");
const chatForm        = document.getElementById("chat-form");
const chatInput       = document.getElementById("chat-input");
const terminalOutput  = document.getElementById("terminal-output");
const tracker         = document.getElementById("tracker");
const trackerJobId    = document.getElementById("tracker-job-id");
const trackerStage    = document.getElementById("tracker-stage");
const trackerScene    = document.getElementById("tracker-scene");
const trackerPct      = document.getElementById("tracker-pct");
const trackerFill     = document.getElementById("tracker-fill");
const videoPanel      = document.getElementById("video-panel");
const finalVideo      = document.getElementById("final-video");
const downloadLink    = document.getElementById("download-link");
const episodeList     = document.getElementById("episode-list");
const jobList         = document.getElementById("job-list");
const backendPanel    = document.getElementById("backend-panel");
const backendDetail   = document.getElementById("backend-detail");
const fallbackReport  = document.getElementById("fallback-report");
const fallbackList    = document.getElementById("fallback-list");
const qcReport        = document.getElementById("qc-report");
const qcDetail        = document.getElementById("qc-detail");
const artifacts       = document.getElementById("artifacts");
const artifactList    = document.getElementById("artifact-list");
const statusSd        = document.getElementById("status-sd");
const statusTts       = document.getElementById("status-tts");
const statusFactory   = document.getElementById("status-factory");
const selLanguage     = document.getElementById("sel-language");
const selProfile      = document.getElementById("sel-profile");
const inpEpisodeId    = document.getElementById("inp-episode-id");

// ── API helpers ───────────────────────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${path}`);
  return res.json();
}

// ── chat messages ─────────────────────────────────────────────────────────

function addMsg(text, role = "bot") {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendTerminal(text) {
  terminalOutput.textContent += text + "\n";
  terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// ── backend status ────────────────────────────────────────────────────────

async function loadBackendStatus() {
  try {
    const data = await api("/api/status");
    // Factory
    statusFactory.textContent = "Factory OK";
    statusFactory.className   = "badge ok";
    // SD backend
    if (data.sd_available) {
      statusSd.textContent = `SD: ${data.sd_model || "ready"}`;
      statusSd.className   = "badge ok";
    } else {
      statusSd.textContent = "SD: Pillow fallback";
      statusSd.className   = "badge warn";
    }
    // TTS
    const tts = data.tts_backends || [];
    statusTts.textContent = tts.length ? `TTS: ${tts[0]}` : "TTS: none";
    statusTts.className   = tts.length ? "badge ok" : "badge danger";
    // Detail panel
    backendDetail.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    statusFactory.textContent = "Factory offline";
    statusFactory.className   = "badge danger";
    statusSd.textContent  = "SD: ?";
    statusTts.textContent = "TTS: ?";
    backendDetail.textContent = String(e);
  }
}

document.getElementById("btn-check-status").onclick = () => {
  backendPanel.hidden = !backendPanel.hidden;
  if (!backendPanel.hidden) loadBackendStatus();
};

// ── episode list ──────────────────────────────────────────────────────────

async function loadEpisodes() {
  try {
    const data = await api("/api/episodes");
    episodeList.innerHTML = "";
    for (const ep of (data.episodes || [])) {
      const li = document.createElement("li");
      li.className = ep.has_final ? "ok" : "";
      li.textContent = `Ep ${ep.id}${ep.has_final ? " ✓" : ""}`;
      li.title = `Episode ${ep.id}`;
      const latest = [...(ep.jobs || [])].reverse().find(j => j.has_final);
      if (latest) li.onclick = () => openJobVideo(latest.job_id, ep.id);
      episodeList.appendChild(li);
    }
  } catch (e) { /* server may not be ready */ }
}

// ── job list ─────────────────────────────────────────────────────────────

async function loadJobs() {
  try {
    const data = await api("/api/jobs");
    jobList.innerHTML = "";
    for (const job of (data.jobs || []).slice().reverse().slice(0, 12)) {
      const li = document.createElement("li");
      const statusClass = job.status === "COMPLETED" ? "ok" : job.status === "FAILED" ? "fail" : "running";
      li.className = statusClass;
      li.textContent = `${job.episode_id} — ${job.status} (${Math.round(job.progress || 0)}%)`;
      li.onclick = () => trackJob(job.job_id);
      jobList.appendChild(li);
    }
  } catch (e) { /* ok */ }
}

// ── video ────────────────────────────────────────────────────────────────────

function openJobVideo(jobId, episodeId) {
  const url = `${API}/api/jobs/${encodeURIComponent(jobId)}/video`;
  finalVideo.src     = `${url}?t=${Date.now()}`;
  downloadLink.href  = url;
  downloadLink.download = `episode-${String(episodeId).padStart(4, "0")}-FINAL.mp4`;
  videoPanel.hidden = false;
}

// ── job tracking ──────────────────────────────────────────────────────────

function openWs(jobId) {
  if (wsTerminal) wsTerminal.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  wsTerminal = new WebSocket(`${proto}://${location.host}/ws/terminal/${jobId}`);
  wsTerminal.onmessage = e => {
    const line = e.data;
    if (line.startsWith("[DONE]")) {
      // handled by poll
    } else if (line.startsWith("[FINAL]")) {
      // handled by poll
    } else {
      appendTerminal(line);
    }
  };
  wsTerminal.onerror = () => appendTerminal("[WS] connection error — falling back to poll");
}

function renderFallbacks(logs) {
  const falls = (logs || []).filter(l => l.includes("[FALLBACK]") || l.includes("[WARNING]"));
  if (falls.length === 0) { fallbackReport.hidden = true; return; }
  fallbackReport.hidden = false;
  fallbackList.innerHTML = "";
  falls.forEach(f => {
    const li = document.createElement("li"); li.textContent = f;
    fallbackList.appendChild(li);
  });
}

function renderQc(job) {
  if (!job.qc) { qcReport.hidden = true; return; }
  qcReport.hidden = false;
  qcDetail.textContent = JSON.stringify(job.qc, null, 2);
}

function renderArtifacts(job) {
  const outs = job.outputs || {};
  const keys = Object.keys(outs);
  if (!keys.length) { artifacts.hidden = true; return; }
  artifacts.hidden = false;
  artifactList.innerHTML = "";
  keys.forEach(k => {
    const li = document.createElement("li");
    li.textContent = `${k}: ${outs[k]}`;
    artifactList.appendChild(li);
  });
}

function trackJob(jobId) {
  activeJobId   = jobId;
  tracker.hidden = false;
  trackerJobId.textContent = jobId.slice(0, 8);
  terminalOutput.textContent = "";
  appendTerminal(`[FACTORY] Tracking job ${jobId}`);
  openWs(jobId);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      if (job.error === "not found") return;

      trackerStage.textContent = job.stage || "idle";
      trackerPct.textContent   = `${Math.round(job.progress || 0)}%`;
      trackerFill.style.width  = `${job.progress || 0}%`;
      trackerScene.textContent = job.scene_info ? `Scene ${job.scene_info}` : "";

      // replace terminal with latest logs
      if (job.logs && job.logs.length) {
        terminalOutput.textContent = job.logs.join("\n");
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
      }
      renderFallbacks(job.logs || []);
      renderQc(job);
      renderArtifacts(job);

      if (job.status === "COMPLETED") {
        clearInterval(pollTimer);
        trackerStage.textContent = "COMPLETED";
        addMsg(`Episode ${job.episode_id} complete!\n` +
               `${job.total_shots || ""} shots\nFINAL MP4 ready.`, "bot");
        openJobVideo(job.job_id, job.episode_id);
        loadEpisodes();
      } else if (job.status === "FAILED") {
        clearInterval(pollTimer);
        trackerStage.textContent = "FAILED";
        addMsg(`Production failed: ${job.error}`, "error");
      }
      loadJobs();
    } catch (e) { /* transient */ }
  }, 1500);
}

// ── Stop / Retry ────────────────────────────────────────────────────────────

document.getElementById("btn-stop-job").onclick = async () => {
  if (!activeJobId) return;
  try {
    const r = await api(`/api/jobs/${activeJobId}/stop`, { method: "POST" });
    addMsg(`Stop requested: ${r.status || JSON.stringify(r)}`, "bot");
    if (pollTimer) clearInterval(pollTimer);
    trackerStage.textContent = "STOPPED";
  } catch (e) { addMsg(`Stop error: ${e.message}`, "error"); }
};

document.getElementById("btn-retry-job").onclick = async () => {
  if (!activeJobId) return;
  try {
    const r = await api(`/api/jobs/${activeJobId}/retry`, { method: "POST" });
    if (r.job_id) {
      addMsg(`Retry started: job ${r.job_id}`, "bot");
      trackJob(r.job_id);
    } else {
      addMsg(`Retry response: ${JSON.stringify(r)}`, "bot");
    }
  } catch (e) { addMsg(`Retry error: ${e.message}`, "error"); }
};

// ── New Episode ──────────────────────────────────────────────────────────

document.getElementById("btn-new-episode").onclick = () => {
  videoPanel.hidden = true;
  tracker.hidden    = true;
  activeJobId       = null;
  if (pollTimer) clearInterval(pollTimer);
  terminalOutput.textContent = "";
  chatInput.focus();
  addMsg("ابدأ بكتابة السيناريو في خانة Chat\nCreate new episode: write script in Chat.", "bot");
};

// ── Refresh buttons ───────────────────────────────────────────────────────

document.getElementById("btn-refresh-episodes").onclick = loadEpisodes;
document.getElementById("btn-refresh-jobs").onclick      = loadJobs;

// ── Terminal controls ─────────────────────────────────────────────────────

document.getElementById("btn-clear-terminal").onclick = () => {
  terminalOutput.textContent = "";
};
document.getElementById("btn-copy-terminal").onclick = () => {
  navigator.clipboard.writeText(terminalOutput.textContent);
};

// ── Chat submit ────────────────────────────────────────────────────────────

chatForm.addEventListener("submit", async e => {
  e.preventDefault();
  const raw = chatInput.value.trim();
  if (!raw) return;
  chatInput.value = "";
  addMsg(raw, "user");

  // Inject sidebar settings into the message if set
  let message = raw;
  const lang    = selLanguage.value;
  const profile = selProfile.value;
  const epId    = inpEpisodeId.value.trim();

  // Only inject if not already in message
  if (epId && !message.includes(epId)) {
    message = `Create Episode ${epId}\n${message}`;
  }

  let result;
  try {
    result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, language: lang, profile }),
    });
  } catch (err) {
    addMsg(`Error: ${err.message}`, "error");
    return;
  }

  addMsg(result.reply || "OK", "bot");
  if (result.job_id) {
    trackJob(result.job_id);
  }
});

// ── init ───────────────────────────────────────────────────────────────────────

addMsg(
  "AURELIA Cinematic Production Factory\n" +
  "─────────────────────\n" +
  "Send script in Chat to begin production.\n" +
  "Format: Episode ID + Title + Language + script\n" +
  "Logs: right panel | Status: top bar",
  "bot"
);

loadBackendStatus();
loadEpisodes();
loadJobs();
setInterval(loadJobs, 5000);

const API = "";

let activeJobId = null;
let pollTimer = null;

const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const terminalOutput = document.getElementById("terminal-output");
const progressPanel = document.getElementById("progress-panel");
const progressStage = document.getElementById("progress-stage");
const progressPct = document.getElementById("progress-pct");
const progressFill = document.getElementById("progress-fill");
const videoPanel = document.getElementById("video-panel");
const finalVideo = document.getElementById("final-video");
const downloadLink = document.getElementById("download-link");
const episodeList = document.getElementById("episode-list");
const jobList = document.getElementById("job-list");
const episodeDialog = document.getElementById("episode-dialog");
const episodeForm = document.getElementById("episode-form");

function addMessage(text, role = "bot") {
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

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  return res.json();
}

async function loadEpisodes() {
  const data = await api("/api/episodes");
  episodeList.innerHTML = "";
  for (const ep of data.episodes || []) {
    const li = document.createElement("li");
    li.textContent = `Episode ${ep.id}${ep.has_final ? " ✓" : ""}`;
    const latest = [...(ep.jobs || [])].reverse().find((job) => job.has_final);
    li.onclick = () => latest && showJobVideo(latest.job_id, ep.id);
    episodeList.appendChild(li);
  }
}

async function loadJobs() {
  const data = await api("/api/jobs");
  jobList.innerHTML = "";
  for (const job of (data.jobs || []).slice().reverse()) {
    const li = document.createElement("li");
    li.textContent = `${job.episode_id} — ${job.status} (${Math.round(job.progress)}%)`;
    li.onclick = () => trackJob(job.job_id);
    jobList.appendChild(li);
  }
}

function showJobVideo(jobId, episodeId) {
  const url = `/api/jobs/${encodeURIComponent(jobId)}/video`;
  finalVideo.src = `${url}?t=${Date.now()}`;
  downloadLink.href = url;
  downloadLink.download = `episode-${String(episodeId).padStart(4, "0")}-FINAL.mp4`;
  videoPanel.hidden = false;
}

async function trackJob(jobId) {
  activeJobId = jobId;
  progressPanel.hidden = false;
  terminalOutput.textContent = "";
  appendTerminal(`[FACTORY] Tracking job ${jobId}`);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const job = await api(`/api/jobs/${jobId}`);
    if (job.error && job.error === "not found") return;

    progressStage.textContent = job.stage || "—";
    progressPct.textContent = `${Math.round(job.progress || 0)}%`;
    progressFill.style.width = `${job.progress || 0}%`;

    const logs = job.logs || [];
    terminalOutput.textContent = logs.join("\n");
    terminalOutput.scrollTop = terminalOutput.scrollHeight;

    if (job.status === "COMPLETED") {
      clearInterval(pollTimer);
      addMessage(`Episode ${job.episode_id} complete!\nFINAL MP4 ready.`, "bot");
      showJobVideo(job.job_id, job.episode_id);
      loadEpisodes();
    } else if (job.status === "FAILED") {
      clearInterval(pollTimer);
      addMessage(`Production failed: ${job.error}`, "bot");
    }
    loadJobs();
  }, 1500);
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  addMessage(message, "user");

  const result = await api("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });

  addMessage(result.reply || "OK", "bot");

  if (result.job_id) {
    trackJob(result.job_id);
  }
});

// Production is Chat-only. The legacy dialog no longer starts a separate
// production path; it only focuses the canonical Chat input.
if (document.getElementById("btn-new-episode")) {
  document.getElementById("btn-new-episode").onclick = () => {
    episodeDialog.close();
    chatInput.focus();
    addMessage("Send Episode ID + Title + Language + complete script in Chat.", "bot");
  };
}
if (document.getElementById("dialog-cancel")) {
  document.getElementById("dialog-cancel").onclick = () => episodeDialog.close();
}

if (episodeForm) {
  episodeForm.addEventListener("submit", (e) => {
    e.preventDefault();
    episodeDialog.close();
    chatInput.focus();
  });
}

addMessage(
  "Welcome to AURELIA Maker.\nSend Episode ID + Title + Language + the complete episode content in Chat.",
  "bot"
);

loadEpisodes();
loadJobs();
setInterval(loadJobs, 5000);

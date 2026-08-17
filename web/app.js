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
    li.onclick = () => showEpisodeVideo(ep.id);
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

function showEpisodeVideo(episodeId) {
  const ep = episodeId.padStart(4, "0");
  finalVideo.src = `/api/video/${ep}?t=${Date.now()}`;
  downloadLink.href = `/api/video/${ep}`;
  downloadLink.download = `episode-${ep}-FINAL.mp4`;
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
      showEpisodeVideo(job.episode_id);
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

document.getElementById("btn-new-episode").onclick = () => episodeDialog.showModal();
document.getElementById("dialog-cancel").onclick = () => episodeDialog.close();

episodeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const episodeId = document.getElementById("episode-id-input").value.padStart(4, "0");
  const profile = document.getElementById("profile-input").value;
  episodeDialog.close();

  addMessage(`Create Episode ${episodeId}`, "user");
  const result = await api("/api/episodes/produce", {
    method: "POST",
    body: JSON.stringify({ episode_id: episodeId, profile }),
  });

  addMessage(`Production started for Episode ${episodeId}.`, "bot");
  if (result.job_id) trackJob(result.job_id);
});

addMessage(
  "Welcome to AURELIA Maker.\nEnter an episode request such as: Create Episode <ID>",
  "bot"
);

loadEpisodes();
loadJobs();
setInterval(loadJobs, 5000);

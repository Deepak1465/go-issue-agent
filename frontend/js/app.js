const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let pollTimer = null;

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const gemini = $("#pillGemini");
    const go = $("#pillGo");

    if (data.gemini_configured) {
      gemini.textContent = "Gemini ✓";
      gemini.classList.add("ok");
    } else {
      gemini.textContent = "Gemini ✗ (set API key)";
      gemini.classList.add("warn");
    }

    if (data.go_available) {
      go.textContent = "Go ✓";
      go.classList.add("ok");
    } else {
      go.textContent = "Go ✗ (install Go)";
      go.classList.add("warn");
    }
  } catch {
    $("#pillGemini").textContent = "Server offline";
  }
}

function setRunning(running) {
  const btn = $("#runBtn");
  const label = btn.querySelector(".btn-label");
  btn.disabled = running;
  $("#demoBtn").disabled = running;
  if (running) {
    label.innerHTML = '<span class="spinner"></span>Running…';
  } else {
    label.textContent = "Run Agent";
  }
}

function showProgress(show) {
  $("#progressSection").hidden = !show;
}

function updateProgress(job) {
  $("#jobId").textContent = `job: ${job.id}`;
  $("#progressMsg").textContent = job.message || job.phase || "Working…";

  const pct = job.max_turns ? Math.min(95, (job.turn / job.max_turns) * 100) : 10;
  $("#progressFill").style.width = `${job.status === "completed" ? 100 : pct}%`;

  const log = $("#eventLog");
  const events = job.events || [];
  const recent = events.slice(-12);
  log.innerHTML = recent
    .map((e) => {
      if (e.type === "tool") {
        return `<li class="tool">[turn ${e.turn}] → ${e.tool}(${JSON.stringify(e.args)})</li>`;
      }
      if (e.type === "tool_result" && !e.success) {
        return `<li class="error">[turn ${e.turn}] ← ${e.tool}: ${e.result}</li>`;
      }
      if (e.type === "tool_result") {
        return `<li class="success">[turn ${e.turn}] ← ${e.tool} OK</li>`;
      }
      if (e.type === "phase") {
        return `<li>${e.message}</li>`;
      }
      if (e.type === "error") {
        return `<li class="error">${e.message}</li>`;
      }
      return "";
    })
    .join("");
  log.scrollTop = log.scrollHeight;
}

function simpleMarkdown(md) {
  return md
    .replace(/^### (.*$)/gim, "<h3>$1</h3>")
    .replace(/^## (.*$)/gim, "<h2>$1</h2>")
    .replace(/^# (.*$)/gim, "<h1>$1</h1>")
    .replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

function showResults(data) {
  $("#resultsPanel").hidden = false;

  const issue = data.issue || {};
  const pr = data.pr || {};
  $("#resultTitle").textContent = pr.title || `Issue #${issue.number}`;
  $("#resultMeta").textContent = [
    issue.title,
    data.branch ? `branch: ${data.branch}` : null,
    data.turns ? `${data.turns} turns` : null,
    data.demo ? "(sample output)" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const badge = $("#prBadge");
  if (data.pr_ready || pr.title) {
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }

  const summary = data.pr_summary_md || formatSummary(data);
  $("#prSummary").innerHTML = simpleMarkdown(summary);
  $("#diffCode").textContent = data.diff || "(no diff)";

  const actions = data.actions || [];
  $("#actionList").innerHTML = actions
    .map(
      (a) => `
    <li>
      <code>${a.tool}</code>
      <span class="args">${JSON.stringify(a.args || {})}</span>
    </li>`
    )
    .join("");
}

function formatSummary(data) {
  const pr = data.pr || {};
  return `# ${pr.title || "Pull Request Summary"}\n\n${pr.body || ""}`;
}

async function loadSample() {
  setRunning(true);
  showProgress(false);
  try {
    const res = await fetch("/api/sample");
    const data = await res.json();
    showResults(data);
  } catch (err) {
    alert("Failed to load sample: " + err.message);
  } finally {
    setRunning(false);
  }
}

async function pollJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  const job = await res.json();
  updateProgress(job);

  if (job.status === "completed" && job.result) {
    clearInterval(pollTimer);
    setRunning(false);
    showResults({
      issue: job.result.issue,
      pr: job.result.pr,
      branch: job.result.branch,
      turns: job.result.turns,
      diff: job.result.diff,
      actions: job.result.actions,
      pr_summary_md: job.pr_summary_md,
      pr_ready: job.result.pr_ready,
    });
    $("#progressMsg").textContent = "Completed!";
    return;
  }

  if (job.status === "failed") {
    clearInterval(pollTimer);
    setRunning(false);
    $("#progressMsg").textContent = `Failed: ${job.error || "Unknown error"}`;
  }
}

$("#runForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const issueUrl = $("#issueUrl").value.trim();
  if (!issueUrl) return;

  setRunning(true);
  showProgress(true);
  $("#eventLog").innerHTML = "";
  $("#resultsPanel").hidden = true;

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ issue_url: issueUrl, max_turns: 30 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to start");

    pollTimer = setInterval(() => pollJob(data.job_id), 1500);
    pollJob(data.job_id);
  } catch (err) {
    setRunning(false);
    alert(err.message);
  }
});

$("#demoBtn").addEventListener("click", loadSample);

$$(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("#issueUrl").value = chip.dataset.url;
  });
});

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".tab-content").forEach((c) => c.classList.remove("active"));
    tab.classList.add("active");
    $(`#tab-${tab.dataset.tab}`).classList.add("active");
  });
});

checkHealth();

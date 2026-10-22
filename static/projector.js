// Projector: ask the server for the current question every second and redraw the bars.
(function () {
  const POLL_MS = 1000;

  const waiting = document.getElementById("waiting");
  const live = document.getElementById("live");
  const questionEl = document.getElementById("proj-question");
  const barsEl = document.getElementById("proj-bars");
  const counterEl = document.getElementById("proj-counter");
  const statusEl = document.getElementById("proj-status");
  const totalEl = document.getElementById("proj-total");
  const totalLabelEl = document.getElementById("proj-total-label");
  const connection = document.getElementById("connection");

  // Rebuild the bar rows only when the question changes, so widths can animate.
  let renderedKey = null;

  function buildBars(question) {
    barsEl.replaceChildren();
    question.options.forEach((option, i) => {
      const row = document.createElement("div");
      row.className = `bar-row opt-${i}`;

      const label = document.createElement("div");
      label.className = "bar-label";
      label.textContent = option.text;

      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      track.appendChild(fill);

      const stats = document.createElement("div");
      stats.className = "bar-stats";
      stats.innerHTML = '<span class="bar-percent"></span><span class="bar-count"></span>';

      row.append(label, track, stats);
      barsEl.appendChild(row);
    });
  }

  function render(data) {
    document.querySelectorAll(".proj-join-code, .proj-big-code").forEach((el) => {
      el.textContent = data.join_code;
    });

    const question = data.question;
    if (!question) {
      waiting.hidden = false;
      live.hidden = true;
      counterEl.textContent = "";
      renderedKey = null;
      return;
    }

    waiting.hidden = true;
    live.hidden = false;

    const key = question.id + "|" + question.options.map((o) => o.text).join("|");
    if (key !== renderedKey) {
      questionEl.textContent = question.text;
      buildBars(question);
      renderedKey = key;
    }

    const topVotes = Math.max(...question.options.map((o) => o.votes));
    barsEl.querySelectorAll(".bar-row").forEach((row, i) => {
      const option = question.options[i];
      row.querySelector(".bar-fill").style.width = option.percent + "%";
      row.querySelector(".bar-percent").textContent = option.percent + "%";
      row.querySelector(".bar-count").textContent =
        option.votes + (option.votes === 1 ? " vote" : " votes");
      row.classList.toggle("leading", topVotes > 0 && option.votes === topVotes);
    });

    counterEl.textContent = `Question ${question.number} of ${question.count}`;
    totalEl.textContent = question.total;
    totalLabelEl.textContent = question.total === 1 ? "vote" : "votes";
    statusEl.textContent = question.open ? "Voting open" : "Voting closed";
    statusEl.classList.toggle("closed", !question.open);
  }

  async function poll() {
    try {
      const response = await fetch("/api/current", { cache: "no-store" });
      if (!response.ok) throw new Error("Server returned " + response.status);
      render(await response.json());
      connection.hidden = true;
    } catch (err) {
      connection.hidden = false;
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }

  poll();
})();

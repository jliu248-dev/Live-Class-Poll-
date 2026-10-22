// Student voting page: follow the current question every second and send votes.
(function () {
  const POLL_MS = 1000;

  const loading = document.getElementById("vote-loading");
  const waiting = document.getElementById("vote-waiting");
  const questionBox = document.getElementById("vote-question");
  const counterEl = document.getElementById("vote-counter");
  const textEl = document.getElementById("vote-text");
  const optionsEl = document.getElementById("vote-options");
  const errorEl = document.getElementById("vote-error");
  const doneEl = document.getElementById("vote-done");
  const closedEl = document.getElementById("vote-closed");
  const connection = document.getElementById("connection");

  let currentId = null;
  let chosenIndex = null;
  let submitting = false;
  let latest = null;

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function buildOptions(question) {
    optionsEl.replaceChildren();
    question.options.forEach((option, i) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `vote-option opt-${i}`;
      button.innerHTML = '<span class="swatch"></span><span class="vote-option-text"></span>';
      button.querySelector(".vote-option-text").textContent = option.text;
      button.addEventListener("click", () => submitVote(question.id, i));
      optionsEl.appendChild(button);
    });
  }

  function render(data) {
    // The teacher made a new class code: reload to show the join form again.
    if (data.joined === false) {
      window.location.reload();
      return;
    }
    latest = data;
    loading.hidden = true;
    const question = data.question;

    if (!question) {
      waiting.hidden = false;
      questionBox.hidden = true;
      currentId = null;
      return;
    }

    waiting.hidden = true;
    questionBox.hidden = false;

    if (question.id !== currentId) {
      currentId = question.id;
      chosenIndex = null;
      errorEl.hidden = true;
      counterEl.textContent = `Question ${question.number} of ${question.count}`;
      textEl.textContent = question.text;
      buildOptions(question);
    }

    const locked = data.has_voted || !question.open || submitting;
    optionsEl.querySelectorAll(".vote-option").forEach((button, i) => {
      button.disabled = locked;
      button.classList.toggle("chosen", i === chosenIndex);
    });
    doneEl.hidden = !data.has_voted;
    closedEl.hidden = data.has_voted || question.open;
  }

  async function submitVote(questionId, optionIndex) {
    if (submitting) return;
    submitting = true;
    errorEl.hidden = true;
    if (latest) render(latest);

    try {
      const response = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_id: questionId, option: optionIndex }),
      });
      const body = await response.json().catch(() => ({}));
      if (response.status === 403) {
        window.location.reload();
        return;
      }
      if (response.ok) {
        chosenIndex = optionIndex;
        latest = { ...latest, has_voted: true };
      } else {
        showError(body.error || "Your vote couldn't be saved. Please try again.");
      }
    } catch (err) {
      showError("Couldn't send your vote. Check your connection and try again.");
    } finally {
      submitting = false;
      if (latest) render(latest);
    }
  }

  async function poll() {
    try {
      const response = await fetch("/api/current", { cache: "no-store" });
      if (!response.ok) throw new Error("Server returned " + response.status);
      const data = await response.json();
      if (!submitting) render(data);
      connection.hidden = true;
    } catch (err) {
      connection.hidden = false;
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }

  poll();
})();

// Teacher page: let the "Add another option" button add answer fields, up to the limit.
(function () {
  const container = document.getElementById("options");
  const addButton = document.getElementById("add-option");
  const max = Number(container.dataset.max);

  function updateButton() {
    addButton.hidden = container.children.length >= max;
  }

  addButton.addEventListener("click", () => {
    const count = container.children.length;
    if (count >= max) return;

    const row = container.lastElementChild.cloneNode(true);
    const swatch = row.querySelector(".swatch");
    const input = row.querySelector("input");
    swatch.className = `swatch opt-${count}`;
    input.value = "";
    input.placeholder = `Option ${count + 1}`;
    input.setAttribute("aria-label", `Option ${count + 1}`);
    container.appendChild(row);
    input.focus();
    updateButton();
  });

  updateButton();
})();

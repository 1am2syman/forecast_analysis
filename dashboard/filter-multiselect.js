/* Search and selection helpers shared by Product filter controls and tests. */
((root, factory) => {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FilterMultiSelect = api;
})(typeof globalThis === "undefined" ? window : globalThis, () => {
  function normalizeText(value) {
    return String(value ?? "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function editDistanceWithinOne(left, right) {
    if (left === right) return true;
    if (Math.abs(left.length - right.length) > 1) return false;
    let leftIndex = 0;
    let rightIndex = 0;
    let edits = 0;
    while (leftIndex < left.length && rightIndex < right.length) {
      if (left[leftIndex] === right[rightIndex]) {
        leftIndex += 1;
        rightIndex += 1;
        continue;
      }
      edits += 1;
      if (edits > 1) return false;
      if (left.length > right.length) leftIndex += 1;
      else if (right.length > left.length) rightIndex += 1;
      else {
        leftIndex += 1;
        rightIndex += 1;
      }
    }
    return (
      edits + Number(leftIndex < left.length || rightIndex < right.length) <= 1
    );
  }

  function tokenScore(queryToken, candidateTokens, compactCandidate) {
    let best = null;
    for (const candidateToken of candidateTokens) {
      let score = null;
      if (candidateToken === queryToken) score = 100;
      else if (queryToken.length >= 2 && candidateToken.startsWith(queryToken))
        score = 85;
      else if (queryToken.length >= 2 && candidateToken.includes(queryToken))
        score = 70;
      else if (
        queryToken.length >= 3 &&
        candidateToken.length >= 3 &&
        editDistanceWithinOne(queryToken, candidateToken)
      )
        score = 55;
      if (score !== null) best = Math.max(best ?? score, score);
    }
    if (
      best === null &&
      queryToken.length >= 2 &&
      compactCandidate.includes(queryToken)
    )
      best = 60;
    return best;
  }

  function fuzzyScore(query, candidate) {
    const normalizedQuery = normalizeText(query);
    if (!normalizedQuery) return 1;
    const normalizedCandidate = normalizeText(candidate);
    const candidateTokens = normalizedCandidate.split(" ").filter(Boolean);
    const compactCandidate = candidateTokens.join("");
    const scores = normalizedQuery
      .split(" ")
      .filter(Boolean)
      .map((queryToken) =>
        tokenScore(queryToken, candidateTokens, compactCandidate),
      );
    if (scores.some((score) => score === null)) return null;
    return scores.reduce((total, score) => total + score, 0);
  }

  function rankOptions(options, query) {
    return (options || [])
      .map((option, index) => ({
        option,
        index,
        score: fuzzyScore(query, option.searchText || option.label),
      }))
      .filter((entry) => entry.score !== null)
      .sort(
        (left, right) =>
          Number(Boolean(left.option.disabled)) -
            Number(Boolean(right.option.disabled)) ||
          right.score - left.score ||
          left.option.label.localeCompare(right.option.label) ||
          left.index - right.index,
      )
      .map((entry) => entry.option);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function setMarkup(element, markup) {
    const parsed = new DOMParser().parseFromString(
      `<body>${markup}</body>`,
      "text/html",
    );
    element.replaceChildren(...parsed.body.childNodes);
  }

  let instanceCount = 0;

  function create(root, { onChange } = {}) {
    const fieldLabel =
      root
        .closest(".compact-field")
        ?.querySelector(":scope > span")
        ?.textContent?.trim() || "Product filter";
    const allLabel = root.dataset.allLabel || `All ${fieldLabel.toLowerCase()}`;
    instanceCount += 1;
    const listId = `filter-multiselect-${root.dataset.productFilter}-${instanceCount}`;
    root.classList.add("filter-multiselect");
    setMarkup(
      root,
      `
        <button class="filter-multiselect__trigger" type="button" aria-haspopup="listbox" aria-expanded="false" data-action="product-filter-toggle" data-multiselect-trigger>
          <span data-multiselect-summary>${escapeHtml(allLabel)}</span><i aria-hidden="true"></i>
        </button>
        <div class="filter-multiselect__popover" data-multiselect-popover hidden>
          <label class="filter-multiselect__search">
            <span>Search ${escapeHtml(fieldLabel.toLowerCase())}</span>
            <input type="search" role="combobox" autocomplete="off" aria-autocomplete="list" aria-controls="${escapeHtml(listId)}" aria-expanded="true" placeholder="Type to filter…" data-multiselect-search />
          </label>
          <div class="filter-multiselect__meta">
            <span data-multiselect-count>No selections</span>
            <button type="button" data-action="product-filter-clear" data-multiselect-clear>Clear all</button>
          </div>
          <div class="filter-multiselect__list" id="${escapeHtml(listId)}" role="listbox" aria-label="${escapeHtml(fieldLabel)}" aria-multiselectable="true" data-multiselect-list></div>
        </div>`,
    );

    const trigger = root.querySelector("[data-multiselect-trigger]");
    const popover = root.querySelector("[data-multiselect-popover]");
    const search = root.querySelector("[data-multiselect-search]");
    const list = root.querySelector("[data-multiselect-list]");
    const clear = root.querySelector("[data-multiselect-clear]");
    let options = [];
    let selected = new Set();
    let activeIndex = -1;

    const optionKey = (value) => String(value);
    const visibleOptions = () => {
      const selectedOptions = options.filter((option) =>
        selected.has(optionKey(option.value)),
      );
      const unselected = rankOptions(
        options.filter((option) => !selected.has(optionKey(option.value))),
        search.value,
      );
      return [...selectedOptions, ...unselected];
    };

    function summary() {
      return selected.size ? `${selected.size} selected` : allLabel;
    }

    const selectableIndices = (visible) =>
      visible
        .map((option, index) => ({ option, index }))
        .filter(({ option }) => !option.disabled)
        .map(({ index }) => index);

    function render() {
      const visible = visibleOptions();
      root.querySelector("[data-multiselect-summary]").textContent = summary();
      root.querySelector("[data-multiselect-count]").textContent = selected.size
        ? `${selected.size} selected`
        : "No selections";
      clear.disabled = selected.size === 0;
      activeIndex = Math.min(activeIndex, visible.length - 1);
      setMarkup(
        list,
        visible.length
          ? visible
              .map((option, index) => {
                const key = optionKey(option.value);
                const isSelected = selected.has(key);
                const isDisabled = Boolean(option.disabled) && !isSelected;
                const id = `${listId}-option-${index}`;
                return `<div class="filter-multiselect__option${isSelected ? " is-selected" : ""}${isDisabled ? " is-disabled" : ""}" id="${escapeHtml(id)}" role="option" aria-selected="${isSelected}" aria-disabled="${isDisabled}" data-filter-option="${escapeHtml(key)}" data-filter-option-index="${index}"><i aria-hidden="true">${isSelected ? "✓" : ""}</i><span>${escapeHtml(option.label)}</span></div>`;
              })
              .join("")
          : '<p class="filter-multiselect__empty">No matching options</p>',
      );
      const active = list.querySelector(
        `[data-filter-option-index="${activeIndex}"]`,
      );
      search.setAttribute("aria-activedescendant", active?.id || "");
    }

    function setOpen(open) {
      popover.hidden = !open;
      trigger.setAttribute("aria-expanded", String(open));
      root.classList.toggle("is-open", open);
      if (open) {
        render();
        requestAnimationFrame(() => search.focus());
      } else {
        activeIndex = -1;
        search.value = "";
        search.removeAttribute("aria-activedescendant");
      }
    }

    function toggle(key, { notify = true } = {}) {
      const option = options.find((item) => optionKey(item.value) === key);
      if (option?.disabled && !selected.has(key)) return;
      if (selected.has(key)) selected.delete(key);
      else selected.add(key);
      render();
      if (notify) onChange?.(value());
    }

    function value() {
      return options
        .filter((option) => selected.has(optionKey(option.value)))
        .map((option) => option.value);
    }

    function setOptions(nextOptions, nextSelected = []) {
      options = (nextOptions || []).map((option) => ({ ...option }));
      const valid = new Set(options.map((option) => optionKey(option.value)));
      selected = new Set(
        (nextSelected || []).map(optionKey).filter((key) => valid.has(key)),
      );
      render();
    }

    function setValue(nextSelected = []) {
      setOptions(options, nextSelected);
    }

    trigger.addEventListener("click", () => setOpen(popover.hidden));
    trigger.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown") return;
      event.preventDefault();
      setOpen(true);
    });
    search.addEventListener("input", () => {
      activeIndex = selectableIndices(visibleOptions())[0] ?? -1;
      render();
    });
    search.addEventListener("keydown", (event) => {
      const visible = visibleOptions();
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        const indices = selectableIndices(visible);
        const direction = event.key === "ArrowDown" ? 1 : -1;
        const current = indices.indexOf(activeIndex);
        if (!indices.length) activeIndex = -1;
        else if (current === -1)
          activeIndex = direction === 1 ? indices[0] : indices.at(-1);
        else
          activeIndex =
            indices[(current + direction + indices.length) % indices.length];
        render();
      } else if (event.key === "Enter" && activeIndex >= 0) {
        event.preventDefault();
        toggle(optionKey(visible[activeIndex].value));
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        trigger.focus();
      }
    });
    list.addEventListener("click", (event) => {
      const option = event.target.closest("[data-filter-option]");
      if (option) toggle(option.dataset.filterOption);
    });
    list.addEventListener("pointermove", (event) => {
      const option = event.target.closest("[data-filter-option-index]");
      if (!option) return;
      activeIndex = Number(option.dataset.filterOptionIndex);
      search.setAttribute("aria-activedescendant", option.id);
    });
    clear.addEventListener("click", () => {
      if (!selected.size) return;
      selected.clear();
      render();
      onChange?.(value());
      search.focus();
    });
    document.addEventListener("pointerdown", (event) => {
      if (!popover.hidden && !root.contains(event.target)) setOpen(false);
    });

    render();
    return { close: () => setOpen(false), setOptions, setValue, value };
  }

  return { create, fuzzyScore, normalizeText, rankOptions };
});

// Progressive-enhance any <select multiple class="chip-source"> into a
// chip-button + popover. The underlying <select> stays in the DOM as the
// source of truth so form submission keeps working — we only mutate its
// .selected on each toggle. No JS = native multi-select fallback.
(function () {
  "use strict";

  function buildOptionData(select) {
    const options = [];
    for (const o of select.options) {
      if (!o.value) continue;
      options.push({
        value: o.value,
        label: o.textContent.trim(),
        count: parseInt(o.dataset.count || "0", 10),
      });
    }
    return options;
  }

  function selectedValues(select) {
    return Array.from(select.selectedOptions).map((o) => o.value);
  }

  function renderChipLabel(button, defaultLabel, selected) {
    if (selected.length === 0) {
      button.innerHTML = `${defaultLabel} <span class="chip-caret">▾</span>`;
      button.classList.remove("chip-active");
    } else if (selected.length === 1) {
      button.innerHTML = `${defaultLabel}: <strong>${selected[0]}</strong> <span class="chip-caret">▾</span>`;
      button.classList.add("chip-active");
    } else {
      button.innerHTML = `${defaultLabel}: <strong>${selected[0]}</strong> <span class="chip-pill">+${selected.length - 1}</span> <span class="chip-caret">▾</span>`;
      button.classList.add("chip-active");
    }
  }

  function buildPopover(select, options, groupPrefix) {
    const pop = document.createElement("div");
    pop.className = "chip-popover";
    pop.setAttribute("role", "listbox");
    pop.setAttribute("aria-multiselectable", "true");

    const searchWrap = document.createElement("div");
    searchWrap.className = "chip-search";
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.placeholder = "Filter…";
    searchInput.autocomplete = "off";
    searchWrap.appendChild(searchInput);
    pop.appendChild(searchWrap);

    const list = document.createElement("div");
    list.className = "chip-list";
    pop.appendChild(list);

    // Two groups when groupPrefix is set: items starting with prefix go up top
    // (e.g. "Remote — Europe / Worldwide / unspecified" pinned), the rest below.
    let group1 = options;
    let group2 = [];
    if (groupPrefix) {
      group1 = options.filter((o) => o.value.startsWith(groupPrefix));
      group2 = options
        .filter((o) => !o.value.startsWith(groupPrefix))
        .sort((a, b) => a.label.localeCompare(b.label));
    }

    function renderRow(opt, dom) {
      const id = `chip-opt-${select.id}-${opt.value.replace(/\W+/g, "_")}`;
      const row = document.createElement("label");
      row.className = "chip-row";
      row.dataset.search = opt.label.toLowerCase();
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = id;
      cb.value = opt.value;
      const native = Array.from(select.options).find((o) => o.value === opt.value);
      cb.checked = !!(native && native.selected);
      cb.addEventListener("change", () => {
        if (native) native.selected = cb.checked;
        updateButton();
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      const text = document.createElement("span");
      text.className = "chip-row-text";
      text.innerHTML = `<span class="chip-row-label">${opt.label}</span><span class="chip-row-count">${opt.count.toLocaleString()}</span>`;
      row.appendChild(cb);
      row.appendChild(text);
      dom.appendChild(row);
    }

    if (group1.length > 0 && groupPrefix) {
      const h = document.createElement("div");
      h.className = "chip-group-head";
      h.textContent = "Remote";
      list.appendChild(h);
    }
    for (const o of group1) renderRow(o, list);

    if (group2.length > 0) {
      const h = document.createElement("div");
      h.className = "chip-group-head";
      h.textContent = groupPrefix ? "Country" : "Options";
      list.appendChild(h);
      for (const o of group2) renderRow(o, list);
    }

    const footer = document.createElement("div");
    footer.className = "chip-footer";
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "chip-clear";
    clearBtn.textContent = "Clear";
    clearBtn.addEventListener("click", () => {
      for (const o of select.options) o.selected = false;
      for (const cb of pop.querySelectorAll('input[type="checkbox"]')) cb.checked = false;
      updateButton();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const doneBtn = document.createElement("button");
    doneBtn.type = "button";
    doneBtn.className = "chip-done";
    doneBtn.textContent = "Done";
    doneBtn.addEventListener("click", () => closePopover());
    footer.appendChild(clearBtn);
    footer.appendChild(doneBtn);
    pop.appendChild(footer);

    searchInput.addEventListener("input", () => {
      const q = searchInput.value.toLowerCase().trim();
      for (const row of list.querySelectorAll(".chip-row")) {
        const hit = !q || (row.dataset.search || "").includes(q);
        row.style.display = hit ? "" : "none";
      }
      // Hide group heads with no visible rows
      for (const head of list.querySelectorAll(".chip-group-head")) {
        let next = head.nextElementSibling;
        let any = false;
        while (next && !next.classList.contains("chip-group-head")) {
          if (next.classList.contains("chip-row") && next.style.display !== "none") {
            any = true; break;
          }
          next = next.nextElementSibling;
        }
        head.style.display = any ? "" : "none";
      }
    });

    let button, updateButton, closePopover;
    pop._wire = (b, u, c) => { button = b; updateButton = u; closePopover = c; };
    return pop;
  }

  function enhance(select) {
    const defaultLabel = select.dataset.chipLabel || "Filter";
    const groupPrefix = select.dataset.chipGroupPrefix || "";
    const options = buildOptionData(select);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");

    const popover = buildPopover(select, options, groupPrefix);
    popover.style.display = "none";

    function updateButton() {
      renderChipLabel(button, defaultLabel, selectedValues(select));
    }
    function closePopover() {
      popover.style.display = "none";
      button.setAttribute("aria-expanded", "false");
      document.removeEventListener("click", outsideClick, true);
      document.removeEventListener("keydown", escClose);
    }
    function outsideClick(e) {
      if (!popover.contains(e.target) && e.target !== button) closePopover();
    }
    function escClose(e) {
      if (e.key === "Escape") closePopover();
    }
    function openPopover() {
      popover.style.display = "";
      button.setAttribute("aria-expanded", "true");
      // Focus the search input for fast filter-by-typing
      const searchEl = popover.querySelector(".chip-search input");
      if (searchEl) setTimeout(() => searchEl.focus(), 0);
      document.addEventListener("click", outsideClick, true);
      document.addEventListener("keydown", escClose);
    }
    button.addEventListener("click", () => {
      if (popover.style.display === "none") openPopover();
      else closePopover();
    });

    popover._wire(button, updateButton, closePopover);

    const wrap = document.createElement("div");
    wrap.className = "chip-wrap";
    wrap.appendChild(button);
    wrap.appendChild(popover);
    select.parentNode.insertBefore(wrap, select);
    select.classList.add("chip-source-hidden");

    updateButton();
  }

  function init() {
    for (const sel of document.querySelectorAll("select.chip-source")) {
      enhance(sel);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

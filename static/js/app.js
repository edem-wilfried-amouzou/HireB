(() => {
  // Copier le lien public
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const el = document.querySelector(btn.dataset.copy);
    if (!el) return;
    navigator.clipboard.writeText(el.value || el.textContent).then(() => {
      const label = btn.textContent;
      btn.textContent = "Copié";
      setTimeout(() => (btn.textContent = label), 1500);
    });
  });

  // Confirmation avant une action sensible : <form data-confirm="Message">
  document.addEventListener("submit", (e) => {
    const msg = e.target.dataset && e.target.dataset.confirm;
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Démo de la page d'accueil : le nom apparaît à la présélection
  document.querySelectorAll("[data-reveal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const who = btn.closest(".demo-row").querySelector(".who");
      who.textContent = who.dataset.name;
      who.classList.add("on");
      btn.disabled = true;
      btn.textContent = "Présélectionné";
    });
  });

  // Afficher/masquer le bloc « travail à rendre »
  document.querySelectorAll("[data-toggle]").forEach((box) => {
    box.addEventListener("change", () => {
      document.querySelector(box.dataset.toggle).hidden = !box.checked;
    });
  });

  // Options visibles seulement pour « Choix unique »
  const syncKind = (row) => {
    const kind = row.querySelector('select[name$="-kind"]');
    const choices = row.querySelector(".js-choices");
    if (kind && choices) choices.hidden = kind.value !== "choice";
  };
  document.addEventListener("change", (e) => {
    if (e.target.matches('select[name$="-kind"]')) syncKind(e.target.closest("[data-row]"));
  });

  // Listes dynamiques (questions, sujets)
  document.querySelectorAll("[data-formset]").forEach((fs) => {
    const prefix = fs.dataset.formset;
    const total = document.getElementById(`id_${prefix}-TOTAL_FORMS`);
    const tpl = fs.querySelector(":scope > template");
    const list = fs.querySelector(":scope > [data-rows]");
    list.querySelectorAll("[data-row]").forEach(syncKind);

    fs.querySelector(":scope > div > [data-add]").addEventListener("click", () => {
      const n = parseInt(total.value, 10);
      list.insertAdjacentHTML("beforeend", tpl.innerHTML.replaceAll("__prefix__", n));
      total.value = n + 1;
      const row = list.lastElementChild;
      syncKind(row);
      row.querySelector("input[type=text], textarea")?.focus();
    });

    list.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-remove]");
      if (!btn) return;
      const row = btn.closest("[data-row]");
      const del = row.querySelector('input[name$="-DELETE"]');
      if (del) del.checked = true;
      row.hidden = true;
    });

    fs.closest("form").addEventListener("submit", () => {
      let i = 0;
      list.querySelectorAll("[data-row]:not([hidden])").forEach((row) => {
        const pos = row.querySelector('input[name$="-position"]');
        if (pos) pos.value = i++;
      });
    });
  });
})();

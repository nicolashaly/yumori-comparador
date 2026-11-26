// Yumori: atajo de búsqueda, favoritos (localStorage), filtros en drawer y fade-in de imágenes.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // "/" o Ctrl/Cmd+K enfocan la búsqueda; Escape la suelta.
  addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    const search = $(".search input");
    if (!search) return;
    if ((e.key === "/" && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
      e.preventDefault();
      search.focus();
      search.select();
    } else if (e.key === "Escape") {
      document.activeElement?.blur();
      closeFilters();
    }
  });

  // Favoritos guardados en el navegador (sin cuenta).
  const KEY = "yumori:fav";
  const read = () => {
    try {
      const ids = JSON.parse(localStorage.getItem(KEY));
      return Array.isArray(ids) && ids.every((id) => typeof id === "string") ? ids : [];
    } catch { return []; }
  };
  const write = (ids) => { try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch {} };
  const paint = () => {
    const ids = read();
    $$("[data-fav]").forEach((b) => {
      const on = ids.includes(b.dataset.fav);
      b.setAttribute("aria-pressed", on);
      const label = $(".label", b);
      if (label) label.textContent = on ? "Guardado" : "Guardar";
    });
    $$(".fav-count").forEach((c) => (c.textContent = ids.length || ""));
  };
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-fav]");
    if (!b) return;
    e.preventDefault();
    const id = b.dataset.fav;
    const ids = read();
    write(ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
    paint();
    const favGrid = $("#fav-grid");
    if (favGrid && !read().includes(id)) {
      b.closest(".card")?.remove();
      $("#fav-empty").hidden = !!favGrid.children.length;  // al quitar el último, mostrar el aviso en vez de una página en blanco
    }
  });
  paint();

  $("#fav-export")?.addEventListener("click", () => {
    const status = $("#fav-transfer-status");
    try {
      const raw = localStorage.getItem(KEY);
      const ids = raw === null ? [] : JSON.parse(raw);
      if (!Array.isArray(ids) || ids.some(id => typeof id !== "string" || !/^[0-9a-f]{10}$/.test(id))) throw new Error("Lista inválida");
      const blob = new Blob([JSON.stringify({ version: 1, key: KEY, ids }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = "yumori-favoritos.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = "Archivo exportado. Impórtalo en Favoritos de la nueva dirección; la lista de este sitio se conserva.";
    } catch { status.textContent = "No se pudo exportar. La lista guardada se conserva."; }
  });

  // Página de favoritos: pide las cards al servidor.
  const grid = $("#fav-grid");
  if (grid) {
    const status = document.createElement("div");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    const message = document.createElement("p");
    const retry = document.createElement("button");
    Object.assign(retry, { type: "button", className: "btn btn-ghost", textContent: "Reintentar", hidden: true });
    status.append(message, retry);
    grid.after(status);
    let loading = false;
    async function loadFavorites() {
      if (loading) return;
      const ids = read();
      $("#fav-empty").hidden = true;
      retry.hidden = true;
      if (!ids.length) {
        grid.innerHTML = "";
        message.textContent = "";
        $("#fav-empty").hidden = false;
        return;
      }
      loading = true;
      retry.disabled = true;
      grid.setAttribute("aria-busy", "true");
      message.textContent = "Cargando favoritos…";
      let reload = false;
      try {
        const parts = [];
        for (let i = 0; i < ids.length; i += 100) {
          const response = await fetch("/fragmento/cards?ids=" + encodeURIComponent(ids.slice(i, i + 100).join(",")));
          if (!response.ok) throw new Error("No se pudieron cargar los favoritos");
          parts.push(await response.text());
        }
        // Si se editó la lista durante la carga, volver a pedirla sin sobrescribir esos cambios.
        if (JSON.stringify(read()) !== JSON.stringify(ids)) { reload = true; return; }
        const cards = document.createElement("div");
        cards.innerHTML = parts.join("");
        const resolved = new Set();
        $$("[data-fav]", cards).forEach((b) => {
          if (resolved.has(b.dataset.fav)) b.closest(".card")?.remove();
          else resolved.add(b.dataset.fav);
        });
        // Resolver alias y omitir productos desaparecidos solo después de completar todos los lotes.
        grid.replaceChildren(...cards.children);
        write([...resolved]);
        paint(); imgs(); $("#fav-empty").hidden = !!grid.children.length;
        message.textContent = "";
      } catch {
        message.textContent = "Sin conexión: no se pudieron cargar tus favoritos. La lista guardada se conserva. Puedes reintentar.";
        retry.hidden = false;
      } finally {
        loading = false;
        retry.disabled = false;
        grid.setAttribute("aria-busy", "false");
        if (reload) loadFavorites();
      }
    }
    retry.addEventListener("click", loadFavorites);
    loadFavorites();
  }

  // Buscador: sugerencias de productos mientras se escribe (tarjetas horizontales que las arma el servidor).
  // Flechas para moverse, Enter abre la marcada (sin marcar, Enter busca como siempre) y Escape cierra.
  $$(".search").forEach((form, k) => {
    const input = $("input", form);
    const box = document.createElement("div");
    Object.assign(box, { className: "suggest", id: "suggest-" + k, hidden: true });
    box.setAttribute("role", "listbox");
    box.setAttribute("aria-label", "Sugerencias");
    form.append(box);
    for (const [a, v] of [["role", "combobox"], ["aria-autocomplete", "list"], ["aria-controls", box.id], ["aria-expanded", "false"]])
      input.setAttribute(a, v);
    let timer, ctrl, last = "", active = -1;
    const opts = () => $$("[role=option]", box);
    const show = (on) => { box.hidden = !on; input.setAttribute("aria-expanded", on); if (!on) mark(-1); };
    function mark(i) {
      opts().forEach((o, j) => o.setAttribute("aria-selected", j === i));
      active = i;
      const o = opts()[i];
      if (o) { input.setAttribute("aria-activedescendant", o.id); o.scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    function load() {
      const q = input.value.trim();
      if (q.length < 2) { last = q; ctrl?.abort(); show(false); return; }
      if (q === last) return show(true);
      last = q;
      ctrl?.abort();
      ctrl = new AbortController();
      fetch("/fragmento/sugerencias?q=" + encodeURIComponent(q), { signal: ctrl.signal })
        .then((r) => r.text())
        .then((html) => { box.innerHTML = html; show(true); mark(-1); imgs(); })
        .catch(() => {});
    }
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 150); });
    input.addEventListener("focus", () => { if (box.innerHTML && input.value.trim() === last && last.length >= 2) show(true); });
    input.addEventListener("keydown", (e) => {
      const o = opts();
      if (box.hidden || !o.length) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        mark(e.key === "ArrowDown" ? (active + 1) % o.length : active <= 0 ? o.length - 1 : active - 1);
      } else if (e.key === "Enter" && o[active]) {
        e.preventDefault();
        location.href = o[active].href;
      } else if (e.key === "Escape") {
        e.stopPropagation();  // el primer Escape cierra la lista; el segundo suelta la búsqueda
        show(false);
      }
    });
    box.addEventListener("mousedown", (e) => e.preventDefault());  // que el clic no le quite el foco al campo antes de abrir el enlace
    form.addEventListener("focusout", (e) => { if (!form.contains(e.relatedTarget)) show(false); });
  });

  // Franja de ofertas del inicio. En pantallas con mouse avanza sola cada 5 s, con flechas y pausa visible (WCAG 2.2.2), y se detiene con
  // el mouse encima o el foco dentro; no avanza sola si la persona pidió menos movimiento. En celular y tablet (pantalla táctil) no se
  // mueve sola: se desliza con el dedo (scroll-snap en el CSS). Sin JS, se desliza igual.
  const deals = $("[data-deals]");
  const track = deals && $(".deals-track", deals);
  const mouse = matchMedia("(hover: hover) and (pointer: fine)");
  if (track && mouse.matches && track.children.length > 1) {
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    const ctl = document.createElement("div");
    ctl.className = "deals-ctl";
    const icon = (d) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
    const button = (label, svg) => {
      const b = document.createElement("button");
      Object.assign(b, { type: "button", className: "btn btn-ghost btn-icon", innerHTML: icon(svg) });
      b.setAttribute("aria-label", label);
      return b;
    };
    const prev = button("Ofertas anteriores", '<path d="m15 6-6 6 6 6"/>');
    const next = button("Más ofertas", '<path d="m9 6 6 6-6 6"/>');
    const toggle = button("Pausar", '<path d="M9 6v12M15 6v12"/>');
    ctl.append(prev, next, toggle);
    $(".deals-head", deals).append(ctl);
    deals.classList.add("js");

    let paused = reduced.matches, hover = false, focus = false, timer;
    const running = () => !paused && !hover && !focus && !reduced.matches;
    const step = () => track.children[0].getBoundingClientRect().width + (parseFloat(getComputedStyle(track).columnGap) || 0);
    function go(dir) {
      const end = track.scrollLeft + track.clientWidth >= track.scrollWidth - 4;
      if (dir > 0 && end) track.scrollTo({ left: 0 });  // al final vuelve al principio
      else if (dir < 0 && track.scrollLeft <= 4) track.scrollTo({ left: track.scrollWidth });
      else track.scrollBy({ left: dir * step() });
    }
    function sync() {
      toggle.hidden = reduced.matches;  // sin avance automático no hay nada que pausar
      toggle.setAttribute("aria-label", paused ? "Reanudar" : "Pausar");
      toggle.innerHTML = icon(paused ? '<path d="m8 5 11 7-11 7z"/>' : '<path d="M9 6v12M15 6v12"/>');
      clearInterval(timer);
      if (running()) timer = setInterval(() => go(1), 5000);
    }
    prev.addEventListener("click", () => go(-1));
    next.addEventListener("click", () => go(1));
    toggle.addEventListener("click", () => { paused = !paused; sync(); });
    deals.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") { hover = true; sync(); } });
    deals.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse") { hover = false; sync(); } });
    deals.addEventListener("focusin", () => { focus = true; sync(); });
    deals.addEventListener("focusout", (e) => { if (!deals.contains(e.relatedTarget)) { focus = false; sync(); } });
    reduced.addEventListener("change", () => { paused = reduced.matches; sync(); });
    sync();
  }

  // Filtros: drawer en tablet/móvil.
  const filters = $(".filters"), overlay = $(".overlay");
  let opener = null;
  function closeFilters() {
    if (!filters?.classList.contains("open")) return;
    filters.classList.remove("open"); overlay?.classList.remove("open");
    opener?.setAttribute("aria-expanded", "false"); opener?.focus();
  }
  $$("[data-open-filters]").forEach((b) => b.addEventListener("click", () => {
    opener = b; b.setAttribute("aria-expanded", "true");
    filters.classList.add("open"); overlay.classList.add("open");
    $("[data-close-filters]", filters)?.focus();
  }));
  $$("[data-close-filters]").forEach((b) => b.addEventListener("click", closeFilters));
  overlay?.addEventListener("click", closeFilters);
  $$(".filters input[type=checkbox], .filters select, .toolbar select").forEach((el) => el.addEventListener("change", () => el.form.requestSubmit()));

  // Galería: al tocar una miniatura se cambia la imagen principal.
  document.addEventListener("click", (e) => {
    const t = e.target.closest(".thumb");
    const main = $("#main-img");
    if (!t || !main) return;
    main.classList.remove("loaded");
    main.onload = () => main.classList.add("loaded");
    main.src = t.dataset.full;
    main.alt = t.dataset.alt || "";
    $$(".thumb").forEach((b) => b.removeAttribute("aria-current"));
    t.setAttribute("aria-current", "true");
  });

  // Imágenes: fade-in al cargar. Se cargan desde cada tienda, así que si una está caída o no responde, se prueba la imagen del mismo
  // producto en otra tienda (data-alts). Una tienda que falló se recuerda en la página: sus demás imágenes pasan directo al respaldo y
  // sus miniaturas de la galería se ocultan. Sin respaldo, queda el fondo.
  const dead = new Set();
  const host = (u) => { try { return new URL(u, location.href).host; } catch { return ""; } };
  const WAIT = 6000;  // ms: una tienda que no responde no da error enseguida, el navegador puede esperar mucho más
  const seen = "IntersectionObserver" in window && new IntersectionObserver((es) => es.forEach((en) => {
    if (en.isIntersecting) { seen.unobserve(en.target); en.target._arm(); }  // el plazo corre recién cuando la imagen se está cargando
  }), { rootMargin: "200px" });
  function imgs() {
    $$("img[data-src-fade]").forEach((img) => {
      if (img._watched) return;
      img._watched = true;
      let alts = []; try { alts = JSON.parse(img.dataset.alts || "[]"); } catch {}
      let timer;
      const done = () => { clearTimeout(timer); img.classList.add("loaded"); img.parentElement.classList.add("done"); };
      const fail = () => {
        clearTimeout(timer);
        const h = host(img.src);
        dead.add(h);
        $$(".thumb").forEach((b) => { if (host(b.dataset.full) === h) b.hidden = true; });
        alts = alts.filter((u) => !dead.has(host(u)));
        if (alts.length) { img.src = alts.shift(); img._arm(); }
        else img.parentElement.classList.add("done");
      };
      img._arm = () => {
        if (dead.has(host(img.src))) return fail();
        clearTimeout(timer);
        timer = setTimeout(() => { if (!img.naturalWidth) fail(); }, WAIT);
      };
      img.addEventListener("load", done);
      img.addEventListener("error", fail);
      if (img.complete && img.naturalWidth) done();
      else if (img.complete && img.src) fail();  // ya falló antes de que este script la viera
      else if (seen) seen.observe(img);
      else img._arm();
    });
  }
  imgs();
})();

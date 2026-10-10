(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const form = $("#ask");
  const USDC = ["dorahacks_usdc", "superteam_usdc"];

  function syncPayer() {
    if (!form) return;
    const usdc = USDC.includes($("#payer").value);
    $("#usdc-box").hidden = !usdc;
    $("#rails-box").hidden = usdc;
  }

  async function post(url, body) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({ error: "The server sent something unexpected." }));
    if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  }

  function wire(root) {
    root.querySelectorAll(".confirm").forEach((b) => b.addEventListener("click", async () => {
      const plan = b.closest("[data-plan]").dataset.plan;
      b.disabled = true;
      try {
        await post(`/api/plan/${plan}/confirm`, { line: b.dataset.line });
        b.classList.add("is-done"); b.textContent = "Confirmed"; b.setAttribute("aria-pressed", "true");
      } catch (e) { b.textContent = "Try again"; }
      b.disabled = false;
    }));
    root.querySelectorAll("form.receipt").forEach((f) => f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const btn = f.querySelector("button");
      const fd = new FormData(f);
      btn.disabled = true; btn.textContent = "Reading the trace back…";
      try {
        const data = await post("/api/receipt", { plan_id: f.dataset.plan, landed_amount: fd.get("landed_amount"),
          currency: fd.get("currency"), landed_on: fd.get("landed_on") || null });
        $(`#stamps-${f.dataset.plan}`).insertAdjacentHTML("beforeend", data.html);
        f.reset();
      } catch (e) { alert(e.message); }
      btn.disabled = false; btn.textContent = "Check it";
    }));
  }

  if (form) {
    $("#payer").addEventListener("change", syncPayer);
    syncPayer();
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(form);
      const body = { payer: fd.get("payer"), amount: fd.get("amount"), country: fd.get("country"),
        rails: fd.getAll("rails"), chain: fd.get("chain"), exchange: fd.get("exchange"), question: fd.get("question") };
      const btn = $("#go"), status = $("#status");
      btn.disabled = true; status.className = "hint";
      const steps = ["Checking what the payer offers…", "Checking each option against its own provider's page…",
        "Looking up the tax treaty…", "Fetching the ECB reference rate…", "Computing what lands…",
        "Checking the explanation against the sources…"];
      let i = 0; status.textContent = steps[0];
      const tick = setInterval(() => { i = Math.min(i + 1, steps.length - 1); status.textContent = steps[i]; }, 2200);
      try {
        const data = await post("/api/plan", body);
        const res = $("#result");
        res.innerHTML = data.html;
        wire(res);
        history.replaceState(null, "", `/plan/${data.plan_id}`);
        status.textContent = "Done. Every figure on the plan is footnoted.";
        if (window.matchMedia("(max-width: 900px)").matches) res.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (e) {
        status.textContent = e.message; status.className = "hint err";
      } finally { clearInterval(tick); btn.disabled = false; }
    });
  }
  wire(document);
})();

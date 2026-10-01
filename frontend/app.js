const $ = s => document.querySelector(s);
const STEPS = [{ label: "Slow", f: 1 / 3 }, { label: "Medium", f: 2 / 3 }, { label: "Fast", f: 1 }];
const POLL_MS = 400;

let cfg = null, selected = null, lastState = null, toastTimer = null;

async function api(path, method = "GET") {
    const r = await fetch(path, { method });
    if (!r.ok) {
        let msg = "Something went wrong";
        try { msg = (await r.json()).detail || msg; } catch (_) {}
        throw new Error(msg);
    }
    return r.json();
}

function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2500);
}

async function act(fn) {
    try { await fn(); } catch (e) { toast(e.message); }
    poll(true);
}

const speedFor = f => Math.max(1, Math.round(cfg.max_speed * f));

function btn(text, cls, onclick) {
    const b = document.createElement("button");
    b.textContent = text;
    b.className = cls || "";
    b.onclick = onclick;
    return b;
}

function build() {
    const locos = $("#locos");
    cfg.locos.forEach(id => {
        const b = btn(id, "pick", () => { selected = id; render(); });
        b.dataset.id = id;
        locos.append(b);
    });
    selected = cfg.locos[0] || null;

    STEPS.forEach(s => {
        const b = btn(s.label, "step", () => act(() => api(`/api/loco/${selected}/speed/${speedFor(s.f)}`, "POST")));
        b.dataset.speed = speedFor(s.f);
        $("#speeds").append(b);
    });

    $("#stop").onclick = () => act(() => api(`/api/loco/${selected}/stop`, "POST"));
    document.querySelectorAll(".dir").forEach(b => {
        b.onclick = () => act(() => api(`/api/loco/${selected}/direction/${b.dataset.dir}`, "POST"));
    });

    const sw = $("#switches");
    cfg.switches.forEach(id => {
        const b = btn(id, "sw", () => act(() => api(`/api/switch/${id}/flip`, "POST")));
        b.dataset.id = id;
        sw.append(b);
    });
    $("#switchSection").hidden = cfg.switches.length === 0;

    TrackMap.build($("#map"), cfg, {
        onSwitch: id => act(() => api(`/api/switch/${id}/flip`, "POST")),
        onPick: id => { selected = id; render(); },
    });

    $("#panel").hidden = false;
}

function setStatus(text, kind) {
    const s = $("#status");
    s.textContent = text;
    s.className = "status " + (kind || "");
}

function render() {
    const st = lastState;
    const online = !!st && st.status === "online";
    const loco = st && selected ? st.locomotives[selected] : null;
    const powerOff = online && st.power === false;

    if (!st) setStatus("Can't reach the train system. Ask a staff member for help.", "bad");
    else if (!online) setStatus("The train controller is offline. Ask a staff member for help.", "bad");
    else if (powerOff) setStatus("Track power is off. Ask a staff member to switch it on.", "bad");
    else setStatus("Connected. Pick a speed to start.", "ok");

    const canDrive = online && !powerOff && !!loco;
    document.querySelectorAll("#speeds button, #stop, .dir").forEach(b => b.disabled = !canDrive);
    document.querySelectorAll("#switches button").forEach(b => b.disabled = !online || powerOff);
    $("#estop").disabled = !st;

    document.querySelectorAll(".pick").forEach(b => b.classList.toggle("on", b.dataset.id === selected));
    const speed = loco ? loco.speed : 0;
    document.querySelectorAll(".step").forEach(b =>
        b.classList.toggle("on", speed > 0 && Math.abs(speed - Number(b.dataset.speed)) <= 1));
    document.querySelectorAll(".dir").forEach(b =>
        b.classList.toggle("on", !!loco && loco.direction === b.dataset.dir));

    $("#where").textContent = loco
        ? (speed > 0 ? "Moving" : "Stopped") + (loco.block ? ` · at ${TrackMap.labelFor(loco.block)}` : "")
        : "";

    document.querySelectorAll("#switches button").forEach(b => {
        const sw = st && st.switches[b.dataset.id];
        const label = sw ? (sw.state === "straight" ? "straight" : sw.state === "turnout" ? "diverging" : "unknown") : "";
        b.textContent = `Switch ${b.dataset.id}` + (label ? ` (${label})` : "");
    });

    TrackMap.update(st, selected);
}

let polling = false;
async function poll(now) {
    if (polling && !now) return;
    polling = true;
    try { lastState = await api("/api/state"); } catch (_) { lastState = null; }
    polling = false;
    render();
}

async function start() {
    while (!cfg) {
        try { cfg = await api("/api/allowed"); }
        catch (_) { setStatus("Can't reach the train system. Retrying…", "bad"); await new Promise(r => setTimeout(r, 1500)); }
    }
    build();
    $("#estop").onclick = () => act(async () => { await api("/api/estop", "POST"); toast("All trains stopped"); });
    await poll(true);
    setInterval(poll, POLL_MS);
}
start();
/* Simplified track map. A hand-drawn schematic keyed by Rocrail ids, not the
   real track grid. To support a different layout, edit only the SCHEMATIC block.
   API: TrackMap.build(svg, cfg, {onSwitch(id), onPick(id)}); TrackMap.update(state, selectedLoco) */
const TrackMap = (() => {
    const NS = "http://www.w3.org/2000/svg";
    const ROWS = [62, 122, 182, 242];

    // ---------- SCHEMATIC (edit this for another layout) ----------
    const STATIONS = [
        ...ROWS.map((cy, i) => ({ id: "sb" + (i + 1), label: "Staging " + (i + 1), x: 40, y: cy - 20, w: 150, h: 40 })),
        { id: "cb1", label: "Central Station 1", x: 600, y: 85, w: 170, h: 40 },
        { id: "cb2", label: "Central Station 2", x: 600, y: 155, w: 170, h: 40 },
        { id: "cb3", label: "Loop A", x: 340, y: 360, w: 110, h: 40 },
        { id: "cb4", label: "Loop B", x: 180, y: 360, w: 110, h: 40 },
    ];
    const LINES = [
        [[20, 242], [20, 14], [520, 14], [520, 380], [450, 380]],   // trains leaving staging
        [[520, 300], [215, 300], [215, 62]],                         // trains coming back
        [[520, 105], [600, 105]], [[520, 175], [600, 175]],         // into Central Station
        [[340, 380], [290, 380]], [[180, 380], [150, 380], [150, 300], [215, 300]],  // loop
        ...ROWS.map(y => [[40, y], [20, y]]),
        ...ROWS.map(y => [[190, y], [215, y]]),
    ];
    // Approximate spots; a switch only appears if visitors are allowed to use it.
    const SWITCH_SPOTS = {
        sw4: [20, 92], sw5: [20, 152], sw6: [20, 212],
        sw3: [215, 92], sw2: [215, 152], sw1: [215, 212],
        sw7: [520, 60], sw8: [520, 140], sw11: [520, 220], sw10: [520, 260], sw9: [520, 340],
    };
    const signalFor = id => id + "s";   // plan.xml convention: block "sb1" has signal "sb1s"
    // --------------------------------------------------------------

    let svg, cfg, handlers, trainLayer;
    const stationEls = {}, signalEls = {}, switchEls = {};

    function el(name, attrs, parent, text) {
        const e = document.createElementNS(NS, name);
        for (const k in attrs) e.setAttribute(k, attrs[k]);
        if (text !== undefined) e.textContent = text;
        if (parent) parent.append(e);
        return e;
    }

    function build(svgEl, config, h) {
        svg = svgEl; cfg = config; handlers = h;
        svg.setAttribute("viewBox", "0 0 800 440");
        svg.replaceChildren();

        const lines = el("g", {}, svg);
        LINES.forEach(pts => el("polyline", { class: "rail", points: pts.map(p => p.join(",")).join(" ") }, lines));

        STATIONS.forEach(s => {
            const g = el("g", {}, svg);
            stationEls[s.id] = el("rect", { class: "station", x: s.x, y: s.y, width: s.w, height: s.h, rx: 12 }, g);
            el("text", { class: "slabel", x: s.x + 4, y: s.y - 6 }, g, s.label);
            signalEls[s.id] = el("circle", { class: "signal", cx: s.x + s.w - 14, cy: s.y + s.h / 2, r: 7 }, g);
        });

        cfg.switches.forEach(id => {
            const spot = SWITCH_SPOTS[id];
            if (!spot) return;
            const g = el("g", {
                class: "swspot", tabindex: 0, role: "button", "aria-label": "Switch " + id,
                transform: `translate(${spot[0]},${spot[1]})`
            }, svg);
            const flip = () => handlers.onSwitch(id);
            g.addEventListener("click", flip);
            g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } });
            el("circle", { r: 15 }, g);
            el("text", { class: "swid", y: 5 }, g, id.replace(/\D/g, ""));
            switchEls[id] = el("text", { class: "swstate", y: 30 }, g, "");
        });

        trainLayer = el("g", {}, svg);
    }

    function update(st, selected) {
        if (!svg) return;
        const online = !!st && st.status === "online";
        svg.classList.toggle("offline", !online);
        const blocks = (st && st.blocks) || {}, locos = (st && st.locomotives) || {};

        const where = {};
        cfg.locos.forEach(id => {
            const b = (locos[id] && locos[id].block) || Object.keys(blocks).find(k => blocks[k].loco === id) || "";
            if (b) (where[b] = where[b] || []).push(id);
        });

        STATIONS.forEach(s => {
            stationEls[s.id].classList.toggle("busy", !!where[s.id]);
            const sg = st && st.signals && st.signals[signalFor(s.id)];
            signalEls[s.id].setAttribute("class", "signal " + (sg ? (sg.state === "green" ? "go" : "stop") : "none"));
        });

        for (const id in switchEls) {
            const sw = st && st.switches && st.switches[id];
            const diverging = sw && sw.state === "turnout";
            switchEls[id].textContent = sw ? (diverging ? "diverging" : sw.state === "straight" ? "straight" : "") : "";
            switchEls[id].parentNode.classList.toggle("diverging", !!diverging);
        }

        trainLayer.replaceChildren();
        STATIONS.forEach(s => {
            const here = where[s.id] || [];
            const tw = Math.min(110, (s.w - 36) / Math.max(here.length, 1));
            here.forEach((id, i) => {
                const moving = locos[id] && locos[id].speed > 0;
                const g = el("g", {
                    class: "train" + (id === selected ? " sel" : ""), role: "button",
                    "aria-label": "Train " + id
                }, trainLayer);
                g.addEventListener("click", () => handlers.onPick(id));
                el("rect", { x: s.x + 6 + i * (tw + 4), y: s.y + 6, width: tw, height: s.h - 12, rx: 8 }, g);
                el("text", { x: s.x + 6 + i * (tw + 4) + tw / 2, y: s.y + s.h / 2 + 5 }, g,
                    (moving ? "\u25B6 " : "") + id);
            });
        });
    }

    function labelFor(id) {
        const s = STATIONS.find(s => s.id === id);
        return s ? s.label : id;
    }

    return { build, update, labelFor };
})();
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Flag,
  Gauge,
  RefreshCw,
  ShieldCheck,
  Timer,
  Trophy
} from "lucide-react";

const DATA_BASE =
  process.env.NEXT_PUBLIC_F1_DATA_BASE_URL ||
  "https://raw.githubusercontent.com/ShreyTriesToCode/f1-race-intel/main";

const OFFICIAL_LINKS = {
  timing: "https://www.formula1.com/en/timing/f1-live",
  schedule: "https://www.formula1.com/en/racing/2026",
  f1tv: "https://www.formula1.com/en/subscribe-to-f1-tv"
};

const F1_IMG = "https://media.formula1.com/image/upload";

const DRIVER_IMAGES = {
  "lando norris": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mclaren/lannor01/2026mclarenlannor01right.webp`,
  "oscar piastri": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mclaren/oscpia01/2026mclarenoscpia01right.webp`,
  "max verstappen": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/redbullracing/maxver01/2026redbullracingmaxver01right.webp`,
  "charles leclerc": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/ferrari/chalec01/2026ferrarichalec01right.webp`,
  "lewis hamilton": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/ferrari/lewham01/2026ferrarilewham01right.webp`,
  "george russell": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/georus01/2026mercedesgeorus01right.webp`,
  "kimi antonelli": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp`,
  "andrea kimi antonelli": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp`,
  "fernando alonso": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/astonmartin/feralo01/2026astonmartinferalo01right.webp`,
  "carlos sainz": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/carsai01/2026williamscarsai01right.webp`,
  "alex albon": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/alealb01/2026williamsalealb01right.webp`,
  "alexander albon": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/alealb01/2026williamsalealb01right.webp`,
  "nico hulkenberg": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/nichul01/2026audinichul01right.webp`,
  "nico hülkenberg": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/nichul01/2026audinichul01right.webp`,
  "gabriel bortoleto": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/gabbor01/2026audigabbor01right.webp`,
  "sergio perez": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/serper01/2026cadillacserper01right.webp`,
  "sergio pérez": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/serper01/2026cadillacserper01right.webp`,
  "valtteri bottas": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/valbot01/2026cadillacvalbot01right.webp`
};

const TEAM_CARS = {
  "mclaren": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/mclaren/2026mclarencarright.webp`,
  "ferrari": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/ferrari/2026ferraricarright.webp`,
  "mercedes": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/mercedes/2026mercedescarright.webp`,
  "red bull racing": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/redbullracing/2026redbullracingcarright.webp`,
  "red bull": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/redbullracing/2026redbullracingcarright.webp`,
  "williams": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/williams/2026williamscarright.webp`,
  "aston martin": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/astonmartin/2026astonmartincarright.webp`,
  "audi": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/audi/2026audicarright.webp`,
  "kick sauber": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/audi/2026audicarright.webp`,
  "cadillac": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/cadillac/2026cadillaccarright.webp`
};

function key(value) {
  return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();
}
function cleanTitle(title) {
  return String(title || "F1 Race Intel")
    .replace(/^F1 Briefing:\s*/i, "")
    .replace(/^F1 Weekend Briefing:\s*/i, "")
    .replace(/\s*Grand Prix$/i, "");
}
function initials(name) {
  return String(name || "?").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}
function driverImage(driver) {
  return driver?.image || DRIVER_IMAGES[key(driver?.name || driver)] || "";
}
function teamCar(team) {
  return TEAM_CARS[key(team)] || "";
}
function esc(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}
function inline(text) {
  return esc(text).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/`(.*?)`/g, "<code>$1</code>");
}
function mdToHtml(md) {
  const lines = String(md || "").split("\n");
  let html = "";
  let list = null;
  const close = () => {
    if (list) html += `</${list}>`;
    list = null;
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      close();
      continue;
    }
    if (line.startsWith("# ")) {
      close();
      html += `<h1>${inline(line.slice(2))}</h1>`;
    } else if (line.startsWith("## ")) {
      close();
      html += `<h2>${inline(line.slice(3))}</h2>`;
    } else if (line.startsWith("- ")) {
      if (list !== "ul") {
        close();
        html += "<ul>";
        list = "ul";
      }
      html += `<li>${inline(line.slice(2))}</li>`;
    } else if (/^\d+\.\s/.test(line)) {
      if (list !== "ol") {
        close();
        html += "<ol>";
        list = "ol";
      }
      html += `<li>${inline(line.replace(/^\d+\.\s/, ""))}</li>`;
    } else if (line.startsWith("---")) {
      close();
      html += "<hr>";
    } else {
      close();
      html += `<p>${inline(line)}</p>`;
    }
  }
  close();
  return html;
}
function level(value) {
  const t = String(value || "").toLowerCase();
  if (t.includes("high")) return 82;
  if (t.includes("medium-high")) return 74;
  if (t.includes("medium-good")) return 68;
  if (t.includes("medium")) return 54;
  if (t.includes("low-medium")) return 38;
  if (t.includes("low")) return 26;
  return 50;
}
function parseBriefingTop10(md) {
  const matches = String(md || "").matchAll(/^\d+\.\s+([^,\n]+)(?:,\s*(.*))?$/gm);
  return Array.from(matches).slice(0, 10).map((match) => ({
    name: match[1]?.trim(),
    reason: match[2]?.trim() || "Model estimate"
  }));
}
function formatTime(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "Start unavailable";
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function Countdown({ startIso }) {
  const [time, setTime] = useState({ d: "--", h: "--", m: "--" });
  useEffect(() => {
    const target = new Date(startIso || "");
    if (Number.isNaN(target.getTime())) return;
    const tick = () => {
      const diff = target - Date.now();
      if (diff <= 0) return setTime({ d: "00", h: "00", m: "00" });
      const seconds = Math.floor(diff / 1000);
      setTime({
        d: String(Math.floor(seconds / 86400)).padStart(2, "0"),
        h: String(Math.floor((seconds % 86400) / 3600)).padStart(2, "0"),
        m: String(Math.floor((seconds % 3600) / 60)).padStart(2, "0")
      });
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => clearInterval(id);
  }, [startIso]);

  return (
    <div className="countdown">
      <div><strong>{time.d}</strong><span>Days</span></div>
      <div><strong>{time.h}</strong><span>Hours</span></div>
      <div><strong>{time.m}</strong><span>Minutes</span></div>
    </div>
  );
}

function DriverArt({ driver }) {
  const [failed, setFailed] = useState(false);
  const src = driverImage(driver);
  if (!src || failed) return <div className="driver-fallback">{initials(driver?.name)}</div>;
  return <img src={src} alt={driver?.name || "Driver"} onError={() => setFailed(true)} />;
}

function TeamCar({ team }) {
  const [failed, setFailed] = useState(false);
  const src = teamCar(team);
  if (!src || failed) return <span className="team-fallback">{initials(team)}</span>;
  return <img className="team-car" src={src} alt={`${team} car`} onError={() => setFailed(true)} />;
}

function TargetTabs({ targets, activeIndex, setActiveIndex }) {
  if (!targets.length) return null;
  return (
    <div className="target-tabs">
      {targets.map((target, index) => (
        <button
          key={`${target.target_type}-${target.event?.title || index}`}
          className={activeIndex === index ? "active" : ""}
          onClick={() => setActiveIndex(index)}
        >
          <span>{String(target.target_type || "target").toUpperCase()}</span>
          <strong>{target.event?.title || target.title || "F1 target"}</strong>
        </button>
      ))}
    </div>
  );
}

function PredictionList({ predictions }) {
  const list = predictions?.length ? predictions.slice(0, 10) : [{ name: "No prediction yet", reason: "Run the workflow once." }];
  return (
    <div className="prediction-list">
      {list.map((driver, index) => (
        <article className={`prediction-card ${index === 0 ? "leader" : ""}`} key={`${driver.driver_id || driver.name}-${index}`}>
          <div className="rank">{index + 1}</div>
          <div className="prediction-copy">
            <strong>{driver.name}</strong>
            <span>{driver.team || "Team pending"}</span>
            <p>{driver.reason || "Model estimate"}</p>
            <div className="chips tight">
              {driver.score !== undefined && <small>Score {driver.score}</small>}
              {driver.confidence !== undefined && <small>{driver.confidence}% confidence</small>}
            </div>
          </div>
          <div className="driver-art"><DriverArt driver={driver} /></div>
        </article>
      ))}
    </div>
  );
}

export default function Home() {
  const [indexData, setIndexData] = useState([]);
  const [active, setActive] = useState(null);
  const [debug, setDebug] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [status, setStatus] = useState("Waiting for data");
  const [copied, setCopied] = useState(false);
  const [targetIndex, setTargetIndex] = useState(0);

  async function loadDebug() {
    try {
      const res = await fetch(`${DATA_BASE}/data_cache/latest-model-debug.json?v=${Date.now()}`);
      if (res.ok) setDebug(await res.json());
    } catch {
      setDebug(null);
    }
  }

  async function loadBriefing(item) {
    setStatus("Loading briefing");
    setActive(item);
    const res = await fetch(`${DATA_BASE}/${item.path}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`briefing HTTP ${res.status}`);
    setMarkdown(await res.text());
    setTargetIndex(0);
    setStatus("Ready");
  }

  async function loadIndex() {
    setStatus("Syncing");
    const res = await fetch(`${DATA_BASE}/briefings/index.json?v=${Date.now()}`);
    if (!res.ok) throw new Error(`index HTTP ${res.status}`);
    const data = await res.json();
    const list = Array.isArray(data) ? data : data.briefings || [];
    list.sort((a, b) => String(b.generated_iso || b.generated || b.start || "").localeCompare(String(a.generated_iso || a.generated || a.start || "")));
    setIndexData(list);
    await loadDebug();
    if (list[0]) await loadBriefing(list[0]);
    else setStatus("No briefings");
  }

  useEffect(() => {
    loadIndex().catch((error) => {
      console.error(error);
      setStatus("No data");
    });
  }, []);

  const targets = useMemo(() => {
    const payloads = Array.isArray(debug?.payloads) ? debug.payloads.filter((p) => p?.ok !== false) : [];
    if (payloads.length) return payloads;
    if (!active) return [];
    return [{
      event: { title: active.event_title || active.title, start: active.start_iso || active.start },
      target_type: active.prediction_model?.output_target_type || "race",
      top10: active.top10 || [],
      profile: active,
      weather: active.weather || {},
      team_fit: active.team_fit || [],
      prediction_model: active.prediction_model || {}
    }];
  }, [debug, active]);

  const selectedTarget = targets[targetIndex] || targets[0] || {};
  const profile = selectedTarget.profile || active || {};
  const weather = selectedTarget.weather || active?.weather || {};
  const model = selectedTarget.prediction_model || active?.prediction_model || {};
  const predictions = selectedTarget.top10?.length ? selectedTarget.top10 : active?.top10?.length ? active.top10 : parseBriefingTop10(markdown);
  const topDriver = predictions[0] || {};
  const title = cleanTitle(active?.title || selectedTarget?.event?.title || "Race Intel");
  const html = useMemo(() => mdToHtml(markdown), [markdown]);
  const car = teamCar(topDriver.team);
  const canCopy = Boolean(markdown);

  async function copyBriefing() {
    if (!canCopy) return;
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  }

  return (
    <main className="app">
      <nav className="nav">
        <div className="brand">
          <div className="brand-mark">F1</div>
          <div>
            <strong>Race Intel</strong>
            <span>Sprint and Race predictions</span>
          </div>
        </div>
        <div className="nav-actions">
          <a href="/live"><Timer size={15} /> Live page</a>
          <a href={OFFICIAL_LINKS.timing} target="_blank" rel="noreferrer"><Timer size={15} /> F1 timing</a>
          <a href={OFFICIAL_LINKS.schedule} target="_blank" rel="noreferrer"><CalendarDays size={15} /> Calendar</a>
          <button onClick={() => loadIndex().catch(() => setStatus("Refresh failed"))}><RefreshCw size={15} /> Refresh</button>
        </div>
        <div className="status"><i /><span>{status}</span></div>
      </nav>

      <section className="hero">
        <article className="hero-panel">
          {car && <img className="hero-car" src={car} alt="" />}
          <div className="hero-content">
            <div className="chips">
              <span>Weekend mode ready</span>
              <span>{model.prediction_stage_label || "Model active"}</span>
              <span>{model.output_target_type || "Sprint/Race"}</span>
            </div>
            <h1>{title}</h1>
            <p>
              Clean view of the next Sprint and Race predictions. Qualifying, practice, weather, upgrades,
              track traits, current-season car form, and historical data remain inputs.
            </p>
          </div>
          <div className="hero-stats">
            <div><span>Circuit</span><strong>{profile.circuit || active?.circuit || "-"}</strong></div>
            <div><span>Target</span><strong>{String(selectedTarget.target_type || model.output_target_type || "Race").toUpperCase()}</strong></div>
            <div><span>Generated</span><strong>{active?.generated || "-"}</strong></div>
          </div>
        </article>

        <aside className="side-card">
          <div className="section-head">
            <h2>Next target</h2>
            <Clock size={18} />
          </div>
          <p className="muted">{selectedTarget.event?.title || active?.event_title || "No target loaded"}</p>
          <strong className="time">{formatTime(selectedTarget.event?.start || active?.start_iso || active?.start)}</strong>
          <Countdown startIso={selectedTarget.event?.start || active?.start_iso} />
        </aside>
      </section>

      <TargetTabs targets={targets} activeIndex={targetIndex} setActiveIndex={setTargetIndex} />

      <section className="layout">
        <article className="card prediction-section">
          <div className="section-head">
            <h2>Prediction</h2>
            <Trophy size={18} />
          </div>
          <PredictionList predictions={predictions} />
        </article>

        <aside className="stack">
          <article className="card">
            <div className="section-head"><h2>Track</h2><Gauge size={18} /></div>
            <div className="fact"><span>Car trait</span><strong>{profile.car_trait || active?.car_trait || "-"}</strong></div>
            <div className="fact"><span>Speed profile</span><strong>{profile.speed_profile || active?.speed_profile || "-"}</strong></div>
            <div className="fact"><span>Overtaking</span><strong>{profile.overtaking || active?.overtaking || "-"}</strong></div>
            <div className="bar"><i style={{ "--value": `${level(profile.overtaking || active?.overtaking)}%` }} /></div>
            <div className="fact"><span>Tyre stress</span><strong>{profile.tyre_stress || active?.tyre_stress || "-"}</strong></div>
            <div className="bar"><i style={{ "--value": `${level(profile.tyre_stress || active?.tyre_stress)}%` }} /></div>
          </article>

          <article className="card">
            <div className="section-head"><h2>Weather</h2><Flag size={18} /></div>
            <div className="mini-grid">
              <div><span>Temp</span><strong>{weather.temperature || "-"}</strong></div>
              <div><span>Rain</span><strong>{weather.rain || "-"}</strong></div>
              <div><span>Wind</span><strong>{weather.wind || "-"}</strong></div>
              <div><span>Source</span><strong>{weather.source || "Open-Meteo"}</strong></div>
            </div>
            <p className="note">{weather.impact || "Weather impact appears after the next run."}</p>
          </article>

          <article className="card">
            <div className="section-head"><h2>Strategy</h2><ShieldCheck size={18} /></div>
            <div className="fact"><span>Baseline</span><strong>{profile.strategy_bias || active?.strategy_bias || "-"}</strong></div>
            <div className="fact"><span>Pit window</span><strong>{profile.pit_window || active?.pit_window || "-"}</strong></div>
            <p className="note">Main risk: tyre drop-off, safety-car timing, traffic after pit stop, and weather crossover.</p>
          </article>
        </aside>
      </section>

      <section className="layout small">
        <article className="card">
          <div className="section-head"><h2>Team fit</h2><CheckCircle2 size={18} /></div>
          <div className="team-list">
            {(selectedTarget.team_fit || active?.team_fit || []).slice(0, 5).map((team, index) => (
              <div className="team" key={`${team}-${index}`}>
                <TeamCar team={team} />
                <div><strong>{index + 1}. {team}</strong><span>Track-fit and form estimate</span></div>
              </div>
            ))}
          </div>
        </article>

        <article className="card">
          <div className="section-head"><h2>Data status</h2><ExternalLink size={18} /></div>
          <div className="fact"><span>Output mode</span><strong>{debug?.output_mode || "Latest"}</strong></div>
          <div className="fact"><span>Backfill used</span><strong>{debug?.backfill?.used ?? "-"}</strong></div>
          <div className="fact"><span>ML model</span><strong>{model.ml_model_loaded ? "Loaded" : "Fallback"}</strong></div>
          <div className="fact"><span>OpenF1</span><strong>{model.available_components?.openf1_provider_status || "Fallback if unavailable"}</strong></div>
        </article>

        <article className="card">
          <div className="section-head"><h2>Archive</h2><CalendarDays size={18} /></div>
          <div className="archive-list">
            {indexData.slice(0, 8).map((item) => (
              <button className={active?.path === item.path ? "active" : ""} key={item.path} onClick={() => loadBriefing(item)}>
                <strong>{item.title}</strong>
                <span>{item.generated || item.start || item.path}</span>
              </button>
            ))}
          </div>
        </article>
      </section>

      <section className="card briefing">
        <div className="section-head">
          <h2>Briefing text</h2>
          <button className="copy" onClick={copyBriefing}><Copy size={15} /> {copied ? "Copied" : "Copy"}</button>
        </div>
        <div className="briefing-text" dangerouslySetInnerHTML={{ __html: html || "<p>No briefing loaded.</p>" }} />
      </section>

      <footer>
        Race Intel uses generated GitHub Actions data and links to official viewing/timing sources. It does not stream race video.
      </footer>
    </main>
  );
}

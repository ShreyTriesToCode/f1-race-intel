"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Eye,
  Flag,
  Gauge,
  PlayCircle,
  Radio,
  RefreshCw,
  ShieldAlert,
  Timer,
  Trophy,
  Video
} from "lucide-react";

const DATA_BASE =
  process.env.NEXT_PUBLIC_F1_DATA_BASE_URL ||
  "https://raw.githubusercontent.com/ShreyTriesToCode/f1-briefing-bot/main";

const OFFICIAL_LINKS = {
  f1tv: "https://www.formula1.com/en/subscribe-to-f1-tv",
  liveTiming: "https://www.formula1.com/en/timing/f1-live",
  schedule: "https://www.formula1.com/en/racing/2026"
};

const F1_IMG = "https://media.formula1.com/image/upload";

const OFFICIAL_DRIVER_IMAGES = {
  "george russell": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/georus01/2026mercedesgeorus01right.webp`,
  "kimi antonelli": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp`,
  "andrea kimi antonelli": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mercedes/andant01/2026mercedesandant01right.webp`,
  "charles leclerc": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/ferrari/chalec01/2026ferrarichalec01right.webp`,
  "lewis hamilton": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/ferrari/lewham01/2026ferrarilewham01right.webp`,
  "lando norris": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mclaren/lannor01/2026mclarenlannor01right.webp`,
  "oscar piastri": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/mclaren/oscpia01/2026mclarenoscpia01right.webp`,
  "max verstappen": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/redbullracing/maxver01/2026redbullracingmaxver01right.webp`,
  "isack hadjar": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/redbullracing/isahad01/2026redbullracingisahad01right.webp`,
  "esteban ocon": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/haas/estoco01/2026haasestoco01right.webp`,
  "oliver bearman": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/haas/olibea01/2026haasolibea01right.webp`,
  "pierre gasly": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/alpine/piegas01/2026alpinepiegas01right.webp`,
  "franco colapinto": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/alpine/fracol01/2026alpinefracol01right.webp`,
  "liam lawson": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/racingbulls/lialaw01/2026racingbullslialaw01right.webp`,
  "arvid lindblad": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/racingbulls/arvlin01/2026racingbullsarvlin01right.webp`,
  "nico hulkenberg": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/nichul01/2026audinichul01right.webp`,
  "nico hülkenberg": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/nichul01/2026audinichul01right.webp`,
  "gabriel bortoleto": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/audi/gabbor01/2026audigabbor01right.webp`,
  "carlos sainz": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/carsai01/2026williamscarsai01right.webp`,
  "alexander albon": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/alealb01/2026williamsalealb01right.webp`,
  "alex albon": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/williams/alealb01/2026williamsalealb01right.webp`,
  "sergio perez": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/serper01/2026cadillacserper01right.webp`,
  "sergio pérez": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/serper01/2026cadillacserper01right.webp`,
  "valtteri bottas": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/cadillac/valbot01/2026cadillacvalbot01right.webp`,
  "fernando alonso": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/astonmartin/feralo01/2026astonmartinferalo01right.webp`,
  "lance stroll": `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/2026/astonmartin/lanstr01/2026astonmartinlanstr01right.webp`
};

const OFFICIAL_TEAM_CARS = {
  "mercedes": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/mercedes/2026mercedescarright.webp`,
  "ferrari": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/ferrari/2026ferraricarright.webp`,
  "mclaren": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/mclaren/2026mclarencarright.webp`,
  "red bull racing": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/redbullracing/2026redbullracingcarright.webp`,
  "red bull": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/redbullracing/2026redbullracingcarright.webp`,
  "haas": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/haas/2026haascarright.webp`,
  "haas f1 team": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/haas/2026haascarright.webp`,
  "alpine": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/alpine/2026alpinecarright.webp`,
  "racing bulls": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/racingbulls/2026racingbullscarright.webp`,
  "audi": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/audi/2026audicarright.webp`,
  "kick sauber": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/audi/2026audicarright.webp`,
  "williams": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/williams/2026williamscarright.webp`,
  "cadillac": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/cadillac/2026cadillaccarright.webp`,
  "aston martin": `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/2026/astonmartin/2026astonmartincarright.webp`
};

const SCENARIOS = {
  baseline: { label: "Baseline", note: "Uses the generated ensemble output without manual bias.", pit: "Follow the generated pit window.", weights: {} },
  rain: { label: "Rain risk", note: "Boosts reliability, weather adaptation, and strategy execution.", pit: "Delay fixed dry stops. React to crossover timing.", weights: { weather_adaptation: 8, reliability: 6, team_strategy: 5, qualifying: -3 } },
  safetyCar: { label: "Safety car", note: "Boosts pit execution and strategy swing potential.", pit: "Pit under SC or VSC if tyre age is close to window.", weights: { pit_execution: 8, team_strategy: 7, reliability: 3 } },
  highDeg: { label: "High degradation", note: "Boosts race pace, tyre handling, pit execution, and consistency.", pit: "Two-stop risk rises. Avoid extending a dead tyre.", weights: { race_pace: 7, pit_execution: 6, reliability: 4, circuit_history: 3 } },
  lowOvertake: { label: "Low overtaking", note: "Boosts qualifying, pit execution, and track position.", pit: "Undercut becomes stronger. Avoid traffic.", weights: { qualifying: 9, pit_execution: 5, circuit_history: 4, team_strategy: 4 } }
};

function normalizeKey(value) {
  return String(value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();
}
function initials(name) {
  return String(name || "?").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}
function driverImage(driver) {
  const key = normalizeKey(driver?.name || driver);
  return driver?.image || OFFICIAL_DRIVER_IMAGES[key] || "";
}
function teamCar(team) {
  const key = normalizeKey(team);
  return OFFICIAL_TEAM_CARS[key] || "";
}
function teamColor(team) {
  return {
    "mclaren": "#ff8000", "ferrari": "#e10600", "mercedes": "#00d2be",
    "red bull racing": "#3671c6", "red bull": "#3671c6", "williams": "#64c4ff",
    "aston martin": "#229971", "alpine": "#2293d1", "haas": "#b6babd",
    "haas f1 team": "#b6babd", "racing bulls": "#6692ff", "audi": "#d21f3c",
    "kick sauber": "#d21f3c", "cadillac": "#c9a646"
  }[normalizeKey(team)] || "#e10600";
}
function cleanTitle(title) {
  return String(title || "F1 Briefing").replace(/^F1 Briefing:\s*/i, "").replace(/\s*-\s*Race$/i, "");
}
function numeric(value) {
  const match = String(value ?? "").match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : null;
}
function level(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("very low")) return 18;
  if (text.includes("low-medium")) return 34;
  if (text.includes("low")) return 26;
  if (text.includes("medium-good")) return 66;
  if (text.includes("medium-high")) return 76;
  if (text.includes("medium")) return 54;
  if (text.includes("good") || text.includes("high")) return 82;
  return 50;
}
function speedLevel(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("straight")) return 88;
  if (text.includes("aero")) return 76;
  if (text.includes("traction")) return 58;
  return 50;
}
function inline(text) {
  return String(text || "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/`(.*?)`/g, "<code>$1</code>");
}
function mdToHtml(md) {
  const lines = String(md || "").split("\n");
  let html = "";
  let list = null;
  const close = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const clean = raw.trim();
    if (!clean) { close(); continue; }
    if (clean.startsWith("# ")) { close(); html += `<h1>${inline(clean.slice(2))}</h1>`; }
    else if (clean.startsWith("## ")) { close(); html += `<h2>${inline(clean.slice(3))}</h2>`; }
    else if (clean.startsWith("- ")) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(clean.slice(2))}</li>`; }
    else if (/^\d+\.\s/.test(clean)) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(clean.replace(/^\d+\.\s/, ""))}</li>`; }
    else if (clean.startsWith("---")) { close(); html += "<hr>"; }
    else { close(); html += `<p>${inline(clean)}</p>`; }
  }
  close();
  return html;
}

function Countdown({ startIso }) {
  const [time, setTime] = useState({ d: "--", h: "--", m: "--", s: "--" });
  useEffect(() => {
    const target = new Date(startIso || "");
    if (Number.isNaN(target.getTime())) return;
    const tick = () => {
      const diff = target - Date.now();
      if (diff <= 0) return setTime({ d: "00", h: "00", m: "00", s: "00" });
      const seconds = Math.floor(diff / 1000);
      setTime({
        d: String(Math.floor(seconds / 86400)).padStart(2, "0"),
        h: String(Math.floor((seconds % 86400) / 3600)).padStart(2, "0"),
        m: String(Math.floor((seconds % 3600) / 60)).padStart(2, "0"),
        s: String(seconds % 60).padStart(2, "0")
      });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startIso]);

  return (
    <div className="countdown">
      <div className="timebox"><strong>{time.d}</strong><span>Days</span></div>
      <div className="timebox"><strong>{time.h}</strong><span>Hours</span></div>
      <div className="timebox"><strong>{time.m}</strong><span>Min</span></div>
      <div className="timebox"><strong>{time.s}</strong><span>Sec</span></div>
    </div>
  );
}

function DriverImage({ driver }) {
  const [failed, setFailed] = useState(false);
  const src = driverImage(driver);
  if (!src || failed) return <div className="fallback-driver">{initials(driver?.name)}</div>;
  return <img className="driver-img" src={src} alt={driver?.name || "F1 driver"} onError={() => setFailed(true)} />;
}

function TeamCar({ team }) {
  const [failed, setFailed] = useState(false);
  const src = teamCar(team);
  if (!src || failed) return <span className="team-fallback">{initials(team)}</span>;
  return <img className="team-car" src={src} alt={`${team} car`} onError={() => setFailed(true)} />;
}

function DriverCard({ driver, index, onOpen }) {
  const color = teamColor(driver.team);
  return (
    <article className={`driver-card ${index === 0 ? "featured" : ""}`} style={{ borderColor: `${color}88` }} onClick={() => onOpen(driver)}>
      <div className="driver-content">
        <span className="driver-rank" style={{ background: color }}>{index + 1}</span>
        <strong className="driver-name">{driver.name || "Unknown Driver"}</strong>
        <span className="driver-reason">{driver.reason || "Dynamic prediction"}</span>
        <span className="driver-team">
          {driver.team || "Team pending"}
          {driver.score !== undefined && <span className="score-pill">Score {driver.score}</span>}
          {driver.confidence !== undefined && <span>{driver.confidence}% confidence</span>}
        </span>
      </div>
      <div className="driver-media"><DriverImage driver={driver} /></div>
    </article>
  );
}

function DetailModal({ driver, onClose }) {
  if (!driver) return null;
  const rows = Object.entries(driver.component_scores || {}).filter(([, v]) => v !== null && v !== undefined);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{driver.name}</h3>
            <p className="mini">{driver.team} · Score {driver.score} · Confidence {driver.confidence}%</p>
          </div>
          <button className="close-btn" onClick={onClose}>Close</button>
        </div>
        <p className="impact">{driver.reason}</p>
        <div className="debug-table">
          {rows.map(([key, value]) => (
            <div className="debug-row" key={key}>
              <span>{key.replaceAll("_", " ")}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StrategySimulator({ active, onChange, top10 }) {
  const scenario = SCENARIOS[active];
  const adjusted = useMemo(() => {
    return (top10 || []).map((driver) => {
      let delta = 0;
      const comps = driver.component_scores || {};
      for (const [key, bias] of Object.entries(scenario.weights || {})) {
        const value = comps[key];
        if (typeof value === "number") delta += (value / 100) * bias;
      }
      return { ...driver, simScore: Math.round((Number(driver.score || 0) + delta) * 10) / 10 };
    }).sort((a, b) => b.simScore - a.simScore).slice(0, 5);
  }, [active, top10, scenario]);

  return (
    <article className="card simulator" id="simulator">
      <div className="section-title">
        <h3>Strategy Simulator</h3>
        <span className="mini">Scenario model</span>
      </div>
      <div className="scenario-tabs">
        {Object.entries(SCENARIOS).map(([key, item]) => (
          <button className={`ghost-btn ${active === key ? "active" : ""}`} key={key} onClick={() => onChange(key)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="impact">{scenario.note}<br />Pit idea: {scenario.pit}</div>
      <ul className="list" style={{ marginTop: 14 }}>
        {adjusted.map((driver, index) => (
          <li className="row" key={driver.driver_id || driver.name}>
            <span>{index + 1}. {driver.name}</span>
            <strong>{driver.simScore}</strong>
          </li>
        ))}
      </ul>
    </article>
  );
}

function LiveHub({ top10 }) {
  const rows = (top10 || []).slice(0, 10).map((driver, index) => ({
    pos: index + 1,
    driver: driver.name,
    team: driver.team,
    gap: index === 0 ? "Leader" : `+${(index * 2.4 + 0.8).toFixed(1)}s`,
    tyre: index % 3 === 0 ? "M" : index % 3 === 1 ? "H" : "S"
  }));

  return (
    <article className="card live" id="live">
      <div className="section-title">
        <h3>Live Race Hub</h3>
        <span className="mini">Legal timing-style dashboard, no pirate video</span>
      </div>
      <div className="live-board">
        <div>
          <div className="live-row header">
            <span>POS</span><span>Driver</span><span>Team</span><span className="hide-mobile">Gap</span><span className="hide-mobile">Tyre</span>
          </div>
          <div className="timing-table">
            {rows.map((row) => (
              <div className="live-row" key={row.driver}>
                <span className="rank-badge">{row.pos}</span>
                <strong>{row.driver}</strong>
                <span>{row.team || "-"}</span>
                <span className="hide-mobile">{row.gap}</span>
                <span className="hide-mobile">{row.tyre}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="race-control">
          <div className="rc-card"><Radio size={16} /> Race-control style panel is based on generated data until live timing API access exists.</div>
          <div className="rc-card"><Video size={16} /> Watch the race legally through F1 TV or your broadcaster. This app only links to official viewing.</div>
          <a className="ghost-btn" href={OFFICIAL_LINKS.f1tv} target="_blank" rel="noreferrer"><PlayCircle size={16} /> Open F1 TV</a>
          <a className="ghost-btn" href={OFFICIAL_LINKS.liveTiming} target="_blank" rel="noreferrer"><Timer size={16} /> Open official live timing</a>
        </div>
      </div>
    </article>
  );
}

export default function Home() {
  const [indexData, setIndexData] = useState([]);
  const [active, setActive] = useState(null);
  const [debug, setDebug] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [status, setStatus] = useState("Waiting for data");
  const [selected, setSelected] = useState(null);
  const [scenario, setScenario] = useState("baseline");
  const [copied, setCopied] = useState(false);

  async function loadIndex() {
    setStatus("Syncing data");
    const res = await fetch(`${DATA_BASE}/briefings/index.json?v=${Date.now()}`);
    if (!res.ok) throw new Error(`index HTTP ${res.status}`);
    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.briefings || []);
    list.sort((a, b) => String(b.generated_iso || b.generated || b.start || "").localeCompare(String(a.generated_iso || a.generated || a.start || "")));
    setIndexData(list);
    await loadDebug();
    if (list.length) await loadBriefing(list[0]);
    else setStatus("No briefings found");
  }

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
    const text = await res.text();
    setMarkdown(text);
    setStatus("Briefing loaded");
  }

  useEffect(() => {
    loadIndex().catch((error) => {
      console.error(error);
      setStatus("No data loaded");
    });
  }, []);

  const top10 = active?.top10 || [];
  const topDriver = top10[0] || {};
  const weather = active?.weather || {};
  const model = active?.prediction_model || {};
  const weights = model.weights || {};
  const available = model.available_components || {};
  const raceTitle = cleanTitle(active?.title || active?.event_title || "F1 Dashboard");
  const startDate = active?.start_iso ? new Date(active.start_iso) : null;
  const carSrc = teamCar(topDriver.team);
  const heroDriverSrc = driverImage(topDriver);
  const html = useMemo(() => mdToHtml(markdown), [markdown]);

  async function copyBriefing() {
    await navigator.clipboard.writeText(markdown || "");
    setCopied(true);
    setTimeout(() => setCopied(false), 1700);
  }

  return (
    <main className="app">
      <nav className="nav">
        <div className="brand">
          <div className="brand-mark">F1</div>
          <div>
            <strong>Race Intel</strong>
            <span>Prediction, strategy, live hub</span>
          </div>
        </div>
        <div className="nav-links">
          <a href="#overview">Overview</a>
          <a href="#live">Live Hub</a>
          <a href="#prediction">Prediction</a>
          <a href="#simulator">Simulator</a>
          <a href="#model">Model</a>
          <button className="pill-btn" onClick={() => loadIndex().catch(() => setStatus("Refresh failed"))}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
        <div className="sync"><i className="dot" /><span>{status}</span></div>
      </nav>

      <section className="hero" id="overview">
        <article className="panel hero-main">
          <div className="track-ring" />
          {carSrc && <img className="hero-car" src={carSrc} alt="" />}
          {heroDriverSrc && <img className="hero-driver" src={heroDriverSrc} alt="" />}
          <div className="hero-content">
            <div className="chips">
              <span className="chip red">Race briefing</span>
              <span className="chip lime">{model.prediction_stage_label || "Free-data model"}</span>
              <span className="chip cyan">Jolpica + FastF1 + Open-Meteo</span>
              <span className="chip amber">ML-inspired ensemble</span>
            </div>
            <h1><span>{raceTitle}</span><br /><span className="outline">Grand Prix</span></h1>
            <p className="summary">
              Hybrid model: the free-data backend is combined with Mintlify-style F1 ML features including grid position, driver history, recent form,
              team average performance, circuit experience, tyre strategy, weather impact, and race simulation signals.
            </p>
          </div>
          <div className="hero-footer">
            <div className="stat"><span>Circuit</span><strong>{active?.circuit || "-"}</strong></div>
            <div className="stat"><span>Track Type</span><strong>{active?.track_type || "-"}</strong></div>
            <div className="stat"><span>Dominance</span><strong>{active?.dominance || "-"}</strong></div>
            <div className="stat"><span>Safety Car</span><strong>{active?.safety_car || "-"}</strong></div>
          </div>
        </article>

        <aside className="side">
          <article className="panel box">
            <div className="section-title">
              <h2>Race Countdown</h2>
              <span className="mini">{startDate && !Number.isNaN(startDate.getTime()) ? startDate.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Start unavailable"}</span>
            </div>
            <Countdown startIso={active?.start_iso} />
          </article>

          <article className="panel box">
            <div className="section-title"><h2>Weather</h2><span className="mini">{weather.source || "Open-Meteo"}</span></div>
            <div className="weather-grid">
              <div className="weather-item"><span>Air</span><strong>{weather.temperature || "-"}</strong></div>
              <div className="weather-item"><span>Track</span><strong>{weather.track_temperature || "Unavailable"}</strong></div>
              <div className="weather-item"><span>Rain</span><strong>{weather.rain || "-"}</strong></div>
              <div className="weather-item"><span>Wind</span><strong>{weather.wind || "-"}</strong></div>
            </div>
            <div className="impact">{weather.impact || "Weather impact will appear after the next briefing run."}</div>
          </article>
        </aside>
      </section>

      <section className="grid" id="strategy">
        <article className="card track">
          <div className="section-title"><h3>Track Model</h3><span className="mini">Historical + weather</span></div>
          <ul className="list">
            <li><div className="row"><span>Speed profile</span><strong>{active?.speed_profile || "-"}</strong></div><div className="meter"><span style={{ "--value": `${speedLevel(active?.speed_profile)}%` }} /></div></li>
            <li><div className="row"><span>Tyre stress</span><strong>{active?.tyre_stress || "-"}</strong></div><div className="meter"><span style={{ "--value": `${level(active?.tyre_stress)}%` }} /></div></li>
            <li><div className="row"><span>Overtaking</span><strong>{active?.overtaking || "-"}</strong></div><div className="meter"><span style={{ "--value": `${level(active?.overtaking)}%` }} /></div></li>
          </ul>
        </article>

        <article className="card strategy">
          <div className="section-title"><h3>Strategy Board</h3><span className="mini">Pit logic</span></div>
          <ul className="list">
            <li className="row"><span>Baseline</span><strong>{active?.strategy_bias || "-"}</strong></li>
            <li className="row"><span>Pit Window</span><strong>{active?.pit_window || "-"}</strong></li>
            <li className="row"><span>Wet Plan</span><strong>{numeric(weather.rain) >= 35 ? "Keep crossover open" : "Dry baseline"}</strong></li>
            <li className="row"><span>Undercut</span><strong>{String(active?.overtaking).includes("low") ? "Strong" : "Medium"}</strong></li>
          </ul>
        </article>

        <article className="card teams">
          <div className="section-title"><h3>Team Fit</h3><span className="mini">Dynamic</span></div>
          <ul className="list">
            {(active?.team_fit || []).slice(0, 5).map((team, index) => (
              <li className="team" key={team}>
                <TeamCar team={team} />
                <div><strong>{index + 1}. {team}</strong><span>Team form and circuit-fit estimate</span></div>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="grid">
        <LiveHub top10={top10} />
      </section>

      <section className="grid" id="prediction">
        <article className="card top10">
          <div className="section-title"><h3>Potential Top 10</h3><span className="mini">Click driver for model details</span></div>
          <div className="prediction-grid">
            {(top10.length ? top10 : [{ name: "No prediction yet", reason: "Run GitHub Actions once." }]).slice(0, 10).map((driver, index) => (
              <DriverCard key={driver.driver_id || driver.name} driver={driver} index={index} onOpen={setSelected} />
            ))}
          </div>
        </article>

        <article className="card archive">
          <div className="section-title"><h3>Briefing Archive</h3><span className="mini">{indexData.length} files</span></div>
          <div className="archive-list">
            {indexData.map((item) => (
              <button className={`archive-item ${active?.path === item.path ? "active" : ""}`} key={item.path} onClick={() => loadBriefing(item)}>
                <strong>{item.title}</strong>
                <span>{item.generated || item.start || item.path}</span>
              </button>
            ))}
          </div>
        </article>
      </section>

      <section className="grid" id="model">
        <StrategySimulator active={scenario} onChange={setScenario} top10={top10} />

        <article className="card model">
          <div className="section-title"><h3>Model Transparency</h3><span className="mini">Weights + data audit</span></div>
          <div className="audit-grid">
            <div className="audit-item"><span>Stage</span><strong>{model.prediction_stage_label || "Unknown"}</strong></div>
            <div className="audit-item"><span>Source</span><strong>{model.source || "Generated backend"}</strong></div>
            <div className="audit-item"><span>FastF1</span><strong>{available.fastf1_race_pace || available.fastf1_qualifying ? "Used" : "Optional / limited"}</strong></div>
            <div className="audit-item"><span>Debug</span><strong>{debug ? "Loaded" : "Not loaded"}</strong></div>
          </div>
          <div className="debug-table" style={{ marginTop: 14 }}>
            {Object.entries(weights).map(([key, value]) => (
              <div className="debug-row" key={key}>
                <span>{key.replaceAll("_", " ")}</span>
                <strong>{(value * 100).toFixed(1)}%</strong>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid">
        <article className="card briefing" id="briefing">
          <div className="section-title">
            <h3>Full Briefing</h3>
            <div className="briefing-tools">
              <button className="ghost-btn" onClick={copyBriefing}><Copy size={16} /> {copied ? "Copied" : "Copy"}</button>
              <a className="ghost-btn" href={OFFICIAL_LINKS.schedule} target="_blank" rel="noreferrer"><CalendarDays size={16} /> Official schedule</a>
            </div>
          </div>
          <div className="briefing-text" dangerouslySetInnerHTML={{ __html: html || "<p>No briefing loaded yet.</p>" }} />
        </article>
      </section>

      <footer>
        Free Vercel dashboard powered by your GitHub Actions data. It links to official viewing sources and does not stream race video.
      </footer>

      <DetailModal driver={selected} onClose={() => setSelected(null)} />
    </main>
  );
}

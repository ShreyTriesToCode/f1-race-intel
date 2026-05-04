"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  Flag,
  Map,
  Radio,
  RefreshCw,
  ShieldCheck,
  Trophy
} from "lucide-react";

const DATA_BASE =
  process.env.NEXT_PUBLIC_F1_DATA_BASE_URL ||
  "https://raw.githubusercontent.com/ShreyTriesToCode/f1-race-intel/main";
const LOCAL_DATA_ENDPOINT = "/api/local-data";

const F1_IMG = "https://media.formula1.com/image/upload";
const F1_MEDIA = "https://media.formula1.com";

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

const DRIVER_MEDIA = {
  "lando norris": { slug: "lannor01", team: "mclaren", display: "Lando_Norris" },
  "oscar piastri": { slug: "oscpia01", team: "mclaren", display: "Oscar_Piastri" },
  "max verstappen": { slug: "maxver01", team: "redbullracing", display: "Max_Verstappen" },
  "charles leclerc": { slug: "chalec01", team: "ferrari", display: "Charles_Leclerc" },
  "lewis hamilton": { slug: "lewham01", team: "ferrari", display: "Lewis_Hamilton" },
  "george russell": { slug: "georus01", team: "mercedes", display: "George_Russell" },
  "kimi antonelli": { slug: "andant01", team: "mercedes", display: "Kimi_Antonelli" },
  "andrea kimi antonelli": { slug: "andant01", team: "mercedes", display: "Kimi_Antonelli" },
  "fernando alonso": { slug: "feralo01", team: "astonmartin", display: "Fernando_Alonso" },
  "lance stroll": { slug: "lanstr01", team: "astonmartin", display: "Lance_Stroll" },
  "carlos sainz": { slug: "carsai01", team: "williams", display: "Carlos_Sainz" },
  "alex albon": { slug: "alealb01", team: "williams", display: "Alexander_Albon" },
  "alexander albon": { slug: "alealb01", team: "williams", display: "Alexander_Albon" },
  "nico hulkenberg": { slug: "nichul01", team: "audi", display: "Nico_Hulkenberg" },
  "nico hülkenberg": { slug: "nichul01", team: "audi", display: "Nico_Hulkenberg" },
  "gabriel bortoleto": { slug: "gabbor01", team: "audi", display: "Gabriel_Bortoleto" },
  "sergio perez": { slug: "serper01", team: "cadillac", display: "Sergio_Perez" },
  "sergio pérez": { slug: "serper01", team: "cadillac", display: "Sergio_Perez" },
  "valtteri bottas": { slug: "valbot01", team: "cadillac", display: "Valtteri_Bottas" },
  "pierre gasly": { slug: "piegas01", team: "alpine", display: "Pierre_Gasly" },
  "franco colapinto": { slug: "fracol01", team: "alpine", display: "Franco_Colapinto" },
  "isack hadjar": { slug: "isahad01", team: "redbullracing", display: "Isack_Hadjar" },
  "liam lawson": { slug: "lialaw01", team: "racingbulls", display: "Liam_Lawson" },
  "esteban ocon": { slug: "estoco01", team: "haas", display: "Esteban_Ocon" },
  "oliver bearman": { slug: "olibea01", team: "haas", display: "Oliver_Bearman" },
  "arvid lindblad": { slug: "arvlin01", team: "racingbulls", display: "Arvid_Lindblad" }
};

const TEAM_CARS = {
  "mclaren": ["mclaren"],
  "ferrari": ["ferrari"],
  "mercedes": ["mercedes"],
  "red bull racing": ["redbullracing", "red-bull-racing"],
  "red bull": ["redbullracing", "red-bull-racing"],
  "williams": ["williams"],
  "aston martin": ["astonmartin", "aston-martin"],
  "aston martin aramco f1 team": ["astonmartin", "aston-martin"],
  "alpine": ["alpine"],
  "alpine f1 team": ["alpine"],
  "bwt alpine f1 team": ["alpine"],
  "haas": ["haas", "haasf1team"],
  "haas f1 team": ["haas", "haasf1team"],
  "moneygram haas f1 team": ["haas", "haasf1team"],
  "racing bulls": ["racingbulls", "rb"],
  "visa cash app rb": ["racingbulls", "rb"],
  "rb": ["racingbulls", "rb"],
  "sauber": ["audi", "kicksauber", "sauber"],
  "kick sauber": ["audi", "kicksauber", "sauber"],
  "audi": ["audi", "kicksauber", "sauber"],
  "cadillac": ["cadillac"]
};

const TEAM_THEMES = {
  "mclaren": ["#ff8700", "#47c7fc"],
  "ferrari": ["#e10600", "#ffd200"],
  "mercedes": ["#00d2be", "#c7c7c7"],
  "red bull racing": ["#1e41ff", "#fcd700"],
  "red bull": ["#1e41ff", "#fcd700"],
  "williams": ["#00a0de", "#ffffff"],
  "aston martin": ["#006f62", "#cedc00"],
  "aston martin aramco f1 team": ["#006f62", "#cedc00"],
  "alpine": ["#0090ff", "#ff4fa3"],
  "alpine f1 team": ["#0090ff", "#ff4fa3"],
  "bwt alpine f1 team": ["#0090ff", "#ff4fa3"],
  "haas": ["#ffffff", "#e6002b"],
  "haas f1 team": ["#ffffff", "#e6002b"],
  "moneygram haas f1 team": ["#ffffff", "#e6002b"],
  "racing bulls": ["#2b4562", "#ffffff"],
  "visa cash app rb": ["#2b4562", "#ffffff"],
  "rb": ["#2b4562", "#ffffff"],
  "sauber": ["#52e252", "#111111"],
  "kick sauber": ["#52e252", "#111111"],
  "audi": ["#e31b23", "#d8d8d8"],
  "cadillac": ["#b9975b", "#d50032"]
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
function unique(list) {
  return Array.from(new Set(list.filter(Boolean)));
}
function driverMedia(driver) {
  const normalized = key(driver?.name || driver);
  if (DRIVER_MEDIA[normalized]) return DRIVER_MEDIA[normalized];
  const compact = normalized.replace(/[^a-z0-9]+/g, "");
  const entry = Object.entries(DRIVER_MEDIA).find(([alias]) => {
    const aliasCompact = alias.replace(/[^a-z0-9]+/g, "");
    return compact.includes(aliasCompact) || aliasCompact.includes(compact);
  });
  return entry?.[1] || null;
}
function driverBodyUrl(meta, year = 2026) {
  if (!meta?.slug || !meta?.team) return "";
  return `${F1_IMG}/c_fill%2Cw_720/q_auto/v1740000001/common/f1/${year}/${meta.team}/${meta.slug}/${year}${meta.team}${meta.slug}right.webp`;
}
function driverHeadshotUrl(meta) {
  if (!meta?.slug || !meta?.display) return "";
  const folder = meta.display.slice(0, 1).toUpperCase();
  return `${F1_MEDIA}/d_driver_fallback_image.png/content/dam/fom-website/drivers/${folder}/${meta.slug.toUpperCase()}_${meta.display}/${meta.slug}.png.transform/1col/image.png`;
}
function driverImageCandidates(driver) {
  const mapped = DRIVER_IMAGES[key(driver?.name || driver)];
  const mappedList = Array.isArray(mapped) ? mapped : [mapped];
  const meta = driverMedia(driver);
  return unique([
    driver?.image,
    driver?.headshot_url,
    ...mappedList,
    driverBodyUrl(meta, 2026),
    driverBodyUrl(meta, 2025),
    driverBodyUrl(meta, 2024),
    driverHeadshotUrl(meta)
  ]);
}
function teamLookup(team, table) {
  const normalized = key(team);
  if (table[normalized]) return table[normalized];
  const compact = normalized.replace(/[^a-z0-9]+/g, "");
  const entry = Object.entries(table)
    .sort((a, b) => b[0].length - a[0].length)
    .find(([alias]) => {
      const aliasCompact = alias.replace(/[^a-z0-9]+/g, "");
      return normalized.includes(alias) || alias.includes(normalized) || compact.includes(aliasCompact) || aliasCompact.includes(compact);
    });
  return entry?.[1];
}
function mediaCar(slug, year = 2026) {
  return `${F1_IMG}/c_lfill%2Cw_3392/q_auto/v1740000001/common/f1/${year}/${slug}/${year}${slug}carright.webp`;
}
function teamCarCandidates(team) {
  const slugs = teamLookup(team, TEAM_CARS) || [key(team).replace(/[^a-z0-9]+/g, "")].filter(Boolean);
  return unique(slugs.flatMap((slug) => [mediaCar(slug, 2026), mediaCar(slug, 2025), mediaCar(slug, 2024)]));
}
function teamTheme(team) {
  const [primary, secondary] = teamLookup(team, TEAM_THEMES) || ["#e10600", "#ffffff"];
  return { "--team-primary": primary, "--team-secondary": secondary };
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
function cleanDataPath(path) {
  return String(path || "").replace(/^\/+/, "");
}
function remoteDataUrl(path) {
  return `${DATA_BASE}/${cleanDataPath(path)}?v=${Date.now()}`;
}
function localDataUrl(path) {
  return `${LOCAL_DATA_ENDPOINT}?path=${encodeURIComponent(cleanDataPath(path))}&v=${Date.now()}`;
}
async function fetchProjectData(path, type = "json") {
  let lastError = null;
  for (const url of [remoteDataUrl(path), localDataUrl(path)]) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`${url} HTTP ${res.status}`);
      return type === "text" ? await res.text() : await res.json();
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error(`Unable to load ${path}`);
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
function dateParts(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return { day: "--", month: "---", time: "--" };
  return {
    day: date.toLocaleDateString([], { day: "2-digit" }),
    month: date.toLocaleDateString([], { month: "short" }).toUpperCase(),
    time: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  };
}
function metric(value, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(number >= 10 ? 1 : 2)}${suffix}`;
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

function RaceWeekendSchedule({ targets, activeIndex, setActiveIndex, active, status }) {
  const rows = (targets?.length ? targets : [{
    target_type: active?.prediction_model?.output_target_type || "race",
    event: { title: active?.event_title || active?.title || "Prediction target", start: active?.start_iso || active?.start }
  }]).slice(0, 4);
  return (
    <div className="monaco-schedule-grid">
      {rows.map((target, index) => {
        const parts = dateParts(target.event?.start);
        return (
          <button
            className={`monaco-schedule-row ${activeIndex === index ? "active" : ""}`}
            key={`${target.target_type}-${target.event?.title || index}`}
            onClick={() => setActiveIndex(index)}
          >
            <span className="schedule-date"><b>{parts.day}</b><small>{parts.month}</small></span>
            <span className="schedule-copy">
              <strong>{target.event?.title || "F1 prediction"}</strong>
              <small>{String(target.target_type || "target").toUpperCase()} · {parts.time}</small>
            </span>
            <span className="schedule-action">Open <ChevronRight size={15} /></span>
          </button>
        );
      })}
      <a className="monaco-schedule-row live-link" href="/live">
        <span className="schedule-date"><b>LIVE</b><small>F1</small></span>
        <span className="schedule-copy">
          <strong>Timing room</strong>
          <small>Leaderboard, race control, radio</small>
        </span>
        <span className="schedule-action">Launch <ChevronRight size={15} /></span>
      </a>
      <div className="monaco-schedule-status">
        <span><Radio size={15} /> Data state</span>
        <strong>{status}</strong>
      </div>
    </div>
  );
}

function ModelSignalMarquee({ predictions, profile, modelMetrics }) {
  const top = predictions?.slice(0, 4) || [];
  const signals = [
    { label: "Track trait", value: profile.car_trait || "Car balance", note: profile.speed_profile || "Circuit profile" },
    { label: "Finish MAE", value: metric(modelMetrics.finish_position?.mae), note: "Backtest regression" },
    { label: "Podium AUC", value: metric(modelMetrics.podium?.auc), note: "Classifier quality" },
    { label: "Lap MAE", value: metric(modelMetrics.neural_lap_time_forecast?.mae_seconds, "s"), note: "Neural pace model" },
    ...top.map((driver, index) => ({
      label: `P${index + 1} pick`,
      value: driver.name || "Driver",
      note: driver.team || driver.reason || "Prediction signal"
    }))
  ].filter((item) => item.value && item.value !== "-");
  const loop = [...signals, ...signals];
  return (
    <section className="signal-strip" aria-label="Model signal stream">
      <div className="signal-track">
        {loop.map((item, index) => (
          <article className="signal-card" key={`${item.label}-${item.value}-${index}`}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.note}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

const OFFICIAL_CIRCUIT_REGISTRY = {
  canada: {
    aliases: ["gilles", "villeneuve", "canadian", "canada", "montreal", "circuit gilles villeneuve"],
    name: "Circuit Gilles Villeneuve",
    officialPage: "https://www.formula1.com/en/racing/2026/canada",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackmontrealdetailed.webp",
    raceLaps: 70,
    sprintLaps: null,
    lengthKm: 4.361,
    raceDistanceKm: 305.27,
  },
  brazil: {
    aliases: ["interlagos", "sao paulo", "são paulo", "brazil", "brasil", "autodromo jose carlos pace", "autódromo josé carlos pace"],
    name: "Autódromo José Carlos Pace",
    officialPage: "https://www.formula1.com/en/racing/2026/brazil",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackinterlagosdetailed.webp",
    raceLaps: 71,
    sprintLaps: null,
    lengthKm: 4.309,
    raceDistanceKm: 305.879,
  },
  monaco: {
    aliases: ["monaco", "monte carlo", "monte-carlo"],
    name: "Circuit de Monaco",
    officialPage: "https://www.formula1.com/en/racing/2026/monaco",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackmonacodetailed.webp",
    raceLaps: 78,
    sprintLaps: null,
    lengthKm: 3.337,
    raceDistanceKm: 260.286,
  },
  great_britain: {
    aliases: ["silverstone", "british", "great britain", "uk", "united kingdom"],
    name: "Silverstone Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/great-britain",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026tracksilverstonedetailed.webp",
    raceLaps: 52,
    sprintLaps: null,
    lengthKm: 5.891,
    raceDistanceKm: 306.198,
  },
  italy: {
    aliases: ["monza", "italian", "italy", "autodromo nazionale monza"],
    name: "Autodromo Nazionale Monza",
    officialPage: "https://www.formula1.com/en/racing/2026/italy",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackmonzadetailed.webp",
    raceLaps: 53,
    sprintLaps: null,
    lengthKm: 5.793,
    raceDistanceKm: 306.72,
  },
  belgium: {
    aliases: ["spa", "belgian", "belgium", "spa-francorchamps", "francorchamps"],
    name: "Circuit de Spa-Francorchamps",
    officialPage: "https://www.formula1.com/en/racing/2026/belgium",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackspadetailed.webp",
    raceLaps: 44,
    sprintLaps: null,
    lengthKm: 7.004,
    raceDistanceKm: 308.052,
  },
  japan: {
    aliases: ["suzuka", "japanese", "japan"],
    name: "Suzuka Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/japan",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026tracksuzukadetailed.webp",
    raceLaps: 53,
    sprintLaps: null,
    lengthKm: 5.807,
    raceDistanceKm: 307.471,
  },
  abu_dhabi: {
    aliases: ["yas marina", "abu dhabi", "united arab emirates", "uae"],
    name: "Yas Marina Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/abu-dhabi",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackabudhabidetailed.webp",
    raceLaps: 58,
    sprintLaps: null,
    lengthKm: 5.281,
    raceDistanceKm: 306.183,
  },
  miami: {
    aliases: ["miami", "miami international"],
    name: "Miami International Autodrome",
    officialPage: "https://www.formula1.com/en/racing/2026/miami",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackmiamidetailed.webp",
    raceLaps: 57,
    sprintLaps: null,
    lengthKm: 5.412,
    raceDistanceKm: 308.326,
  },
  barcelona: {
    aliases: ["barcelona", "catalunya", "spain", "spanish", "barcelona-catalunya"],
    name: "Circuit de Barcelona-Catalunya",
    officialPage: "https://www.formula1.com/en/racing/2026/spain",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackbarcelonadetailed.webp",
    raceLaps: 66,
    sprintLaps: null,
    lengthKm: 4.657,
    raceDistanceKm: 307.236,
  },
  austria: {
    aliases: ["spielberg", "austrian", "austria", "red bull ring"],
    name: "Red Bull Ring",
    officialPage: "https://www.formula1.com/en/racing/2026/austria",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackaustriadetailed.webp",
    raceLaps: 71,
    sprintLaps: null,
    lengthKm: 4.318,
    raceDistanceKm: 306.452,
  },
  hungary: {
    aliases: ["hungaroring", "hungarian", "hungary"],
    name: "Hungaroring",
    officialPage: "https://www.formula1.com/en/racing/2026/hungary",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackhungarydetailed.webp",
    raceLaps: 70,
    sprintLaps: null,
    lengthKm: 4.381,
    raceDistanceKm: 306.63,
  },
  zandvoort: {
    aliases: ["zandvoort", "dutch", "netherlands"],
    name: "Circuit Zandvoort",
    officialPage: "https://www.formula1.com/en/racing/2026/netherlands",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackzandvoortdetailed.webp",
    raceLaps: 72,
    sprintLaps: null,
    lengthKm: 4.259,
    raceDistanceKm: 306.587,
  },
  singapore: {
    aliases: ["singapore", "marina bay"],
    name: "Marina Bay Street Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/singapore",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026tracksingaporedetailed.webp",
    raceLaps: 62,
    sprintLaps: null,
    lengthKm: 4.94,
    raceDistanceKm: 306.143,
  },
  las_vegas: {
    aliases: ["las vegas", "vegas"],
    name: "Las Vegas Strip Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/las-vegas",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026tracklasvegasdetailed.webp",
    raceLaps: 50,
    sprintLaps: null,
    lengthKm: 6.201,
    raceDistanceKm: 309.958,
  },
  qatar: {
    aliases: ["qatar", "lusail", "losail"],
    name: "Lusail International Circuit",
    officialPage: "https://www.formula1.com/en/racing/2026/qatar",
    image: "https://media.formula1.com/image/upload/c_fit%2Cw_900%2Ch_520/q_auto/v1740000001/common/f1/2026/track/2026trackqatardetailed.webp",
    raceLaps: 57,
    sprintLaps: null,
    lengthKm: 5.419,
    raceDistanceKm: 308.611,
  },
};

function getOfficialCircuit(profile) {
  const lookupText = key(
    [
      profile?.circuit,
      profile?.race_name,
      profile?.event_title,
      profile?.country,
      profile?.city,
      profile?.circuit_key,
      profile?.jolpica_race?.raceName,
      profile?.jolpica_race?.Circuit?.circuitName,
      profile?.jolpica_race?.Circuit?.circuitId,
      profile?.jolpica_race?.Circuit?.Location?.country,
    ]
      .filter(Boolean)
      .join(" ")
  );

  return (
    Object.values(OFFICIAL_CIRCUIT_REGISTRY).find((circuit) =>
      circuit.aliases.some((alias) => lookupText.includes(key(alias)))
    ) || null
  );
}

function sessionLaps(profile, circuit, selectedTarget) {
  const targetType = key(
    selectedTarget?.target_type ||
      profile?.prediction_model?.output_target_type ||
      profile?.output_target_type ||
      profile?.event_title ||
      profile?.title
  );

  const explicitSprint =
    selectedTarget?.sprint_laps ??
    profile?.sprint_laps ??
    profile?.weekend?.sprint_laps ??
    profile?.race_info?.sprint_laps;

  const explicitRace =
    selectedTarget?.race_laps ??
    profile?.race_laps ??
    profile?.laps ??
    profile?.weekend?.race_laps ??
    profile?.race_info?.race_laps;

  const isSprint = targetType.includes("sprint");

  if (isSprint) {
    return {
      label: "Sprint laps",
      value: explicitSprint ?? circuit?.sprintLaps ?? "Not confirmed",
      note:
        explicitSprint || circuit?.sprintLaps
          ? "Sprint lap count from generated data or circuit registry."
          : "Sprint lap count is not confirmed in generated data yet.",
    };
  }

  return {
    label: "Race laps",
    value: explicitRace ?? circuit?.raceLaps ?? "Not confirmed",
    note:
      explicitRace || circuit?.raceLaps
        ? "Race lap count from generated data or Formula 1 race-page data."
        : "Race lap count is not confirmed in generated data yet.",
  };
}

function OfficialCircuitImage({ circuit }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [circuit?.image]);

  if (!circuit || !circuit.image || failed) {
    return (
      <div
        className="grid min-h-[300px] place-items-center rounded-[1.7rem] bg-black/40"
        style={{ width: "100%", maxWidth: "100%", overflow: "hidden" }}
      >
        <div className="text-center">
          <Map className="mx-auto mb-4 text-zinc-500" size={54} />
          <p className="text-sm text-zinc-400">
            Official circuit image is not mapped yet for this venue.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="relative min-w-0 overflow-hidden rounded-[1.7rem] border border-white/10 bg-black/70 p-3"
      style={{ width: "100%", maxWidth: "100%", overflow: "hidden" }}
    >
      <div
        className="grid place-items-center overflow-hidden rounded-[1.25rem] bg-black/80"
        style={{
          width: "100%",
          maxWidth: "100%",
          height: "clamp(240px, 32vw, 380px)",
          overflow: "hidden",
        }}
      >
        <img
          src={circuit.image}
          alt={`${circuit.name} official Formula 1 circuit map`}
          loading="lazy"
          onError={() => setFailed(true)}
          style={{
            display: "block",
            width: "100%",
            height: "100%",
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
            objectPosition: "center",
          }}
        />
      </div>
    </div>
  );
}

function CircuitIntelCard({ profile, weather, selectedTarget }) {
  const circuit = getOfficialCircuit(profile);
  const lapInfo = sessionLaps(profile, circuit, selectedTarget);

  return (
    <section id="circuit" className="min-w-0 overflow-hidden rounded-[2rem] border border-white/10 bg-[#111113] p-6 shadow-2xl">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black tracking-tight text-[#f5efe7]">
            Circuit Intel
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            {profile?.circuit || circuit?.name || "Circuit data"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-zinc-200">
          <Map size={26} />
        </div>
      </div>

      <OfficialCircuitImage circuit={circuit} />

      <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#c1e328]">
          Circuit source
        </p>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          {circuit
            ? "Using the official Formula 1 circuit map image for this venue."
            : "No official Formula 1 circuit image is mapped for this venue yet."}
        </p>

        {circuit?.officialPage && (
          <a
            href={circuit.officialPage}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs font-bold text-zinc-200 hover:bg-white/10"
          >
            Open official F1 race page
          </a>
        )}
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-lime-400/20 bg-lime-400/10 p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-lime-300">
            {lapInfo.label}
          </p>
          <p className="mt-2 text-3xl font-black text-[#f5efe7]">
            {lapInfo.value}
          </p>
          <p className="mt-2 text-xs leading-5 text-zinc-400">{lapInfo.note}</p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-500">
            Circuit length
          </p>
          <p className="mt-2 text-lg font-black text-[#f5efe7]">
            {circuit?.lengthKm ? `${circuit.lengthKm} km` : "-"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-500">
            Race distance
          </p>
          <p className="mt-2 text-lg font-black text-[#f5efe7]">
            {circuit?.raceDistanceKm ? `${circuit.raceDistanceKm} km` : "-"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-500">
            Car trait
          </p>
          <p className="mt-2 text-lg font-black text-[#f5efe7]">
            {profile?.car_trait || profile?.dominance || "-"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-500">
            Speed profile
          </p>
          <p className="mt-2 text-lg font-black text-[#f5efe7]">
            {profile?.speed_profile || "-"}
          </p>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-zinc-500">
            Tyre stress
          </p>
          <p className="mt-2 text-lg font-black text-[#f5efe7]">
            {profile?.tyre_stress || "-"}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-lime-400/20 bg-lime-400/10 p-4">
        <p className="text-sm leading-6 text-zinc-200">
          {weather?.impact || "Weather and tyre effects update after the next workflow run."}
        </p>
      </div>
    </section>
  );
}


function DriverArt({ driver }) {
  const candidates = driverImageCandidates(driver);
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [driver?.name, driver?.team, driver?.image, driver?.headshot_url]);
  const src = candidates[index];
  if (!src) return <div className="driver-fallback">{initials(driver?.name)}</div>;
  return <img src={src} alt={driver?.name || "Driver"} onError={() => setIndex((value) => value + 1)} />;
}

function TeamCar({ team }) {
  const candidates = teamCarCandidates(team);
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [team]);
  const src = candidates[index];
  if (!src) {
    return (
      <span className="team-fallback-car" style={teamTheme(team)} aria-label={`${team} livery`}>
        <i /><b>{initials(team)}</b>
      </span>
    );
  }
  return <img className="team-car" src={src} alt={`${team} car`} onError={() => setIndex((value) => value + 1)} />;
}

function HeroCar({ team }) {
  const candidates = teamCarCandidates(team);
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [team]);
  const src = candidates[index];
  if (!src) return <span className="hero-car-fallback team-fallback-car" style={teamTheme(team)}><i /><b>{initials(team)}</b></span>;
  return <img className="hero-car" src={src} alt="" onError={() => setIndex((value) => value + 1)} />;
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
              {driver.predicted_finish_position !== undefined && driver.predicted_finish_position !== null && <small>Model P{Number(driver.predicted_finish_position).toFixed(1)}</small>}
              {driver.predicted_lap_pace_seconds !== undefined && driver.predicted_lap_pace_seconds !== null && <small>Lap {Number(driver.predicted_lap_pace_seconds).toFixed(2)}s</small>}
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
      setDebug(await fetchProjectData("data_cache/latest-model-debug.json"));
    } catch {
      setDebug(null);
    }
  }

  async function loadBriefing(item) {
    setStatus("Loading briefing");
    setActive(item);
    setMarkdown(await fetchProjectData(item.path, "text"));
    setTargetIndex(0);
    setStatus("Ready");
  }

  async function loadIndex() {
    setStatus("Syncing");
    const data = await fetchProjectData("briefings/index.json");
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
  const modelMetrics = model.ml_model_meta?.metrics || {};
  const finishMetrics = modelMetrics.finish_position || {};
  const lapMetrics = modelMetrics.neural_lap_time_forecast || {};
  const rankingMetrics = finishMetrics.ranking || modelMetrics.win_probability_ranking || {};
  const predictions = selectedTarget.top10?.length ? selectedTarget.top10 : active?.top10?.length ? active.top10 : parseBriefingTop10(markdown);
  const topDriver = predictions[0] || {};
  const title = cleanTitle(active?.title || selectedTarget?.event?.title || "Race Intel");
  const html = useMemo(() => mdToHtml(markdown), [markdown]);
  const canCopy = Boolean(markdown);

  async function copyBriefing() {
    if (!canCopy) return;
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  }

  return (
    <main className="app monaco-app">
      <nav className="monaco-nav">
        <a className="monaco-logo" href="#latest" aria-label="Race Intel home">
          <span>F1</span>
        </a>
        <div className="monaco-links">
          <a href="#schedule">Schedule</a>
          <a href="#predictions">Standings</a>
          <a href="#circuit">Circuit</a>
          <a href="#teams">Teams</a>
          <a href="/live">Live Timing</a>
        </div>
        <button className="monaco-menu-button" onClick={() => loadIndex().catch(() => setStatus("Refresh failed"))} aria-label="Refresh data">
          <i /><i />
        </button>
      </nav>

      <section className="monaco-hero" id="latest">
        <div className="monaco-hero-media">
          <HeroCar team={topDriver.team} />
          <div className="monaco-title-mask" aria-hidden="true">{title}</div>
          <div className="speed-light" aria-hidden="true" />
        </div>

        <div className="monaco-hero-copy">
          <div className="chips">
            <span>Race Intel</span>
            <span>{model.prediction_stage_label || "Model active"}</span>
            <span>{model.output_target_type || "Sprint/Race"}</span>
          </div>
          <h1>{title}</h1>
          <p>
            Sprint and Race predictions shaped by qualifying, practice, weather, upgrades, track traits,
            current-season car form, live timing signals, and the high-accuracy model audit.
          </p>
          <div className="monaco-hero-actions">
            <a href="#predictions">View prediction <ChevronRight size={16} /></a>
            <a href="/live">Live timing <Radio size={16} /></a>
          </div>
        </div>

        <aside className="monaco-countdown">
          <div className="section-head">
            <h2>Next target</h2>
            <Clock size={18} />
          </div>
          <p className="muted">{selectedTarget.event?.title || active?.event_title || "No target loaded"}</p>
          <strong className="time">{formatTime(selectedTarget.event?.start || active?.start_iso || active?.start)}</strong>
          <Countdown startIso={selectedTarget.event?.start || active?.start_iso} />
        </aside>

        <div className="hero-stats monaco-hero-stats">
          <div><span>Circuit</span><strong>{profile.circuit || active?.circuit || "-"}</strong></div>
          <div><span>Target</span><strong>{String(selectedTarget.target_type || model.output_target_type || "Race").toUpperCase()}</strong></div>
          <div><span>Generated</span><strong>{active?.generated || "-"}</strong></div>
        </div>
      </section>

      <section className="race-weekend-panel" id="schedule">
        <div className="race-weekend-heading">
          <span>Race Weekend</span>
          <h2>{selectedTarget.event?.title || active?.event_title || "Prediction schedule"}</h2>
          <p>Automatic workflow outputs, timing room, and current sync state in one race-weekend control surface.</p>
        </div>
        <RaceWeekendSchedule
          targets={targets}
          activeIndex={targetIndex}
          setActiveIndex={setTargetIndex}
          active={active}
          status={status}
        />
      </section>

      <ModelSignalMarquee predictions={predictions} profile={profile} modelMetrics={modelMetrics} />

      <section className="layout monaco-grid-main min-w-0 overflow-hidden" id="predictions">
        <article className="card prediction-section">
          <div className="section-head">
            <h2>Prediction Standings</h2>
            <Trophy size={18} />
          </div>
          <PredictionList predictions={predictions} />
        </article>

        <aside className="stack min-w-0 overflow-hidden">
          <CircuitIntelCard profile={profile} weather={weather} selectedTarget={selectedTarget} />

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

      <section className="layout small monaco-support-grid" id="teams">
        <article className="card team-fit-card">
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

        <article className="card model-status-card">
          <div className="section-head"><h2>Model Status</h2><BarChart3 size={18} /></div>
          <div className="fact"><span>Output mode</span><strong>{debug?.output_mode || "Latest"}</strong></div>
          <div className="fact"><span>Backfill used</span><strong>{debug?.backfill?.used ?? "-"}</strong></div>
          <div className="fact"><span>ML model</span><strong>{model.ml_model_loaded ? "Loaded" : "Fallback"}</strong></div>
          <div className="fact"><span>Timing source</span><strong>{model.available_components?.timing_provider_status || "Jolpica/FastF1 fallback"}</strong></div>
          <div className="fact"><span>Finish MAE</span><strong>{metric(finishMetrics.mae)}</strong></div>
          <div className="fact"><span>Lap MAE</span><strong>{metric(lapMetrics.mae_seconds, "s")}</strong></div>
          <div className="fact"><span>Top-5 recall</span><strong>{rankingMetrics.top5_recall !== undefined ? metric(rankingMetrics.top5_recall * 100, "%") : "-"}</strong></div>
        </article>

        <article className="card archive-card">
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

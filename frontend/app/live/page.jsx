"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  BadgeInfo,
  Car,
  Clock3,
  CloudRain,
  Eye,
  EyeOff,
  Flag,
  Gauge,
  Pause,
  Play,
  Radio,
  RefreshCcw,
  Settings2,
  ShieldAlert,
  Timer,
  Trophy,
  Waves
} from "lucide-react";

const DEFAULT_WIDGETS = {
  leaderboard: true,
  intervals: true,
  laps: true,
  stints: true,
  pits: true,
  weather: true,
  raceControl: true,
  telemetry: true,
  radio: true,
  session: true
};

const WIDGET_LABELS = {
  leaderboard: "Leaderboard",
  intervals: "Intervals",
  laps: "Lap times",
  stints: "Tyres and stints",
  pits: "Pit stops",
  weather: "Weather",
  raceControl: "Race control",
  telemetry: "Car metrics",
  radio: "Team radio",
  session: "Session info"
};

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

function fmt(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function time(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return fmt(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function lap(value) {
  if (!value) return "-";
  if (typeof value === "string" && value.includes(":")) return value;
  const n = Number(value);
  if (!Number.isFinite(n)) return fmt(value);
  const m = Math.floor(n / 60);
  const s = (n % 60).toFixed(3).padStart(6, "0");
  return `${m}:${s}`;
}

function color(teamColour) {
  const raw = String(teamColour || "").replace("#", "").trim();
  return /^[0-9a-fA-F]{6}$/.test(raw) ? `#${raw}` : "#e10600";
}

function latestRows(rows, key = "driver_number") {
  const map = new globalThis.Map();
  for (const row of rows || []) {
    map.set(row[key] ?? row.driver_number ?? Math.random(), row);
  }
  return Array.from(map.values());
}

function driverName(driver) {
  return driver?.full_name || [driver?.first_name, driver?.last_name].filter(Boolean).join(" ") || driver?.name_acronym || driver?.driver_number || "-";
}

function normalizeArray(payload) {
  if (!payload?.ok) return [];
  return Array.isArray(payload.data) ? payload.data : [];
}

function normalizeOpenF1Fallback(fallback) {
  if (!fallback) return null;
  const drivers = normalizeArray(fallback.drivers);
  const driverMap = new globalThis.Map(drivers.map((driver) => [driver.driver_number, driver]));
  const intervals = latestRows(normalizeArray(fallback.intervals));
  const positions = latestRows(normalizeArray(fallback.position));
  const laps = latestRows(normalizeArray(fallback.laps));
  const stints = latestRows(normalizeArray(fallback.stints));
  const carData = latestRows(normalizeArray(fallback.car_data));
  const rows = intervals.length ? intervals : positions;
  const leaderboard = rows.map((row, index) => {
    const driver = driverMap.get(row.driver_number) || {};
    const lapRow = laps.find((item) => item.driver_number === row.driver_number) || {};
    const stint = stints.find((item) => item.driver_number === row.driver_number) || {};
    const car = carData.find((item) => item.driver_number === row.driver_number) || {};
    return {
      ...row,
      position: row.position || index + 1,
      name: driverName(driver),
      driver,
      team: driver.team_name,
      colour: color(driver.team_colour),
      interval: row.interval || row.gap_to_leader || row.gap,
      lap_duration: lapRow.lap_duration,
      compound: stint.compound,
      tyre_age: stint.tyre_age_at_start,
      speed: car.speed,
      n_gear: car.n_gear,
      rpm: car.rpm,
      drs: car.drs,
      brake: car.brake
    };
  });

  return {
    session: normalizeArray(fallback.sessions)[0] || {},
    drivers,
    leaderboard,
    intervals: leaderboard,
    laps: leaderboard,
    stints: leaderboard,
    pits: normalizeArray(fallback.pit).slice(-20).reverse(),
    raceControl: normalizeArray(fallback.race_control).slice(-20).reverse(),
    weather: normalizeArray(fallback.weather).slice(-1)[0] || null,
    carData: leaderboard,
    radio: normalizeArray(fallback.team_radio).slice(-20).reverse(),
    source: "OpenF1 fallback"
  };
}

async function fetchF1Timing(session = "latest") {
  const url = new URL("/api/f1timing", window.location.origin);
  url.searchParams.set("session", session || "latest");
  url.searchParams.set("year", String(new Date().getUTCFullYear()));
  const res = await fetch(url.toString(), { cache: "no-store" });
  return res.json();
}

function usePersistentWidgets() {
  const [widgets, setWidgets] = useState(DEFAULT_WIDGETS);
  useEffect(() => {
    try {
      const stored = localStorage.getItem("f1-live-widgets");
      if (stored) setWidgets({ ...DEFAULT_WIDGETS, ...JSON.parse(stored) });
    } catch {}
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("f1-live-widgets", JSON.stringify(widgets));
    } catch {}
  }, [widgets]);
  return [widgets, setWidgets];
}

function SourcePill({ status }) {
  return (
    <div className={cx("source-pill", status?.ok ? "ok" : "warn")}>
      <span>{status?.label || "Source pending"}</span>
      <strong>{status?.detail || ""}</strong>
    </div>
  );
}

function Panel({ id, title, icon, enabled, children, empty }) {
  if (!enabled) return null;
  return (
    <section className="live-card" id={id}>
      <div className="live-card-head">
        <h2>{icon}{title}</h2>
      </div>
      {empty ? <p className="live-empty">{empty}</p> : children}
    </section>
  );
}

function WidgetSettings({ widgets, setWidgets }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="live-settings">
      <button className="live-btn" onClick={() => setOpen(!open)}>
        <Settings2 size={16} /> Widgets
      </button>
      {open && (
        <div className="live-settings-panel">
          {Object.keys(DEFAULT_WIDGETS).map((key) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={!!widgets[key]}
                onChange={(event) => setWidgets((prev) => ({ ...prev, [key]: event.target.checked }))}
              />
              <span>{WIDGET_LABELS[key]}</span>
              {widgets[key] ? <Eye size={14} /> : <EyeOff size={14} />}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function RadioPlayer({ item }) {
  const [proxy, setProxy] = useState(true);
  const url = item?.recording_url || item?.RecordingUrl || item?.url;
  const src = url ? (proxy ? `/api/audio?url=${encodeURIComponent(url)}` : url) : "";
  if (!url) return <span className="radio-missing">No recording URL</span>;
  return (
    <div className="radio-player">
      <audio controls preload="none" src={src} />
      <button onClick={() => setProxy(!proxy)}>{proxy ? "Proxy" : "Direct"}</button>
      <a href={url} target="_blank" rel="noreferrer">Open</a>
    </div>
  );
}

export default function LivePage() {
  const [widgets, setWidgets] = usePersistentWidgets();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [sessionKeyInput, setSessionKeyInput] = useState("latest");
  const [activeSessionKey, setActiveSessionKey] = useState("latest");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState(null);

  async function loadLiveData(nextSession = activeSessionKey) {
    setLoading(true);
    try {
      const data = await fetchF1Timing(nextSession);
      setPayload(data);
      const selectedSession = data?.normalized?.session?.session_path || data?.normalized?.session?.session_name;
      if (selectedSession && nextSession === "latest") setActiveSessionKey(String(selectedSession));
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLiveData("latest");
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => loadLiveData(activeSessionKey), 20000);
    return () => clearInterval(id);
  }, [autoRefresh, activeSessionKey]);

  const normalized = useMemo(() => {
    if (payload?.ok && payload.normalized) return { ...payload.normalized, source: "Formula 1 Live Timing" };
    return normalizeOpenF1Fallback(payload?.openf1_fallback) || {};
  }, [payload]);

  const session = normalized.session || {};
  const drivers = normalized.drivers || [];
  const driverMap = useMemo(() => new globalThis.Map(drivers.map((driver) => [driver.driver_number, driver])), [drivers]);
  const leaderboard = normalized.leaderboard || [];
  const intervals = normalized.intervals || leaderboard;
  const laps = normalized.laps || leaderboard;
  const stints = normalized.stints || leaderboard;
  const pits = normalized.pits || [];
  const raceControl = normalized.raceControl || [];
  const weather = normalized.weather || null;
  const carData = normalized.carData || leaderboard;
  const radio = normalized.radio || [];

  const feedCount = payload?.feed_status ? Object.values(payload.feed_status).filter((item) => item.ok && item.count).length : 0;
  const status = {
    ok: Boolean(payload?.ok),
    label: normalized.source || (payload?.ok ? "Formula 1 Live Timing" : "Fallback mode"),
    detail: payload?.ok ? `${feedCount} feeds` : "OpenF1/public fallback"
  };

  function applySessionKey() {
    const clean = sessionKeyInput.trim() || "latest";
    setActiveSessionKey(clean);
    loadLiveData(clean);
  }

  return (
    <main className="live-shell">
      <header className="live-hero">
        <div>
          <div className="live-kicker"><Radio size={16} /> Race Intel Live</div>
          <h1>Live details</h1>
          <p>
            Primary data now comes from Formula 1 livetiming static feeds. OpenF1 remains a fallback for public historical/latest data when real-time feeds are unavailable.
          </p>
        </div>
        <div className="live-hero-actions">
          <SourcePill status={status} />
          <button className="live-btn" onClick={() => loadLiveData(activeSessionKey)} disabled={loading}>
            <RefreshCcw size={16} /> {loading ? "Refreshing" : "Refresh"}
          </button>
          <button className={cx("live-btn", autoRefresh && "active")} onClick={() => setAutoRefresh(!autoRefresh)}>
            {autoRefresh ? <Pause size={16} /> : <Play size={16} />}
            {autoRefresh ? "Auto" : "Manual"}
          </button>
          <a className="live-btn" href="/">Predictions</a>
        </div>
      </header>

      <section className="live-controls">
        <div className="session-input">
          <label>Session</label>
          <input value={sessionKeyInput} onChange={(e) => setSessionKeyInput(e.target.value)} placeholder="latest, Race, Qualifying, Sprint" />
          <button onClick={applySessionKey}>Load</button>
        </div>
        <WidgetSettings widgets={widgets} setWidgets={setWidgets} />
        <div className="live-meta">
          <span>Active: <strong>{fmt(session.session_name || activeSessionKey)}</strong></span>
          <span>Path: <strong>{fmt(session.base_path || session.session_path)}</strong></span>
          <span>Updated: <strong>{lastUpdated ? lastUpdated.toLocaleTimeString() : "-"}</strong></span>
        </div>
      </section>

      {!payload?.ok && (
        <section className="live-warning">
          <BadgeInfo size={18} />
          <div>
            <strong>Formula 1 livetiming feed is not fully available for this selected session.</strong>
            <p>The dashboard is showing fallback/public data where available. This usually happens before a session starts, after archive delay, or when a feed is restricted.</p>
          </div>
        </section>
      )}

      <section className="live-grid">
        <Panel id="session" enabled={widgets.session} title="Session" icon={<Clock3 size={18} />} empty={!session?.session_name && "No session data available."}>
          <div className="live-facts">
            <div><span>Meeting</span><strong>{fmt(session.meeting_name || session.country_name)}</strong></div>
            <div><span>Session</span><strong>{fmt(session.session_name)}</strong></div>
            <div><span>Type</span><strong>{fmt(session.session_type)}</strong></div>
            <div><span>Start</span><strong>{fmt(session.date_start)}</strong></div>
            <div><span>Lap</span><strong>{fmt(normalized.lapCount?.current_lap)} / {fmt(normalized.lapCount?.total_laps)}</strong></div>
            <div><span>Track</span><strong>{fmt(normalized.trackStatus?.Status || normalized.trackStatus?.Message)}</strong></div>
          </div>
        </Panel>

        <Panel id="leaderboard" enabled={widgets.leaderboard} title="Leaderboard" icon={<Trophy size={18} />} empty={!leaderboard.length && "No timing data available for this session yet."}>
          <div className="live-table">
            <div className="live-row head"><span>Pos</span><span>Driver</span><span>Gap</span><span>Lap</span><span>Tyre</span><span>Speed</span></div>
            {leaderboard.slice(0, 24).map((row, index) => (
              <div className="live-row" key={`${row.driver_number}-${index}`}>
                <span>{fmt(row.position || index + 1)}</span>
                <span className="driver-cell"><i style={{ background: color(row.driver?.team_colour || row.colour) }} />{fmt(row.name || driverName(row.driver))}</span>
                <span>{fmt(row.interval || row.gap_to_leader)}</span>
                <span>{lap(row.lap_duration)}</span>
                <span>{fmt(row.compound)}</span>
                <span>{fmt(row.speed)}{row.speed ? " km/h" : ""}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel id="intervals" enabled={widgets.intervals} title="Intervals" icon={<Timer size={18} />} empty={!intervals.length && "No interval feed available."}>
          <div className="compact-list">
            {intervals.slice(0, 20).map((row) => <div key={`${row.driver_number}-interval`}><strong>{fmt(row.name || driverName(row.driver || driverMap.get(row.driver_number)))}</strong><span>{fmt(row.interval || row.gap_to_leader)}</span></div>)}
          </div>
        </Panel>

        <Panel id="laps" enabled={widgets.laps} title="Lap times" icon={<Flag size={18} />} empty={!laps.length && "No lap data available."}>
          <div className="compact-list">
            {laps.slice(0, 20).map((row) => <div key={`${row.driver_number}-lap`}><strong>{fmt(row.name || driverName(row.driver || driverMap.get(row.driver_number)))}</strong><span>{lap(row.lap_duration)}</span></div>)}
          </div>
        </Panel>

        <Panel id="stints" enabled={widgets.stints} title="Tyres and stints" icon={<Waves size={18} />} empty={!stints.length && "No stint data available."}>
          <div className="compact-list">
            {stints.slice(0, 20).map((row) => <div key={`${row.driver_number}-stint`}><strong>{fmt(row.name || driverName(row.driver || driverMap.get(row.driver_number)))}</strong><span>{fmt(row.compound)} · age {fmt(row.tyre_age || row.tyre_age_at_start)}</span></div>)}
          </div>
        </Panel>

        <Panel id="pits" enabled={widgets.pits} title="Pit stops" icon={<Car size={18} />} empty={!pits.length && "No pit data available."}>
          <div className="compact-list">
            {pits.map((row, index) => <div key={`${row.driver_number}-pit-${index}`}><strong>{driverName(driverMap.get(row.driver_number))}</strong><span>Lap {fmt(row.lap_number)} · {fmt(row.pit_duration || row.duration)}s</span></div>)}
          </div>
        </Panel>

        <Panel id="weather" enabled={widgets.weather} title="Weather" icon={<CloudRain size={18} />} empty={!weather && "No weather data available."}>
          <div className="live-facts weather">
            <div><span>Air</span><strong>{fmt(weather?.air_temperature || weather?.AirTemp)}°C</strong></div>
            <div><span>Track</span><strong>{fmt(weather?.track_temperature || weather?.TrackTemp)}°C</strong></div>
            <div><span>Humidity</span><strong>{fmt(weather?.humidity || weather?.Humidity)}%</strong></div>
            <div><span>Rain</span><strong>{fmt(weather?.rainfall || weather?.Rainfall)}</strong></div>
            <div><span>Wind</span><strong>{fmt(weather?.wind_speed || weather?.WindSpeed)} km/h</strong></div>
            <div><span>Direction</span><strong>{fmt(weather?.wind_direction || weather?.WindDirection)}°</strong></div>
          </div>
        </Panel>

        <Panel id="race-control" enabled={widgets.raceControl} title="Race control" icon={<ShieldAlert size={18} />} empty={!raceControl.length && "No race-control messages available."}>
          <div className="race-control-list">
            {raceControl.map((msg, index) => <article key={`${msg.date}-${index}`}><time>{time(msg.date)}</time><strong>{fmt(msg.category || msg.flag || msg.scope, "Message")}</strong><p>{fmt(msg.message)}</p></article>)}
          </div>
        </Panel>

        <Panel id="telemetry" enabled={widgets.telemetry} title="Car metrics" icon={<Gauge size={18} />} empty={!carData.length && "No car metrics available for this selected feed."}>
          <div className="live-table">
            <div className="live-row head"><span>Driver</span><span>Speed</span><span>Gear</span><span>RPM</span><span>DRS</span><span>Brake</span></div>
            {carData.slice(0, 24).map((row) => <div className="live-row" key={`${row.driver_number}-car`}><span>{fmt(row.name || driverName(row.driver || driverMap.get(row.driver_number)))}</span><span>{fmt(row.speed)}{row.speed ? " km/h" : ""}</span><span>{fmt(row.n_gear)}</span><span>{fmt(row.rpm)}</span><span>{fmt(row.drs)}</span><span>{fmt(row.brake)}</span></div>)}
          </div>
        </Panel>

        <Panel id="radio" enabled={widgets.radio} title="Team radio" icon={<AudioLines size={18} />} empty={!radio.length && "No radio messages available yet."}>
          <div className="radio-list">
            {radio.map((item, index) => <article key={`${item.date}-${item.driver_number}-${index}`}><div><strong>{driverName(driverMap.get(item.driver_number))}</strong><span>{time(item.date)}</span></div><RadioPlayer item={item} /></article>)}
          </div>
        </Panel>
      </section>

      <footer className="live-footer">
        Primary feed: Formula 1 livetiming static data. Fallback: OpenF1 public historical/latest data. This page does not stream race video.
      </footer>
    </main>
  );
}

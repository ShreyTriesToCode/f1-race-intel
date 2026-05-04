"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AudioLines,
  BadgeInfo,
  Car,
  Clock3,
  CloudRain,
  Eye,
  EyeOff,
  Flag,
  Gauge,
  History,
  Map,
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
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function lap(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  const m = Math.floor(n / 60);
  const s = (n % 60).toFixed(3).padStart(6, "0");
  return `${m}:${s}`;
}
function color(teamColour) {
  const raw = String(teamColour || "").replace("#", "").trim();
  return /^[0-9a-fA-F]{6}$/.test(raw) ? `#${raw}` : "#e10600";
}
function latestRows(rows, key = "driver_number") {
  const map = new Map();
  for (const row of rows || []) {
    map.set(row[key] ?? row.driver_number ?? Math.random(), row);
  }
  return Array.from(map.values());
}
function driverName(driver) {
  return driver?.full_name || [driver?.first_name, driver?.last_name].filter(Boolean).join(" ") || driver?.name_acronym || driver?.driver_number || "-";
}
async function fetchOpenF1(endpoint, params = {}) {
  const url = new URL("/api/openf1", window.location.origin);
  url.searchParams.set("endpoint", endpoint);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  const res = await fetch(url.toString(), { cache: "no-store" });
  return res.json();
}
function normalizeArray(payload) {
  if (!payload?.ok) return [];
  return Array.isArray(payload.data) ? payload.data : [];
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
  const ok = status?.okCount || 0;
  const fail = status?.failCount || 0;
  return (
    <div className={cx("source-pill", fail ? "warn" : "ok")}>
      <span>{ok} endpoints active</span>
      {!!fail && <strong>{fail} fallback</strong>}
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

function RadioPlayer({ item, driver }) {
  const [proxy, setProxy] = useState(true);
  const src = item?.recording_url
    ? proxy
      ? `/api/audio?url=${encodeURIComponent(item.recording_url)}`
      : item.recording_url
    : "";

  if (!item?.recording_url) {
    return <span className="radio-missing">No recording URL</span>;
  }

  return (
    <div className="radio-player">
      <audio controls preload="none" src={src} />
      <button onClick={() => setProxy(!proxy)} title="Switch between proxy and original recording URL">
        {proxy ? "Proxy" : "Direct"}
      </button>
      <a href={item.recording_url} target="_blank" rel="noreferrer">Open</a>
    </div>
  );
}

export default function LivePage() {
  const [widgets, setWidgets] = usePersistentWidgets();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [sessionKeyInput, setSessionKeyInput] = useState("latest");
  const [activeSessionKey, setActiveSessionKey] = useState("latest");
  const [meetingKey, setMeetingKey] = useState("latest");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(false);
  const [payloads, setPayloads] = useState({});
  const [errors, setErrors] = useState({});

  async function loadLiveData(nextSession = activeSessionKey) {
    setLoading(true);
    const base = nextSession ? { session_key: nextSession } : { session_key: "latest" };

    const requests = {
      sessions: fetchOpenF1("sessions", nextSession === "latest" ? { session_key: "latest" } : { session_key: nextSession }),
      drivers: fetchOpenF1("drivers", base),
      intervals: fetchOpenF1("intervals", base),
      laps: fetchOpenF1("laps", base),
      stints: fetchOpenF1("stints", base),
      pits: fetchOpenF1("pit", base),
      raceControl: fetchOpenF1("race_control", base),
      weather: fetchOpenF1("weather", base),
      position: fetchOpenF1("position", base),
      carData: fetchOpenF1("car_data", base),
      radio: fetchOpenF1("team_radio", base)
    };

    const settled = await Promise.allSettled(Object.entries(requests).map(async ([key, promise]) => [key, await promise]));
    const nextPayloads = {};
    const nextErrors = {};

    for (const result of settled) {
      if (result.status === "fulfilled") {
        const [key, value] = result.value;
        nextPayloads[key] = value;
        if (!value?.ok) nextErrors[key] = value?.error || `HTTP ${value?.status || "error"}`;
      } else {
        nextErrors.unknown = String(result.reason);
      }
    }

    const sessions = normalizeArray(nextPayloads.sessions);
    const session = sessions[0];
    if (session?.session_key && activeSessionKey === "latest") setActiveSessionKey(String(session.session_key));
    if (session?.meeting_key) setMeetingKey(String(session.meeting_key));

    setPayloads(nextPayloads);
    setErrors(nextErrors);
    setLastUpdated(new Date());
    setLoading(false);
  }

  useEffect(() => {
    loadLiveData("latest");
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => loadLiveData(activeSessionKey), 15000);
    return () => clearInterval(id);
  }, [autoRefresh, activeSessionKey]);

  const drivers = useMemo(() => normalizeArray(payloads.drivers), [payloads.drivers]);
  const driverMap = useMemo(() => {
    const map = new Map();
    for (const driver of drivers) map.set(driver.driver_number, driver);
    return map;
  }, [drivers]);

  const intervals = useMemo(() => latestRows(normalizeArray(payloads.intervals)), [payloads.intervals]);
  const positions = useMemo(() => latestRows(normalizeArray(payloads.position)), [payloads.position]);
  const laps = useMemo(() => latestRows(normalizeArray(payloads.laps)), [payloads.laps]);
  const stints = useMemo(() => latestRows(normalizeArray(payloads.stints)), [payloads.stints]);
  const pits = useMemo(() => normalizeArray(payloads.pits).slice(-20).reverse(), [payloads.pits]);
  const raceControl = useMemo(() => normalizeArray(payloads.raceControl).slice(-20).reverse(), [payloads.raceControl]);
  const weather = useMemo(() => normalizeArray(payloads.weather).slice(-1)[0], [payloads.weather]);
  const carData = useMemo(() => latestRows(normalizeArray(payloads.carData)), [payloads.carData]);
  const radio = useMemo(() => normalizeArray(payloads.radio).slice(-20).reverse(), [payloads.radio]);
  const sessions = normalizeArray(payloads.sessions);
  const session = sessions[0] || {};

  const leaderboard = useMemo(() => {
    const rows = intervals.length ? intervals : positions;
    return rows
      .map((row) => {
        const driver = driverMap.get(row.driver_number) || {};
        const lapRow = laps.find((lapItem) => lapItem.driver_number === row.driver_number) || {};
        const stint = stints.find((item) => item.driver_number === row.driver_number) || {};
        const car = carData.find((item) => item.driver_number === row.driver_number) || {};
        return {
          ...row,
          driver,
          name: driverName(driver),
          team: driver.team_name,
          colour: color(driver.team_colour),
          lap: lapRow,
          stint,
          car
        };
      })
      .sort((a, b) => Number(a.position ?? a.driver_number) - Number(b.position ?? b.driver_number));
  }, [intervals, positions, driverMap, laps, stints, carData]);

  const status = useMemo(() => {
    const all = Object.values(payloads);
    return {
      okCount: all.filter((item) => item?.ok).length,
      failCount: Object.keys(errors).length
    };
  }, [payloads, errors]);

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
            Configurable race-weekend dashboard inspired by f1-dash. It uses OpenF1 when public data is available.
            If live data is blocked or paid, the page keeps working with historical/latest public data and clear fallback states.
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
          <label>Session key</label>
          <input value={sessionKeyInput} onChange={(e) => setSessionKeyInput(e.target.value)} placeholder="latest or session key" />
          <button onClick={applySessionKey}>Load</button>
        </div>
        <WidgetSettings widgets={widgets} setWidgets={setWidgets} />
        <div className="live-meta">
          <span>Active session: <strong>{fmt(activeSessionKey)}</strong></span>
          <span>Meeting: <strong>{fmt(meetingKey)}</strong></span>
          <span>Updated: <strong>{lastUpdated ? lastUpdated.toLocaleTimeString() : "-"}</strong></span>
        </div>
      </section>

      {Object.keys(errors).length > 0 && (
        <section className="live-warning">
          <BadgeInfo size={18} />
          <div>
            <strong>Some live endpoints are unavailable.</strong>
            <p>
              This is expected when OpenF1 blocks real-time data or a session has not started. Historical public data should still load where available.
            </p>
          </div>
        </section>
      )}

      <section className="live-grid">
        <Panel id="session" enabled={widgets.session} title="Session" icon={<Clock3 size={18} />} empty={!session?.session_key && "No session data available."}>
          <div className="live-facts">
            <div><span>Meeting</span><strong>{fmt(session.meeting_key || meetingKey)}</strong></div>
            <div><span>Session</span><strong>{fmt(session.session_name || session.name)}</strong></div>
            <div><span>Type</span><strong>{fmt(session.session_type)}</strong></div>
            <div><span>Start</span><strong>{fmt(session.date_start)}</strong></div>
            <div><span>End</span><strong>{fmt(session.date_end)}</strong></div>
            <div><span>Location</span><strong>{fmt(session.location || session.country_name)}</strong></div>
          </div>
        </Panel>

        <Panel id="leaderboard" enabled={widgets.leaderboard} title="Leaderboard" icon={<Trophy size={18} />} empty={!leaderboard.length && "No interval/position data available for this session."}>
          <div className="live-table">
            <div className="live-row head">
              <span>Pos</span><span>Driver</span><span>Gap</span><span>Lap</span><span>Tyre</span><span>Speed</span>
            </div>
            {leaderboard.slice(0, 24).map((row, index) => (
              <div className="live-row" key={`${row.driver_number}-${index}`}>
                <span>{fmt(row.position || index + 1)}</span>
                <span className="driver-cell"><i style={{ background: row.colour }} />{row.name}</span>
                <span>{fmt(row.interval || row.gap_to_leader || row.gap)}</span>
                <span>{lap(row.lap?.lap_duration)}</span>
                <span>{fmt(row.stint?.compound)}</span>
                <span>{fmt(row.car?.speed)} km/h</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel id="intervals" enabled={widgets.intervals} title="Intervals" icon={<Timer size={18} />} empty={!intervals.length && "No interval feed available."}>
          <div className="compact-list">
            {intervals.slice(0, 20).map((row) => {
              const driver = driverMap.get(row.driver_number);
              return <div key={`${row.driver_number}-interval`}><strong>{driverName(driver)}</strong><span>{fmt(row.interval || row.gap_to_leader || row.gap)}</span></div>;
            })}
          </div>
        </Panel>

        <Panel id="laps" enabled={widgets.laps} title="Lap times" icon={<Flag size={18} />} empty={!laps.length && "No lap data available."}>
          <div className="compact-list">
            {laps.slice(0, 20).map((row) => {
              const driver = driverMap.get(row.driver_number);
              return <div key={`${row.driver_number}-lap`}><strong>{driverName(driver)}</strong><span>{lap(row.lap_duration)} · lap {fmt(row.lap_number)}</span></div>;
            })}
          </div>
        </Panel>

        <Panel id="stints" enabled={widgets.stints} title="Tyres and stints" icon={<Waves size={18} />} empty={!stints.length && "No stint data available."}>
          <div className="compact-list">
            {stints.slice(0, 20).map((row) => {
              const driver = driverMap.get(row.driver_number);
              return <div key={`${row.driver_number}-stint`}><strong>{driverName(driver)}</strong><span>{fmt(row.compound)} · age {fmt(row.tyre_age_at_start)}</span></div>;
            })}
          </div>
        </Panel>

        <Panel id="pits" enabled={widgets.pits} title="Pit stops" icon={<Car size={18} />} empty={!pits.length && "No pit data available."}>
          <div className="compact-list">
            {pits.map((row, index) => {
              const driver = driverMap.get(row.driver_number);
              return <div key={`${row.driver_number}-pit-${index}`}><strong>{driverName(driver)}</strong><span>Lap {fmt(row.lap_number)} · {fmt(row.pit_duration || row.duration)}s</span></div>;
            })}
          </div>
        </Panel>

        <Panel id="weather" enabled={widgets.weather} title="Weather" icon={<CloudRain size={18} />} empty={!weather && "No weather data available."}>
          <div className="live-facts weather">
            <div><span>Air</span><strong>{fmt(weather?.air_temperature)}°C</strong></div>
            <div><span>Track</span><strong>{fmt(weather?.track_temperature)}°C</strong></div>
            <div><span>Humidity</span><strong>{fmt(weather?.humidity)}%</strong></div>
            <div><span>Rain</span><strong>{fmt(weather?.rainfall)}</strong></div>
            <div><span>Wind</span><strong>{fmt(weather?.wind_speed)} km/h</strong></div>
            <div><span>Direction</span><strong>{fmt(weather?.wind_direction)}°</strong></div>
          </div>
        </Panel>

        <Panel id="race-control" enabled={widgets.raceControl} title="Race control" icon={<ShieldAlert size={18} />} empty={!raceControl.length && "No race-control messages available."}>
          <div className="race-control-list">
            {raceControl.map((msg, index) => (
              <article key={`${msg.date}-${index}`}>
                <time>{time(msg.date)}</time>
                <strong>{fmt(msg.category || msg.flag || msg.scope, "Message")}</strong>
                <p>{fmt(msg.message)}</p>
              </article>
            ))}
          </div>
        </Panel>

        <Panel id="telemetry" enabled={widgets.telemetry} title="Car metrics" icon={<Gauge size={18} />} empty={!carData.length && "No car metrics available. Real-time car data may require paid OpenF1 access."}>
          <div className="live-table">
            <div className="live-row head">
              <span>Driver</span><span>Speed</span><span>Gear</span><span>RPM</span><span>DRS</span><span>Brake</span>
            </div>
            {carData.slice(0, 24).map((row) => {
              const driver = driverMap.get(row.driver_number);
              return (
                <div className="live-row" key={`${row.driver_number}-car`}>
                  <span>{driverName(driver)}</span>
                  <span>{fmt(row.speed)} km/h</span>
                  <span>{fmt(row.n_gear)}</span>
                  <span>{fmt(row.rpm)}</span>
                  <span>{fmt(row.drs)}</span>
                  <span>{fmt(row.brake)}</span>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel id="radio" enabled={widgets.radio} title="Team radio" icon={<AudioLines size={18} />} empty={!radio.length && "No radio messages available yet."}>
          <div className="radio-list">
            {radio.map((item, index) => {
              const driver = driverMap.get(item.driver_number);
              return (
                <article key={`${item.date}-${item.driver_number}-${index}`}>
                  <div>
                    <strong>{driverName(driver)}</strong>
                    <span>{time(item.date)}</span>
                  </div>
                  <RadioPlayer item={item} driver={driver} />
                </article>
              );
            })}
          </div>
        </Panel>
      </section>

      <footer className="live-footer">
        OpenF1 historical data is public from 2023 onward. Real-time feeds may require paid OpenF1 access. This page degrades to available public/latest data and does not stream F1 video.
      </footer>
    </main>
  );
}

import { useState, useEffect, useRef, useCallback } from 'react';
import VideoFeed from './components/VideoFeed.jsx';
import EventSidebar from './components/EventSidebar.jsx';
import StatsBar from './components/StatsBar.jsx';
import ZoneEditor from './components/ZoneEditor.jsx';

const WS_URL = 'ws://localhost:8000/ws/stream';
const RECONNECT_DELAY_MS = 3000;
const MAX_EVENTS = 200;

function nowIso() {
  return new Date().toISOString();
}

export default function App() {
  const [wsStatus, setWsStatus] = useState('connecting');
  const [currentFrame, setCurrentFrame] = useState(null);
  const [tracks, setTracks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState({
    fps: 0,
    frame_count: 0,
    uptime_seconds: 0,
    total_alerts: 0,
  });
  const [events, setEvents] = useState([]);
  const [zones, setZones] = useState([]);
  const [activeTab, setActiveTab] = useState('events'); // 'events' | 'zones' | 'settings'

  // Surveillance view toggles
  const [showZones, setShowZones] = useState(true);
  const [showBBoxes, setShowBBoxes] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showFootpoints, setShowFootpoints] = useState(true);
  const [isArmed, setIsArmed] = useState(true);
  const [audioAlerts, setAudioAlerts] = useState(false);

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const seenAlertKeysRef = useRef(new Set());

  // Beep sound generator using Web Audio API for alert sounds
  const playAlertSound = useCallback(() => {
    if (!audioAlerts) return;
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5 note
      osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.25);
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.25);
    } catch {
      // AudioContext not allowed before user interaction
    }
  }, [audioAlerts]);

  // Fetch initial config from backend
  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        if (data.zones) setZones(data.zones);
        if (typeof data.armed === 'boolean') setIsArmed(data.armed);
      }
    } catch (err) {
      console.warn('Could not fetch config:', err);
    }
  }, []);

  // Toggle arming mode
  const handleToggleArm = async () => {
    const nextState = !isArmed;
    setIsArmed(nextState);
    try {
      await fetch('/config/arm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ armed: nextState }),
      });
    } catch (err) {
      console.error('Failed to update armed status:', err);
    }
  };

  // Connect WebSocket stream
  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      fetchConfig();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    ws.onmessage = (evt) => {
      let data;
      try {
        data = JSON.parse(evt.data);
      } catch {
        return;
      }

      const {
        frame,
        tracks: newTracks = [],
        alerts: newAlerts = [],
        stats: newStats = {},
        zones: newZones,
      } = data;

      if (frame !== undefined) setCurrentFrame(frame);
      setTracks(newTracks);
      setAlerts(newAlerts);
      if (newStats) setStats((prev) => ({ ...prev, ...newStats }));
      if (newZones && newZones.length > 0) setZones(newZones);

      // Record any alert to the persistent event log
      if (newAlerts && newAlerts.length > 0) {
        playAlertSound();

        setEvents((prev) => {
          const freshAlerts = [];
          for (const a of newAlerts) {
            // Deduplicate per track and 2-second timestamp window
            const key = `${a.track_id}-${a.type}-${Math.floor(Date.now() / 2000)}`;
            if (!seenAlertKeysRef.current.has(key)) {
              seenAlertKeysRef.current.add(key);
              freshAlerts.push({
                ...a,
                alert_type: a.type || 'intrusion',
                id: `${a.track_id || 'x'}-${a.type}-${nowIso()}`,
                timestamp: a.timestamp || nowIso(),
                isNew: true,
              });
            }
          }

          if (freshAlerts.length === 0) return prev;
          return [...freshAlerts, ...prev].slice(0, MAX_EVENTS);
        });
      }
    };

    ws.onerror = () => {
      // Handled in onclose
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, RECONNECT_DELAY_MS);
    };
  }, [fetchConfig, playAlertSound]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  // Clean deduplication key buffer periodically
  useEffect(() => {
    const timer = setInterval(() => {
      if (seenAlertKeysRef.current.size > 500) {
        seenAlertKeysRef.current.clear();
      }
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  const intrusionAlertCount = events.filter((e) => e.alert_type === 'intrusion').length;
  const areaAlertCount = events.filter((e) => e.alert_type === 'restricted_area').length;

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 overflow-hidden font-sans select-none">
      
      {/* ── Top Navigation Bar ── */}
      <header className="flex items-center justify-between px-5 py-2.5 bg-gray-900/90 border-b border-gray-800 shrink-0 backdrop-blur-md shadow-md z-20">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-bold text-lg">
            🛡️
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-extrabold tracking-tight text-white flex items-center gap-1.5">
                SECURE<span className="text-blue-500">VISION</span> AI
              </h1>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-blue-950 text-blue-300 border border-blue-800">
                v2.0 CV
              </span>
            </div>
            <p className="text-[11px] text-gray-400">
              Autonomous Intrusion & Restricted Zone Security System
            </p>
          </div>
        </div>

        {/* Central HUD Status Indicators */}
        <div className="hidden md:flex items-center gap-4 bg-gray-900/80 px-4 py-1.5 rounded-xl border border-gray-800">
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${isArmed ? 'bg-red-500 animate-ping' : 'bg-gray-500'}`} />
            <span className={`text-xs font-bold font-mono ${isArmed ? 'text-red-400' : 'text-gray-400'}`}>
              {isArmed ? 'ARMED (24/7 DETECTION)' : 'DISARMED'}
            </span>
          </div>
          <span className="text-gray-700">|</span>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-400">Model:</span>
            <span className="font-mono font-semibold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
              YOLOX-Nano ONNX
            </span>
          </div>
        </div>

        {/* Right Status Controls */}
        <div className="flex items-center gap-3">
          {/* Audio toggle button */}
          <button
            onClick={() => setAudioAlerts(!audioAlerts)}
            className={`p-1.5 rounded-lg border text-xs flex items-center gap-1.5 transition-colors ${
              audioAlerts 
                ? 'bg-amber-950/60 border-amber-700 text-amber-300' 
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200'
            }`}
            title="Toggle Alarm Chime on Intrusion"
          >
            <span>{audioAlerts ? '🔔 Sound ON' : '🔕 Sound OFF'}</span>
          </button>

          {/* Connection Status Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-900 border border-gray-800">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                wsStatus === 'connected'
                  ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]'
                  : wsStatus === 'connecting'
                  ? 'bg-amber-400 animate-pulse'
                  : 'bg-rose-500'
              }`}
            />
            <span className="text-xs font-mono font-medium text-gray-300 capitalize">
              {wsStatus}
            </span>
          </div>
        </div>
      </header>

      {/* ── Main Viewport ── */}
      <main className="flex flex-1 overflow-hidden">
        
        {/* Left: Live Video & Controls */}
        <section className="flex flex-col flex-1 min-w-0 p-3.5 gap-3">
          
          {/* Top Camera Status Toolbar */}
          <div className="flex items-center justify-between bg-gray-900/60 px-3 py-2 rounded-xl border border-gray-800">
            <div className="flex items-center gap-3 text-xs">
              <span className="font-bold text-gray-300 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                PRIMARY OPTICAL FEED
              </span>
              <span className="text-gray-600">/</span>
              <span className="font-mono text-gray-400">
                {tracks.length} Target{tracks.length !== 1 ? 's' : ''} in View
              </span>
            </div>

            {/* Video Overlay View Toggles */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setShowZones(!showZones)}
                className={`px-2 py-1 text-[11px] font-semibold rounded-md transition-colors border ${
                  showZones 
                    ? 'bg-red-950/70 border-red-800 text-red-300' 
                    : 'bg-gray-800 border-gray-700 text-gray-500 hover:text-gray-300'
                }`}
              >
                🗺️ Zones
              </button>
              <button
                onClick={() => setShowBBoxes(!showBBoxes)}
                className={`px-2 py-1 text-[11px] font-semibold rounded-md transition-colors border ${
                  showBBoxes 
                    ? 'bg-blue-950/70 border-blue-800 text-blue-300' 
                    : 'bg-gray-800 border-gray-700 text-gray-500 hover:text-gray-300'
                }`}
              >
                📦 Boxes
              </button>
              <button
                onClick={() => setShowFootpoints(!showFootpoints)}
                className={`px-2 py-1 text-[11px] font-semibold rounded-md transition-colors border ${
                  showFootpoints 
                    ? 'bg-emerald-950/70 border-emerald-800 text-emerald-300' 
                    : 'bg-gray-800 border-gray-700 text-gray-500 hover:text-gray-300'
                }`}
              >
                🎯 Foot-points
              </button>
            </div>
          </div>

          {/* Live Video Feed Canvas Component */}
          <div className="flex-1 min-h-0 bg-black rounded-xl border border-gray-800 shadow-2xl overflow-hidden relative flex items-center justify-center">
            <VideoFeed
              frame={currentFrame}
              tracks={tracks}
              alerts={alerts}
              zones={zones}
              showZones={showZones}
              showBBoxes={showBBoxes}
              showLabels={showLabels}
              showFootpoints={showFootpoints}
            />
          </div>

          {/* Live Status & Metric Strip */}
          <StatsBar
            stats={stats}
            totalEvents={events.length}
            activeTracks={tracks.length}
            armed={isArmed}
            onToggleArm={handleToggleArm}
          />
        </section>

        {/* Right Sidebar: Security Event Log & Zone Management */}
        <aside className="w-84 xl:w-96 flex flex-col border-l border-gray-800 bg-gray-900/95 shrink-0 z-10 shadow-2xl">
          {/* Tab Selection */}
          <div className="flex border-b border-gray-800 bg-gray-900/60">
            <button
              onClick={() => setActiveTab('events')}
              className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all border-b-2 ${
                activeTab === 'events'
                  ? 'border-blue-500 text-blue-400 bg-blue-950/20'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
              }`}
            >
              <span>🚨 Live Alerts</span>
              {events.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-red-600 text-white font-extrabold">
                  {events.length}
                </span>
              )}
            </button>
            
            <button
              onClick={() => setActiveTab('zones')}
              className={`flex-1 py-3 text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2 transition-all border-b-2 ${
                activeTab === 'zones'
                  ? 'border-amber-500 text-amber-400 bg-amber-950/20'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
              }`}
            >
              <span>🗺️ Restricted Zones</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-gray-800 text-gray-400">
                {zones.length}
              </span>
            </button>
          </div>

          {/* Active Tab Panel */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'events' ? (
              <EventSidebar
                events={events}
                onClear={() => setEvents([])}
              />
            ) : (
              <ZoneEditor
                zones={zones}
                onUpdateZones={setZones}
              />
            )}
          </div>
        </aside>

      </main>
    </div>
  );
}

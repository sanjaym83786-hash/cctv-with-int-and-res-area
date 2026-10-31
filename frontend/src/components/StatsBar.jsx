/* ─────────────────────────────────────────────────────────────────────────── */
/*  StatsBar                                                                   */
/* ─────────────────────────────────────────────────────────────────────────── */

function fpsColor(fps) {
  if (fps >= 24) return 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40';
  if (fps >= 15) return 'text-amber-400 bg-amber-950/40 border-amber-800/40';
  return 'text-rose-400 bg-rose-950/40 border-rose-800/40';
}

function formatUptime(secs) {
  if (!secs || secs < 0) return '00:00:00';
  const h = String(Math.floor(secs / 3600)).padStart(2, '0');
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const s = String(Math.floor(secs % 60)).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export default function StatsBar({ 
  stats = {}, 
  totalEvents = 0, 
  activeTracks = 0,
  armed = true,
  onToggleArm,
}) {
  const {
    fps = 0,
    frame_count = 0,
    uptime_seconds = 0,
    total_alerts = 0,
  } = stats;

  return (
    <div className="shrink-0 bg-gray-800/60 backdrop-blur-md rounded-xl p-3 border border-gray-700/60 shadow-lg select-none">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
        
        {/* Arm / Disarm Status Card */}
        <div 
          onClick={onToggleArm}
          className={`cursor-pointer rounded-lg p-2.5 border transition-all duration-200 flex items-center justify-between ${
            armed 
              ? 'bg-red-950/40 border-red-700/50 hover:bg-red-900/50 shadow-sm' 
              : 'bg-gray-800/80 border-gray-700 hover:bg-gray-700/60'
          }`}
          title="Click to toggle system arming"
        >
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              System State
            </div>
            <div className={`text-sm font-extrabold flex items-center gap-1.5 mt-0.5 ${
              armed ? 'text-red-400' : 'text-gray-400'
            }`}>
              <span className={`w-2 h-2 rounded-full ${armed ? 'bg-red-500 animate-ping' : 'bg-gray-500'}`} />
              {armed ? 'ARMED 24/7' : 'DISARMED'}
            </div>
          </div>
          <span className="text-xl">{armed ? '🚨' : '🛡️'}</span>
        </div>

        {/* FPS Badge */}
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Stream Rate
            </div>
            <div className={`text-sm font-mono font-bold mt-0.5 ${
              fps >= 20 ? 'text-emerald-400' : fps >= 10 ? 'text-amber-400' : 'text-rose-400'
            }`}>
              {fps.toFixed(1)} FPS
            </div>
          </div>
          <span className="text-xl">⚡</span>
        </div>

        {/* Active Targets */}
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Active Targets
            </div>
            <div className="text-sm font-mono font-bold text-cyan-400 mt-0.5">
              {activeTracks} {activeTracks === 1 ? 'person' : 'persons'}
            </div>
          </div>
          <span className="text-xl">👤</span>
        </div>

        {/* Total Captured Alerts */}
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Total Alerts
            </div>
            <div className="text-sm font-mono font-bold text-red-400 mt-0.5">
              {(total_alerts || totalEvents).toLocaleString()}
            </div>
          </div>
          <span className="text-xl">🔔</span>
        </div>

        {/* Processed Frames */}
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Processed
            </div>
            <div className="text-sm font-mono font-bold text-blue-400 mt-0.5">
              {frame_count.toLocaleString()} frames
            </div>
          </div>
          <span className="text-xl">🖼️</span>
        </div>

        {/* System Uptime */}
        <div className="bg-gray-900/60 rounded-lg p-2.5 border border-gray-800 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              Uptime
            </div>
            <div className="text-sm font-mono font-bold text-purple-400 mt-0.5">
              {formatUptime(uptime_seconds)}
            </div>
          </div>
          <span className="text-xl">⏱️</span>
        </div>

      </div>
    </div>
  );
}

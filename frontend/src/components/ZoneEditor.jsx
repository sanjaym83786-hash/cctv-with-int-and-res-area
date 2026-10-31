import { useState } from 'react';

export default function ZoneEditor({ 
  zones = [], 
  onUpdateZones,
  loiterThreshold = 3,
}) {
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [selectedZoneIdx, setSelectedZoneIdx] = useState(0);

  const handleReset = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      const defaultZones = [
        {
          name: "Perimeter Security Zone",
          polygon: [[50, 50], [590, 50], [590, 430], [50, 430]],
          loiter_seconds: 3.0,
        }
      ];
      const res = await fetch('/api/config/zones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zones: defaultZones }),
      });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      if (onUpdateZones) onUpdateZones(data.zones);
      setFeedback({ ok: true, message: 'Restricted zones reset to default perimeter!' });
    } catch (err) {
      setFeedback({ ok: false, message: `Failed: ${err.message}` });
    } finally {
      setLoading(false);
      setTimeout(() => setFeedback(null), 4000);
    }
  };

  const activeZone = zones[selectedZoneIdx] || zones[0];

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-200 p-4 select-none overflow-y-auto">
      {/* ── Title ── */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-800">
        <div>
          <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <span>🛡️</span> Restricted Area Zones
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Real-time polygonal containment & loitering detector
          </p>
        </div>
        <button
          onClick={handleReset}
          disabled={loading}
          className="px-3 py-1.5 bg-blue-600/80 hover:bg-blue-600 active:scale-95 text-white text-xs font-semibold rounded-lg shadow transition-all duration-150 flex items-center gap-1.5 disabled:opacity-50"
        >
          {loading ? 'Updating...' : 'Reset Default'}
        </button>
      </div>

      {feedback && (
        <div className={`p-3 rounded-lg mb-3 text-xs font-medium border flex items-center gap-2 ${
          feedback.ok ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300' : 'bg-red-950/60 border-red-800 text-red-300'
        }`}>
          <span>{feedback.ok ? '✅' : '❌'}</span>
          <span>{feedback.message}</span>
        </div>
      )}

      {/* ── Active Zone List ── */}
      <div className="space-y-3 mb-5">
        <label className="text-xs font-bold text-gray-400 uppercase tracking-wider block">
          Configured Zones ({zones.length})
        </label>
        
        {zones.length === 0 ? (
          <div className="p-4 rounded-xl bg-gray-800/40 border border-dashed border-gray-700 text-center text-xs text-gray-400">
            No restricted zones currently defined.
          </div>
        ) : (
          zones.map((zone, idx) => {
            const isSelected = selectedZoneIdx === idx;
            const pts = zone.polygon || [];

            return (
              <div
                key={zone.name || idx}
                onClick={() => setSelectedZoneIdx(idx)}
                className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected 
                    ? 'bg-gray-800/90 border-blue-500 shadow-md ring-1 ring-blue-500' 
                    : 'bg-gray-800/40 border-gray-700/60 hover:bg-gray-800/70'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse"></span>
                    <span className="font-bold text-sm text-white">
                      {zone.name || `Zone #${idx + 1}`}
                    </span>
                  </div>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-gray-900 text-amber-300 font-semibold border border-amber-800/40">
                    ⏱ {zone.loiter_seconds || loiterThreshold}s loiter
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs text-gray-400 bg-gray-900/60 p-2 rounded-lg border border-gray-800/80">
                  <div>
                    <span className="text-gray-500">Geometry:</span>{' '}
                    <span className="text-gray-200 font-mono font-medium">{pts.length} vertices</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Test method:</span>{' '}
                    <span className="text-emerald-400 font-mono font-medium">Foot-point</span>
                  </div>
                </div>

                {isSelected && pts.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-gray-700/60">
                    <div className="text-[11px] font-mono text-gray-400 mb-1">
                      Coordinates (X, Y):
                    </div>
                    <div className="grid grid-cols-2 gap-1 text-[10px] font-mono text-gray-300 max-h-24 overflow-y-auto">
                      {pts.map((pt, pIdx) => (
                        <div key={pIdx} className="bg-gray-900 px-2 py-1 rounded">
                          P{pIdx + 1}: [{Math.round(pt[0])}, {Math.round(pt[1])}]
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* ── Detection Logic Info ── */}
      <div className="mt-auto bg-gray-800/40 border border-gray-700/60 rounded-xl p-3.5 space-y-2">
        <h4 className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
          <span>ℹ️</span> How Breach Detection Works
        </h4>
        <ul className="text-xs text-gray-400 space-y-1.5 list-disc list-inside">
          <li>Ray-casting mathematical test checks if the person's feet are within polygon boundaries.</li>
          <li>If an intruder stays inside beyond the dwell threshold, a breach alert is triggered.</li>
          <li>Cooldown ensures the event log is not spammed with duplicate triggers.</li>
        </ul>
      </div>
    </div>
  );
}

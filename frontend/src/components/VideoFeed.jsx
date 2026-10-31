import { useRef, useEffect, useState } from 'react';

const COLORS = {
  trackNormal:  '#22c55e', // green-500
  trackAlerted: '#ef4444', // red-500
  trackLoiter:  '#f59e0b', // amber-500
  zone:         'rgba(239, 68, 68, 0.16)',
  zoneBorder:   '#ef4444',
  zoneLabel:    '#fca5a5',
  labelBg:      'rgba(15, 23, 42, 0.85)',
  confidence:   '#94a3b8',
};

export default function VideoFeed({ 
  frame, 
  tracks = [], 
  alerts = [], 
  zones = [],
  showZones = true,
  showBBoxes = true,
  showLabels = true,
  showFootpoints = true,
}) {
  const containerRef = useRef(null);
  const imgRef = useRef(null);
  const canvasRef = useRef(null);
  const [fullscreen, setFullscreen] = useState(false);

  // Set canvas resolution to match image natural resolution
  const renderOverlay = () => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas || !img.complete || img.naturalWidth === 0) return;

    if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
    }

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // ── 1. Draw Zones ──
    if (showZones && zones) {
      zones.forEach((zone, idx) => {
        const pts = zone.polygon;
        if (!pts || pts.length < 3) return;

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }
        ctx.closePath();

        // Semi-transparent hazard fill
        ctx.fillStyle = COLORS.zone;
        ctx.fill();

        // Dashed glowing border
        ctx.strokeStyle = COLORS.zoneBorder;
        ctx.lineWidth = 2.5;
        ctx.setLineDash([8, 4]);
        ctx.stroke();

        // Zone Name Tag with gradient
        if (pts.length > 0) {
          const vx = pts[0][0];
          const vy = pts[0][1];
          const label = `⚠️ ${zone.name || `Zone ${idx + 1}`}`;
          ctx.font = 'bold 13px ui-sans-serif, system-ui';
          const tw = ctx.measureText(label).width;

          ctx.fillStyle = 'rgba(239, 68, 68, 0.85)';
          ctx.beginPath();
          if (ctx.roundRect) {
            ctx.roundRect(vx, Math.max(0, vy - 24), tw + 14, 22, 4);
          } else {
            ctx.rect(vx, Math.max(0, vy - 24), tw + 14, 22);
          }
          ctx.fill();

          ctx.fillStyle = '#ffffff';
          ctx.fillText(label, vx + 7, Math.max(16, vy - 8));
        }
        ctx.restore();
      });
    }

    // ── 2. Draw Track BBoxes & Labels ──
    if (showBBoxes && tracks) {
      const alertedTrackIds = new Set(alerts.map((a) => a.track_id));

      tracks.forEach((track) => {
        const [x1, y1, x2, y2] = track.bbox.map(Number);
        const w = x2 - x1;
        const h = y2 - y1;
        const isAlerted = alertedTrackIds.has(track.track_id);
        const isPerson = (track.label || track.class) === 'person';

        const strokeColor = isAlerted 
          ? COLORS.trackAlerted 
          : isPerson 
          ? COLORS.trackNormal 
          : COLORS.trackLoiter;

        ctx.save();

        // Outer glow on alert
        if (isAlerted) {
          ctx.shadowColor = 'rgba(239, 68, 68, 0.8)';
          ctx.shadowBlur = 12;
        }

        // Draw bounding box with rounded corners
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = isAlerted ? 3.5 : 2;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x1, y1, w, h, 6);
        } else {
          ctx.rect(x1, y1, w, h);
        }
        ctx.stroke();
        ctx.shadowBlur = 0; // reset

        // Draw corner brackets for tactical sci-fi aesthetic
        const cl = Math.min(16, w / 4, h / 4);
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = isAlerted ? 4 : 3;

        // Top-left
        ctx.beginPath();
        ctx.moveTo(x1, y1 + cl);
        ctx.lineTo(x1, y1);
        ctx.lineTo(x1 + cl, y1);
        ctx.stroke();

        // Top-right
        ctx.beginPath();
        ctx.moveTo(x2 - cl, y1);
        ctx.lineTo(x2, y1);
        ctx.lineTo(x2, y1 + cl);
        ctx.stroke();

        // Bottom-left
        ctx.beginPath();
        ctx.moveTo(x1, y2 - cl);
        ctx.lineTo(x1, y2);
        ctx.lineTo(x1 + cl, y2);
        ctx.stroke();

        // Bottom-right
        ctx.beginPath();
        ctx.moveTo(x2 - cl, y2);
        ctx.lineTo(x2, y2);
        ctx.lineTo(x2, y2 - cl);
        ctx.stroke();

        // ── Bottom-center foot-point test indicator ──
        if (showFootpoints) {
          const footX = (x1 + x2) / 2;
          const footY = y2;
          ctx.beginPath();
          ctx.arc(footX, footY, 4, 0, Math.PI * 2);
          ctx.fillStyle = isAlerted ? '#ef4444' : '#22c55e';
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        // ── Track Label Badge ──
        if (showLabels) {
          const labelText = `${isAlerted ? '🚨 ' : ''}${track.label || 'target'} #${track.track_id}`;
          const confText = track.conf ? `${Math.round(track.conf * 100)}%` : '';
          const fullText = confText ? `${labelText} (${confText})` : labelText;

          ctx.font = 'bold 12px ui-monospace, SFMono-Regular, Menlo, monospace';
          const tw = ctx.measureText(fullText).width;
          const badgeH = 22;
          const badgeY = Math.max(0, y1 - badgeH - 3);

          ctx.fillStyle = isAlerted ? 'rgba(239, 68, 68, 0.95)' : COLORS.labelBg;
          ctx.beginPath();
          if (ctx.roundRect) {
            ctx.roundRect(x1, badgeY, tw + 12, badgeH, 4);
          } else {
            ctx.rect(x1, badgeY, tw + 12, badgeH);
          }
          ctx.fill();

          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = 1;
          ctx.stroke();

          ctx.fillStyle = '#ffffff';
          ctx.fillText(fullText, x1 + 6, badgeY + 15);
        }

        ctx.restore();
      });
    }
  };

  useEffect(() => {
    renderOverlay();
  }, [frame, tracks, alerts, zones, showZones, showBBoxes, showLabels, showFootpoints]);

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(console.error);
      setFullscreen(true);
    } else {
      document.exitFullscreen().catch(console.error);
      setFullscreen(false);
    }
  };

  return (
    <div 
      ref={containerRef}
      className={`relative w-full h-full flex items-center justify-center bg-black overflow-hidden select-none ${
        fullscreen ? 'p-0' : ''
      }`}
    >
      {/* Radar sweeping scanline effect */}
      <div className="radar-line" />

      {/* Live Video Feed Image */}
      {frame ? (
        <div className="relative inline-block max-w-full max-h-full">
          <img
            ref={imgRef}
            src={`data:image/jpeg;base64,${frame}`}
            alt="Surveillance Feed"
            onLoad={renderOverlay}
            className="block max-w-full max-h-[calc(100vh-180px)] object-contain rounded-lg shadow-2xl"
          />
          <canvas
            ref={canvasRef}
            className="absolute top-0 left-0 w-full h-full pointer-events-none rounded-lg"
          />
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center p-8 text-center text-gray-500">
          <div className="w-16 h-16 mb-4 rounded-full border-2 border-dashed border-gray-700 animate-spin flex items-center justify-center">
            <span className="text-xl">📹</span>
          </div>
          <p className="text-sm font-medium text-gray-400">Waiting for live camera stream...</p>
          <p className="text-xs text-gray-600 mt-1">Connecting to OpenCV video pipeline on port 8000</p>
        </div>
      )}

      {/* Floating HUD Camera Watermark / Live Badge */}
      <div className="absolute top-3 left-3 flex items-center gap-2 bg-gray-900/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-700/60 shadow-lg">
        <span className="flex h-2.5 w-2.5 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span>
        </span>
        <span className="text-xs font-mono font-bold tracking-wider text-red-400 uppercase">
          LIVE FEED
        </span>
        <span className="text-gray-500 text-xs">|</span>
        <span className="text-xs font-mono text-gray-300">
          CAM-01
        </span>
      </div>

      {/* Top right quick controls */}
      <div className="absolute top-3 right-3 flex items-center gap-2 bg-gray-900/80 backdrop-blur-md px-2 py-1.5 rounded-lg border border-gray-700/60 shadow-lg">
        <button
          onClick={toggleFullscreen}
          title="Toggle Fullscreen"
          className="p-1 text-gray-300 hover:text-white hover:bg-gray-700/60 rounded transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0-4l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
        </button>
      </div>

      {/* Bottom overlay: Detection summary pills */}
      {tracks && tracks.length > 0 && (
        <div className="absolute bottom-3 left-3 flex items-center gap-2 bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-gray-700/60 shadow-lg">
          <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
            {tracks.length} Object{tracks.length !== 1 ? 's' : ''} Tracked
          </span>
          {alerts.length > 0 && (
            <>
              <span className="text-gray-600">|</span>
              <span className="text-xs font-bold text-red-400 flex items-center gap-1 alert-pulse px-2 py-0.5 bg-red-950/60 rounded border border-red-800/40">
                🚨 {alerts.length} Active Alert{alerts.length !== 1 ? 's' : ''}
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}

import { useRef, useEffect, useState } from 'react';

/* ─────────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                                    */
/* ─────────────────────────────────────────────────────────────────────────── */

function formatTime(ts) {
  const d = ts ? new Date(ts) : new Date();
  if (isNaN(d)) return '--:--:--';
  return d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatDate(ts) {
  const d = ts ? new Date(ts) : new Date();
  if (isNaN(d)) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function alertMeta(alertType) {
  switch (alertType) {
    case 'restricted_area':
      return {
        icon: '⚠️',
        iconBg: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
        badgeClass: 'bg-amber-950/80 text-amber-300 border border-amber-600/50',
        borderAccent: 'border-l-4 border-l-amber-500',
        label: 'Area Breach',
        severity: 'MEDIUM',
      };
    case 'intrusion':
    default:
      return {
        icon: '🚨',
        iconBg: 'bg-red-500/20 text-red-400 border border-red-500/30',
        badgeClass: 'bg-red-950/80 text-red-300 border border-red-600/50',
        borderAccent: 'border-l-4 border-l-red-500',
        label: 'Person Intrusion',
        severity: 'CRITICAL',
      };
  }
}

/* ─────────────────────────────────────────────────────────────────────────── */
/*  EventCard                                                                  */
/* ─────────────────────────────────────────────────────────────────────────── */

function EventCard({ event, onSelect, isSelected }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const meta = alertMeta(event.alert_type);

  return (
    <article
      onClick={() => onSelect && onSelect(event)}
      className={`mx-3 my-2 p-3 rounded-xl transition-all duration-200 cursor-pointer text-left
        ${meta.borderAccent}
        ${isSelected 
          ? 'bg-gray-800 ring-2 ring-blue-500 shadow-lg' 
          : 'bg-gray-800/70 hover:bg-gray-800/95 border border-gray-700/60 shadow-sm'}
        ${mounted ? 'event-slide-in' : 'opacity-0'}
        ${event.isNew ? 'alert-new' : ''}
      `}
    >
      {/* ── Top row: Badge + Severity + Timestamp ── */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-6 h-6 rounded-lg flex items-center justify-center text-xs shrink-0 ${meta.iconBg}`}>
            {meta.icon}
          </span>
          <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider ${meta.badgeClass}`}>
            {meta.label}
          </span>
          <span className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-semibold ${
            meta.severity === 'CRITICAL' ? 'text-red-400 bg-red-950/50' : 'text-amber-400 bg-amber-950/50'
          }`}>
            {meta.severity}
          </span>
        </div>
        <div className="text-right">
          <time className="text-xs font-mono font-medium text-gray-300 block tabular-nums">
            {formatTime(event.timestamp)}
          </time>
          <span className="text-[10px] text-gray-500 block">
            {formatDate(event.timestamp)}
          </span>
        </div>
      </div>

      {/* ── Event Details ── */}
      <div className="space-y-1.5 bg-gray-900/60 p-2.5 rounded-lg border border-gray-800/80">
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
            Target
          </span>
          <span className="font-mono font-semibold text-blue-300 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-800/50">
            Track #{event.track_id ?? 'Unknown'}
          </span>
        </div>

        {event.zone_name && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              Restricted Zone
            </span>
            <span className="font-medium text-amber-200">
              {event.zone_name}
            </span>
          </div>
        )}

        {event.alert_type === 'restricted_area' && event.dwell_seconds !== undefined && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-400"></span>
              Loiter Duration
            </span>
            <span className="font-mono font-bold text-orange-400">
              ⏱ {Number(event.dwell_seconds).toFixed(1)}s
            </span>
          </div>
        )}

        {event.message && (
          <p className="text-xs text-gray-300 mt-1.5 pt-1.5 border-t border-gray-800 leading-relaxed font-sans">
            {event.message}
          </p>
        )}
      </div>
    </article>
  );
}

/* ─────────────────────────────────────────────────────────────────────────── */
/*  EventSidebar                                                               */
/* ─────────────────────────────────────────────────────────────────────────── */

export default function EventSidebar({ 
  events = [], 
  onClear,
  filter = 'all',
  onFilterChange,
  onExport,
}) {
  const [activeFilter, setActiveFilter] = useState(filter);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const listRef = useRef(null);

  const handleFilter = (f) => {
    setActiveFilter(f);
    if (onFilterChange) onFilterChange(f);
  };

  const filteredEvents = events.filter((e) => {
    if (activeFilter === 'intrusion' && e.alert_type !== 'intrusion') return false;
    if (activeFilter === 'restricted_area' && e.alert_type !== 'restricted_area') return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const txt = `${e.alert_type} track ${e.track_id} ${e.zone_name || ''} ${e.message || ''}`.toLowerCase();
      return txt.includes(q);
    }
    return true;
  });

  const intrusionCount = events.filter((e) => e.alert_type === 'intrusion').length;
  const restrictedCount = events.filter((e) => e.alert_type === 'restricted_area').length;

  return (
    <div className="flex flex-col h-full bg-gray-900 select-none">
      {/* ── Header ── */}
      <div className="px-4 py-3 border-b border-gray-800 bg-gray-800/40">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            </span>
            <h2 className="text-sm font-bold tracking-wide text-white uppercase flex items-center gap-2">
              Security Event Log
            </h2>
            <span className="px-2 py-0.5 text-[11px] font-mono font-bold bg-gray-700 text-gray-200 rounded-full">
              {events.length}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            {events.length > 0 && onClear && (
              <button
                onClick={onClear}
                title="Clear all events"
                className="px-2.5 py-1 text-xs font-medium text-gray-400 hover:text-red-300 hover:bg-red-950/40 rounded-md transition-colors border border-gray-700/60"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* ── Search Bar ── */}
        <div className="relative mb-2.5">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter by track ID, zone or keyword..."
            className="w-full bg-gray-900/90 text-xs text-gray-200 placeholder-gray-500 rounded-lg pl-8 pr-3 py-1.5 border border-gray-700 focus:outline-none focus:border-blue-500 transition-colors"
          />
          <svg className="w-3.5 h-3.5 text-gray-500 absolute left-2.5 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-200 text-xs"
            >
              ×
            </button>
          )}
        </div>

        {/* ── Category Filter Pills ── */}
        <div className="grid grid-cols-3 gap-1 bg-gray-900/80 p-1 rounded-lg border border-gray-800">
          <button
            onClick={() => handleFilter('all')}
            className={`py-1 text-xs font-semibold rounded-md transition-all ${
              activeFilter === 'all'
                ? 'bg-blue-600 text-white shadow'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            All ({events.length})
          </button>
          <button
            onClick={() => handleFilter('intrusion')}
            className={`py-1 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1 ${
              activeFilter === 'intrusion'
                ? 'bg-red-600 text-white shadow'
                : 'text-gray-400 hover:text-red-300'
            }`}
          >
            <span>🚨</span>
            <span>Intrusion ({intrusionCount})</span>
          </button>
          <button
            onClick={() => handleFilter('restricted_area')}
            className={`py-1 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1 ${
              activeFilter === 'restricted_area'
                ? 'bg-amber-600 text-white shadow'
                : 'text-gray-400 hover:text-amber-300'
            }`}
          >
            <span>⚠️</span>
            <span>Breach ({restrictedCount})</span>
          </button>
        </div>
      </div>

      {/* ── Scrollable list of events ── */}
      <div ref={listRef} className="flex-1 overflow-y-auto divide-y divide-gray-800/30">
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center px-6">
            <div className="w-14 h-14 rounded-2xl bg-gray-800/80 border border-gray-700/60 flex items-center justify-center mb-3 text-2xl text-gray-500 shadow-inner">
              🛡️
            </div>
            <p className="text-sm font-semibold text-gray-300 mb-1">
              {events.length === 0 ? 'Surveillance Active — No Incidents' : 'No matching events found'}
            </p>
            <p className="text-xs text-gray-500 max-w-xs leading-relaxed">
              {events.length === 0 
                ? 'When a person or intrusion is captured by the live camera feed, real-time alerts appear here immediately.'
                : 'Try adjusting your search query or filter selection.'}
            </p>
          </div>
        ) : (
          filteredEvents.map((evt, idx) => (
            <EventCard 
              key={evt.id || `${evt.track_id}-${evt.timestamp}-${idx}`} 
              event={evt} 
              onSelect={setSelectedEvent}
              isSelected={selectedEvent && selectedEvent.id === evt.id}
            />
          ))
        )}
      </div>

      {/* ── Summary Footer ── */}
      <div className="px-4 py-2 bg-gray-800/50 border-t border-gray-800 text-[11px] text-gray-400 flex items-center justify-between">
        <span>Autoscrolling latest detections</span>
        <span className="font-mono text-gray-400">
          Showing {filteredEvents.length} of {events.length}
        </span>
      </div>
    </div>
  );
}

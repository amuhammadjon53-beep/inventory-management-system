import React, { useMemo, useState, useRef, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { format, startOfMonth, endOfMonth, eachDayOfInterval,
         getDay, addMonths, subMonths,
         startOfWeek, addWeeks } from 'date-fns';

// ─── Intensity ────────────────────────────────────────────────────────────────

const getIntensityOpacity = (value, maxValue) => {
  if (value === 0 || !maxValue) return '0.08';
  const intensity = value / maxValue;
  if (intensity >= 0.9) return '1';
  if (intensity >= 0.7) return '0.85';
  if (intensity >= 0.5) return '0.65';
  if (intensity >= 0.3) return '0.45';
  if (intensity >= 0.1) return '0.25';
  return '0.12';
};

// ─── Portal Tooltip ───────────────────────────────────────────────────────────

const PortalTooltip = ({ x, y, label, value }) => {
  if (x == null) return null;
  return ReactDOM.createPortal(
    <div
      style={{
        position: 'fixed',
        left: x,
        top: y - 12,
        transform: 'translate(-50%, -100%)',
        backgroundColor: '#1a1a1a',
        padding: '7px 13px',
        borderRadius: '8px',
        border: '1px solid rgba(170, 0, 255, 0.45)',
        boxShadow: '0 6px 20px rgba(0,0,0,0.7)',
        color: '#fff',
        fontSize: '11px',
        whiteSpace: 'nowrap',
        zIndex: 2147483647,
        pointerEvents: 'none',
        userSelect: 'none',
      }}
    >
      <div style={{ fontWeight: '700', color: '#cc44ff', marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: '10px', color: '#bbb' }}>{value.toLocaleString()}</div>
    </div>,
    document.body
  );
};

// ─── Heatmap Square ───────────────────────────────────────────────────────────

const HeatmapSquare = ({ value, tooltipLabel, maxValue, onClick }) => {
  const [tip, setTip] = useState(null);
  const opacity = getIntensityOpacity(value, maxValue);
  const isHovered = tip !== null;

  return (
    <>
      <div
        style={{
          position: 'relative',
          width: '100%',
          paddingBottom: '100%',
          cursor: 'pointer',
        }}
        onMouseMove={e => setTip({ x: e.clientX, y: e.clientY })}
        onMouseLeave={() => setTip(null)}
        onClick={onClick}
      >
        <div
          style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: '#aa00ff',
            opacity,
            borderRadius: '5px',
            transition: 'transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease',
            transform: isHovered ? 'scale(1.15)' : 'scale(1)',
            boxShadow: isHovered ? '0 0 10px rgba(170,0,255,0.55)' : 'none',
            border: isHovered
              ? '1px solid rgba(170,0,255,0.7)'
              : '1px solid rgba(255,255,255,0.07)',
          }}
        />
      </div>
      {tip && (
        <PortalTooltip x={tip.x} y={tip.y} label={tooltipLabel} value={value} />
      )}
    </>
  );
};

// ─── Nav button ───────────────────────────────────────────────────────────────

const NavBtn = ({ onClick, children }) => (
  <button
    onClick={onClick}
    style={{
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '8px',
      padding: '8px 16px',
      color: '#fff',
      cursor: 'pointer',
      transition: 'background 0.2s ease',
      fontSize: '14px',
    }}
    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.12)')}
    onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
  >
    {children}
  </button>
);

// ─── Weekly Hourly View ───────────────────────────────────────────────────────

const WeeklyHourlyView = ({ data, maxValue, onDataPointClick }) => {
  const [weekOffset, setWeekOffset] = useState(0);
  const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const hours = Array.from({ length: 12 }, (_, i) => i);
  const periods = ['00-11', '12-23'];

  const baseDate = new Date();
  const currentWeekStart = startOfWeek(baseDate, { weekStartsOn: 1 });
  const weekStart = addWeeks(currentWeekStart, weekOffset);
  const weekEnd = new Date(weekStart.getTime() + 6 * 86400000);
  const weekLabel = `${format(weekStart, 'MMM d')} – ${format(weekEnd, 'MMM d, yyyy')}`;
  const weekDates = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart);
    d.setDate(weekStart.getDate() + i);
    return d;
  });

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px', padding:'0 10px' }}>
        <NavBtn onClick={() => setWeekOffset(w => w - 1)}>←</NavBtn>
        <h2 style={{ margin:0, fontSize:'18px', fontWeight:'600', color:'#fff', letterSpacing:'0.5px' }}>{weekLabel}</h2>
        <NavBtn onClick={() => setWeekOffset(w => w + 1)}>→</NavBtn>
      </div>
      <div style={{ overflowX:'auto' }}>
        <div style={{ display:'inline-block', minWidth:'100%' }}>
          <div style={{ display:'flex', marginBottom:'12px', paddingLeft:'60px' }}>
            {weekDays.map(day => (
              <div key={day} style={{ flex:1, textAlign:'center', fontSize:'12px', fontWeight:'600', color:'#aaa', textTransform:'uppercase', letterSpacing:'0.5px' }}>
                {day}
              </div>
            ))}
          </div>
          {periods.map((period, periodIndex) => (
            <div key={period} style={{ display:'flex', marginBottom: periodIndex === 0 ? '8px' : 0 }}>
              <div style={{ width:'50px', fontSize:'11px', fontWeight:'500', color:'#666', display:'flex', alignItems:'center', justifyContent:'flex-end', paddingRight:'10px' }}>
                {period === '00-11' ? 'AM' : 'PM'}
              </div>
              {hours.map(hour => (
                <div key={`${period}-${hour}`} style={{ flex:1, padding:'0 2px' }}>
                  <div style={{ display:'flex', flexDirection:'column', gap:'4px' }}>
                    {weekDates.map(date => {
                      const dateKey = format(date, 'yyyy-MM-dd');
                      const hourValue = period === '00-11' ? hour : hour + 12;
                      const hourKey = `${dateKey}-${hourValue}`;
                      const value = data[hourKey] || 0;
                      return (
                        <HeatmapSquare
                          key={`${dateKey}-${hourValue}`}
                          value={value}
                          maxValue={maxValue}
                          tooltipLabel={`${format(date, 'EEE, MMM d')} • ${String(hourValue).padStart(2,'0')}:00`}
                          onClick={() => onDataPointClick?.({ date, hour: hourValue, value })}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Month View ───────────────────────────────────────────────────────────────

const MonthView = ({ data, maxValue, currentMonth, setCurrentMonth, onDataPointClick }) => {
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });
  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const startOffset = (getDay(monthStart) + 6) % 7;

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'24px', padding:'0 10px' }}>
        <NavBtn onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}>←</NavBtn>
        <h2 style={{ margin:0, fontSize:'20px', fontWeight:'600', color:'#fff', letterSpacing:'1px' }}>
          {format(currentMonth, 'MMMM yyyy')}
        </h2>
        <NavBtn onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}>→</NavBtn>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:'6px', marginBottom:'12px', padding:'0 4px' }}>
        {dayNames.map(day => (
          <div key={day} style={{ textAlign:'center', fontSize:'12px', fontWeight:'600', color:'#aaa', padding:'6px', textTransform:'uppercase' }}>{day}</div>
        ))}
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:'6px', padding:'0 4px' }}>
        {Array.from({ length: startOffset }).map((_, i) => <div key={`empty-${i}`} style={{ paddingBottom:'100%' }} />)}
        {daysInMonth.map(date => {
          const dateKey = format(date, 'yyyy-MM-dd');
          const value = data[dateKey] || 0;
          return (
            <HeatmapSquare
              key={dateKey}
              value={value}
              maxValue={maxValue}
              tooltipLabel={format(date, 'EEEE, MMMM d, yyyy')}
              onClick={() => onDataPointClick?.({ date, value })}
            />
          );
        })}
      </div>
    </div>
  );
};

// ─── Yearly Overview ──────────────────────────────────────────────────────────

const YearlyOverview = ({ data, maxValue, valueFormatter, onDataPointClick }) => {
  const [yearOffset, setYearOffset] = useState(0);
  const currentYear = new Date().getFullYear() + yearOffset;
  const months = Array.from({ length: 12 }, (_, i) => new Date(currentYear, i, 1));

  return (
    <div>
      <style>{`
        .yearly-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 24px;
          width: 100%;
          box-sizing: border-box;
        }
        @media (max-width: 700px) {
          .yearly-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
          }
        }
        @media (max-width: 440px) {
          .yearly-grid {
            grid-template-columns: 1fr;
            gap: 10px;
          }
        }
      `}</style>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'32px', padding:'0 10px' }}>
        <NavBtn onClick={() => setYearOffset(y => y - 1)}>←</NavBtn>
        <div style={{ textAlign:'center' }}>
          <div style={{
            fontSize:'48px', fontWeight:'800', letterSpacing:'-2px', lineHeight:1,
            background:'linear-gradient(135deg, #fff 40%, #aa00ff)',
            WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent',
          }}>{currentYear}</div>
        </div>
        <NavBtn onClick={() => setYearOffset(y => y + 1)}>→</NavBtn>
      </div>
      <div className="yearly-grid">
        {months.map(month => {
          const monthStart = startOfMonth(month);
          const monthEnd = endOfMonth(month);
          const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });
          const startOffset = (getDay(monthStart) + 6) % 7;
          const monthTotal = daysInMonth.reduce((sum, date) => sum + (data[format(date, 'yyyy-MM-dd')] || 0), 0);
          return (
            <div
              key={format(month, 'yyyy-MM')}
              style={{
                background:'rgba(10,10,10,0.7)', borderRadius:'16px', padding:'16px',
                border:'1px solid rgba(255,255,255,0.1)', transition:'all 0.2s ease',
              }}
            >
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:'16px', paddingBottom:'8px', borderBottom:'1px solid rgba(170,0,255,0.3)' }}>
                <h3 style={{ margin:0, fontSize:'16px', fontWeight:'600', color:'#fff' }}>{format(month, 'MMMM')}</h3>
                <span style={{ fontSize:'11px', color:'#888' }}>{valueFormatter(monthTotal)}</span>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:'4px', marginBottom:'8px' }}>
                {['M','T','W','T','F','S','S'].map((day, i) => (
                  <div key={i} style={{ textAlign:'center', fontSize:'9px', fontWeight:'500', color:'#666' }}>{day}</div>
                ))}
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 1fr)', gap:'4px' }}>
                {Array.from({ length: startOffset }).map((_, i) => <div key={`empty-${i}`} style={{ paddingBottom:'100%' }} />)}
                {daysInMonth.map(date => {
                  const dateKey = format(date, 'yyyy-MM-dd');
                  const value = data[dateKey] || 0;
                  return (
                    <HeatmapSquare
                      key={dateKey}
                      value={value}
                      maxValue={maxValue}
                      tooltipLabel={format(date, 'MMM d, yyyy')}
                      onClick={() => onDataPointClick?.({ date, value })}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── View Toggle ──────────────────────────────────────────────────────────────

const VIEW_OPTIONS = [
  { value: 'weekly', label: 'Hourly / Week' },
  { value: 'month',  label: 'Daily / Month' },
  { value: 'yearly', label: 'Daily / Year'  },
];

const ViewToggle = ({ autoView, activeView, onChange }) => (
  <>
    <style>{`
      .hm-vt-wrap {
        display: flex;
        gap: 4px;
        background: rgba(255,255,255,0.04);
        padding: 4px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
        flex-wrap: wrap;
      }
      .hm-vt-btn {
        flex: 1 1 auto;
        padding: 6px 14px;
        border-radius: 9px;
        border: none;
        cursor: pointer;
        font-size: 12px;
        transition: all 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        white-space: nowrap;
      }
      @media (max-width: 480px) {
        .hm-vt-wrap {
          flex-direction: column;
          width: 100%;
        }
        .hm-vt-btn {
          width: 100%;
          flex: unset;
        }
      }
    `}</style>
    <div className="hm-vt-wrap">
      {VIEW_OPTIONS.map(opt => {
        const isActive = activeView === opt.value;
        const isAuto   = autoView === opt.value;
        return (
          <button
            key={opt.value}
            className="hm-vt-btn"
            onClick={() => onChange(opt.value)}
            style={{
              fontWeight: isActive ? '600' : '400',
              color: isActive ? '#fff' : '#888',
              background: isActive ? 'linear-gradient(135deg, #7700cc, #aa00ff)' : 'transparent',
              boxShadow: isActive ? '0 2px 8px rgba(170,0,255,0.35)' : 'none',
            }}
            onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = '#ccc'; }}
            onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = '#888'; }}
          >
            {opt.label}
            {isAuto && (
              <span style={{
                fontSize: '9px',
                background: isActive ? 'rgba(255,255,255,0.25)' : 'rgba(170,0,255,0.2)',
                color: isActive ? '#fff' : '#aa00ff',
                borderRadius: '4px',
                padding: '1px 4px',
                letterSpacing: '0.3px',
                fontWeight: '600',
              }}>AUTO</span>
            )}
          </button>
        );
      })}
    </div>
  </>
);

// ─── Main Heatmap Component ───────────────────────────────────────────────────

const ActivityHeatmap = ({
  data = {},
  view: autoView = 'weekly',
  activeView,
  onViewChange,
  valueFormatter = v => v.toLocaleString(),
  onDataPointClick,
  title = 'Activity Heatmap',
  subtitle,
}) => {
  const [currentMonth, setCurrentMonth] = useState(new Date());

  const [internalView, setInternalView] = useState(autoView);
  const isControlled = activeView !== undefined && onViewChange !== undefined;
  const currentView  = isControlled ? activeView : internalView;

  const handleViewChange = (v) => {
    if (isControlled) onViewChange(v);
    else setInternalView(v);
  };

  const prevAutoRef = useRef(autoView);
  useEffect(() => {
    if (!isControlled && prevAutoRef.current !== autoView) {
      prevAutoRef.current = autoView;
      setInternalView(autoView);
    }
  }, [autoView, isControlled]);

  const maxValue = useMemo(() => {
    const values = Object.values(data);
    return values.length ? Math.max(...values) : 0;
  }, [data]);

  const renderView = () => {
    switch (currentView) {
      case 'weekly':
        return <WeeklyHourlyView data={data} maxValue={maxValue} valueFormatter={valueFormatter} onDataPointClick={onDataPointClick} />;
      case 'month':
        return <MonthView data={data} maxValue={maxValue} currentMonth={currentMonth} setCurrentMonth={setCurrentMonth} valueFormatter={valueFormatter} onDataPointClick={onDataPointClick} />;
      case 'yearly':
        return <YearlyOverview data={data} maxValue={maxValue} valueFormatter={valueFormatter} onDataPointClick={onDataPointClick} />;
      default:
        return null;
    }
  };

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%)',
      borderRadius: '24px',
      padding: '24px',
      color: 'white',
      width: '100%',
      boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
      border: '1px solid rgba(255,255,255,0.05)',
      boxSizing: 'border-box',
    }}>
      <div style={{ marginBottom: '20px' }}>
        {/* Row 1: title + legend */}
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:'12px', marginBottom:'14px' }}>
          <div>
            <h2 style={{ margin:0, fontSize:'20px', fontWeight:'600', color:'#fff', letterSpacing:'0.5px' }}>{title}</h2>
            {subtitle && <div style={{ fontSize:'12px', color:'#888', marginTop:'4px' }}>{subtitle}</div>}
          </div>
          <div style={{ display:'flex', gap:'8px', alignItems:'center', background:'rgba(255,255,255,0.05)', padding:'8px 14px', borderRadius:'30px', border:'1px solid rgba(255,255,255,0.1)' }}>
            <span style={{ fontSize:'11px', color:'#aaa' }}>Low</span>
            {[0.12, 0.25, 0.45, 0.65, 0.85, 1].map((opacity, i) => (
              <div key={i} style={{ width:'18px', height:'18px', backgroundColor:'#aa00ff', opacity, borderRadius:'4px', border:'1px solid rgba(255,255,255,0.15)' }} />
            ))}
            <span style={{ fontSize:'11px', color:'#aaa' }}>High</span>
          </div>
        </div>
        {/* Row 2: view toggle */}
        <div style={{ display:'flex', alignItems:'flex-start', gap:'10px', flexWrap:'wrap' }}>
          <span style={{ fontSize:'11px', color:'#555', textTransform:'uppercase', letterSpacing:'0.5px', whiteSpace:'nowrap', paddingTop:'10px' }}>View:</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <ViewToggle autoView={autoView} activeView={currentView} onChange={handleViewChange} />
          </div>
        </div>
      </div>

      {renderView()}

      <div style={{ marginTop:'20px', paddingTop:'16px', borderTop:'1px solid rgba(255,255,255,0.05)', fontSize:'11px', color:'#555', textAlign:'center' }}>
        Each square represents activity intensity · Darker = More activity
      </div>
    </div>
  );
};

export default ActivityHeatmap;
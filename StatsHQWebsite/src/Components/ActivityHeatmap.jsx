import React, { useMemo, useState, useCallback } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, 
         getDay, addMonths, subMonths, isSameMonth, isSameDay,
         startOfWeek, endOfWeek, eachWeekOfInterval, getWeek,
         getYear, getMonth, getHours, getDate, getDayOfYear } from 'date-fns';

// Utility function to calculate opacity based on data intensity
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

// Heatmap Square Component
const HeatmapSquare = ({ value, label, tooltipContent, maxValue, onClick }) => {
  const [isHovered, setIsHovered] = useState(false);
  const opacity = getIntensityOpacity(value, maxValue);
  
  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        paddingBottom: '100%',
        cursor: 'pointer',
        transition: 'all 0.2s ease'
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: '#aa00ff',
          opacity: opacity,
          borderRadius: '6px',
          transition: 'all 0.2s ease',
          transform: isHovered ? 'scale(1.05)' : 'scale(1)',
          boxShadow: isHovered ? '0 0 15px rgba(170, 0, 255, 0.5)' : 'none',
          border: isHovered ? '1px solid rgba(170, 0, 255, 0.5)' : '1px solid rgba(255,255,255,0.1)'
        }}
      />
      
      {/* Tooltip */}
      {isHovered && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginBottom: '8px',
            backgroundColor: '#1a1a1a',
            padding: '6px 12px',
            borderRadius: '8px',
            border: `1px solid rgba(170, 0, 255, 0.3)`,
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
            color: '#fff',
            fontSize: '11px',
            whiteSpace: 'nowrap',
            zIndex: 100,
            pointerEvents: 'none'
          }}
        >
          <div style={{ fontWeight: 'bold', color: '#aa00ff' }}>{tooltipContent.label}</div>
          <div style={{ fontSize: '10px', color: '#ccc' }}>Value: {value.toLocaleString()}</div>
        </div>
      )}
    </div>
  );
};

// Weekly Hourly View Component
const WeeklyHourlyView = ({ data, maxValue, valueFormatter, onDataPointClick }) => {
  const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const hours = Array.from({ length: 12 }, (_, i) => i);
  const periods = ['00-11', '12-23'];
  
  // Get current week's dates
  const currentDate = new Date();
  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDates = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(weekStart);
    date.setDate(weekStart.getDate() + i);
    return date;
  });

  // Helper to get hour range label
  const getHourLabel = (hour, period) => {
    const baseHour = period === '00-11' ? hour : hour + 12;
    const hourStr = baseHour.toString().padStart(2, '0');
    return `${hourStr}:00`;
  };

  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ display: 'inline-block', minWidth: '100%' }}>
        {/* Day headers */}
        <div style={{ display: 'flex', marginBottom: '12px', paddingLeft: '60px' }}>
          {weekDays.map(day => (
            <div
              key={day}
              style={{
                flex: 1,
                textAlign: 'center',
                fontSize: '12px',
                fontWeight: '600',
                color: '#aaa',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}
            >
              {day}
            </div>
          ))}
        </div>

        {/* Two rows for AM/PM */}
        {periods.map((period, periodIndex) => (
          <div key={period} style={{ display: 'flex', marginBottom: periodIndex === 0 ? '8px' : 0 }}>
            {/* Period label */}
            <div
              style={{
                width: '50px',
                fontSize: '11px',
                fontWeight: '500',
                color: '#666',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                paddingRight: '10px'
              }}
            >
              {period === '00-11' ? 'AM' : 'PM'}
            </div>

            {/* Hours grid */}
            {hours.map(hour => (
              <div key={`${period}-${hour}`} style={{ flex: 1, padding: '0 2px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {weekDates.map((date, dayIndex) => {
                    const dateKey = format(date, 'yyyy-MM-dd');
                    const hourValue = period === '00-11' ? hour : hour + 12;
                    const hourKey = `${dateKey}-${hourValue}`;
                    const value = data[hourKey] || 0;
                    
                    return (
                      <HeatmapSquare
                        key={`${dateKey}-${hourValue}`}
                        value={value}
                        maxValue={maxValue}
                        tooltipContent={{
                          label: `${format(date, 'EEE, MMM d')} • ${getHourLabel(hour, period)}`
                        }}
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
  );
};

// Month View Component
const MonthView = ({ data, maxValue, currentMonth, setCurrentMonth, valueFormatter, onDataPointClick }) => {
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });
  
  // Get day names for header
  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  
  // Calculate starting offset (Monday-based)
  const startOffset = (getDay(monthStart) + 6) % 7;
  
  const handlePrevMonth = () => setCurrentMonth(subMonths(currentMonth, 1));
  const handleNextMonth = () => setCurrentMonth(addMonths(currentMonth, 1));
  
  return (
    <div>
      {/* Month navigation */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
        padding: '0 10px'
      }}>
        <button
          onClick={handlePrevMonth}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '8px',
            padding: '8px 16px',
            color: '#fff',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            fontSize: '14px'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
          onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
        >
          ←
        </button>
        
        <h2 style={{
          margin: 0,
          fontSize: '20px',
          fontWeight: '600',
          color: '#fff',
          letterSpacing: '1px'
        }}>
          {format(currentMonth, 'MMMM yyyy')}
        </h2>
        
        <button
          onClick={handleNextMonth}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '8px',
            padding: '8px 16px',
            color: '#fff',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            fontSize: '14px'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
          onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
        >
          →
        </button>
      </div>
      
      {/* Day headers */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '6px',
        marginBottom: '12px',
        padding: '0 4px'
      }}>
        {dayNames.map(day => (
          <div
            key={day}
            style={{
              textAlign: 'center',
              fontSize: '12px',
              fontWeight: '600',
              color: '#aaa',
              padding: '6px',
              textTransform: 'uppercase'
            }}
          >
            {day}
          </div>
        ))}
      </div>
      
      {/* Days grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '6px',
        padding: '0 4px'
      }}>
        {/* Empty cells for offset */}
        {Array.from({ length: startOffset }).map((_, i) => (
          <div key={`empty-${i}`} style={{ paddingBottom: '100%' }} />
        ))}
        
        {/* Actual days */}
        {daysInMonth.map(date => {
          const dateKey = format(date, 'yyyy-MM-dd');
          const value = data[dateKey] || 0;
          
          return (
            <HeatmapSquare
              key={dateKey}
              value={value}
              maxValue={maxValue}
              tooltipContent={{
                label: format(date, 'EEEE, MMMM d, yyyy')
              }}
              onClick={() => onDataPointClick?.({ date, value })}
            />
          );
        })}
      </div>
    </div>
  );
};

// Yearly Overview Component
const YearlyOverview = ({ data, maxValue, valueFormatter, onDataPointClick }) => {
  const currentYear = new Date().getFullYear();
  const months = Array.from({ length: 12 }, (_, i) => new Date(currentYear, i, 1));
  
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
      gap: '24px'
    }}>
      {months.map(month => {
        const monthStart = startOfMonth(month);
        const monthEnd = endOfMonth(month);
        const daysInMonth = eachDayOfInterval({ start: monthStart, end: monthEnd });
        const startOffset = (getDay(monthStart) + 6) % 7;
        
        // Calculate total for month
        const monthTotal = daysInMonth.reduce((sum, date) => {
          const dateKey = format(date, 'yyyy-MM-dd');
          return sum + (data[dateKey] || 0);
        }, 0);
        
        return (
          <div
            key={format(month, 'yyyy-MM')}
            style={{
              background: 'rgba(10,10,10,0.7)',
              borderRadius: '16px',
              padding: '16px',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255,255,255,0.1)',
              transition: 'all 0.2s ease'
            }}
          >
            {/* Month header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              marginBottom: '16px',
              paddingBottom: '8px',
              borderBottom: '1px solid rgba(170,0,255,0.3)'
            }}>
              <h3 style={{
                margin: 0,
                fontSize: '16px',
                fontWeight: '600',
                color: '#fff'
              }}>
                {format(month, 'MMMM')}
              </h3>
              <span style={{
                fontSize: '11px',
                color: '#888'
              }}>
                {valueFormatter(monthTotal)}
              </span>
            </div>
            
            {/* Day headers */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, 1fr)',
              gap: '4px',
              marginBottom: '8px'
            }}>
              {['M', 'T', 'W', 'T', 'F', 'S', 'S'].map(day => (
                <div
                  key={day}
                  style={{
                    textAlign: 'center',
                    fontSize: '9px',
                    fontWeight: '500',
                    color: '#666'
                  }}
                >
                  {day}
                </div>
              ))}
            </div>
            
            {/* Days grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, 1fr)',
              gap: '4px'
            }}>
              {Array.from({ length: startOffset }).map((_, i) => (
                <div key={`empty-${i}`} style={{ paddingBottom: '100%' }} />
              ))}
              {daysInMonth.map(date => {
                const dateKey = format(date, 'yyyy-MM-dd');
                const value = data[dateKey] || 0;
                
                return (
                  <HeatmapSquare
                    key={dateKey}
                    value={value}
                    maxValue={maxValue}
                    tooltipContent={{
                      label: format(date, 'MMM d, yyyy')
                    }}
                    onClick={() => onDataPointClick?.({ date, value })}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// Main Heatmap Component
const ActivityHeatmap = ({
  data = {},
  view = 'weekly', // 'weekly', 'month', 'yearly'
  valueFormatter = (value) => value.toLocaleString(),
  onDataPointClick,
  title = 'Activity Heatmap',
  subtitle
}) => {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [hoveredSquare, setHoveredSquare] = useState(null);
  
  // Calculate max value for intensity mapping
  const maxValue = useMemo(() => {
    const values = Object.values(data);
    if (values.length === 0) return 0;
    return Math.max(...values);
  }, [data]);
  
  const renderView = () => {
    switch (view) {
      case 'weekly':
        return (
          <WeeklyHourlyView
            data={data}
            maxValue={maxValue}
            valueFormatter={valueFormatter}
            onDataPointClick={onDataPointClick}
          />
        );
      case 'month':
        return (
          <MonthView
            data={data}
            maxValue={maxValue}
            currentMonth={currentMonth}
            setCurrentMonth={setCurrentMonth}
            valueFormatter={valueFormatter}
            onDataPointClick={onDataPointClick}
          />
        );
      case 'yearly':
        return (
          <YearlyOverview
            data={data}
            maxValue={maxValue}
            valueFormatter={valueFormatter}
            onDataPointClick={onDataPointClick}
          />
        );
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
      border: '1px solid rgba(255,255,255,0.05)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <h2 style={{
            margin: 0,
            fontSize: '20px',
            fontWeight: '600',
            color: '#fff',
            letterSpacing: '0.5px'
          }}>
            {title}
          </h2>
          {subtitle && (
            <div style={{
              fontSize: '12px',
              color: '#888',
              marginTop: '4px'
            }}>
              {subtitle}
            </div>
          )}
        </div>
        
        {/* Legend */}
        <div style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          background: 'rgba(255,255,255,0.05)',
          padding: '8px 16px',
          borderRadius: '30px',
          border: '1px solid rgba(255,255,255,0.1)'
        }}>
          <span style={{ fontSize: '11px', color: '#aaa' }}>Low</span>
          {[0.12, 0.25, 0.45, 0.65, 0.85, 1].map((opacity, i) => (
            <div
              key={i}
              style={{
                width: '20px',
                height: '20px',
                backgroundColor: '#aa00ff',
                opacity: opacity,
                borderRadius: '4px',
                border: '1px solid rgba(255,255,255,0.2)'
              }}
            />
          ))}
          <span style={{ fontSize: '11px', color: '#aaa' }}>High</span>
        </div>
      </div>
      
      {/* Main content */}
      {renderView()}
      
      {/* Footer */}
      <div style={{
        marginTop: '20px',
        paddingTop: '16px',
        borderTop: '1px solid rgba(255,255,255,0.05)',
        fontSize: '11px',
        color: '#666',
        textAlign: 'center'
      }}>
        Each square represents activity intensity • Darker = More activity
      </div>
    </div>
  );
};

export default ActivityHeatmap;
import React, { useState, useMemo, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

// Predefined colors for up to 10 lines
const LINE_COLORS = [
  '#ff6b6b', // red
  '#4ecdc4', // teal
  '#ffe66d', // yellow
  '#c3447a', // pink
  '#6c5ce7', // purple
  '#00b894', // green
  '#fdcb6e', // orange
  '#e17055', // coral
  '#0984e3', // blue
  '#a29bfe'  // lavender
];

// Helper function to truncate text
const truncateText = (text, maxLength = 30) => {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
};

const MultiLineChart = ({ 
  data, 
  lines, 
  title, 
  valueFormatter = (value) => value.toLocaleString() 
}) => {
  const [hoveredLine, setHoveredLine] = useState(null);
  const [hiddenLines, setHiddenLines] = useState({});
  const [isMobile, setIsMobile] = useState(false);
  const [selectedPoints, setSelectedPoints] = useState({}); // Track selected points per line

  // Check if mobile on mount and on resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Format date based on range size
  const formatDateForRange = (date, rangeSize) => {
    if (!date) return '';
    
    if (typeof date === 'string' && date.startsWith('Day')) {
      return date;
    }
    
    try {
      const d = new Date(date);
      if (isNaN(d.getTime())) return '';
      
      if (rangeSize > 365) {
        return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      }
      if (rangeSize > 60) {
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch (e) {
      return '';
    }
  };

  // Calculate which indices to show on X-axis (responsive: 4 for mobile, 10 for desktop)
  const getVisibleTickIndices = (dataLength) => {
    const maxTicks = isMobile ? 4 : 10;
    
    if (dataLength <= maxTicks) {
      return Array.from({ length: dataLength }, (_, i) => i);
    }
    
    // Show exactly maxTicks evenly spaced indices
    const step = (dataLength - 1) / (maxTicks - 1);
    const indices = [];
    for (let i = 0; i < maxTicks; i++) {
      indices.push(Math.round(i * step));
    }
    return indices;
  };

  // Custom tick renderer for X-axis
  const renderCustomTick = (props) => {
    const { x, y, payload, index, visibleIndices } = props;
    
    if (!visibleIndices.includes(index)) {
      return null;
    }
    
    const value = payload.value;
    
    let rangeSize = 0;
    if (data && data.length > 1) {
      const firstDate = new Date(data[0]?.date);
      const lastDate = new Date(data[data.length - 1]?.date);
      if (!isNaN(firstDate.getTime()) && !isNaN(lastDate.getTime())) {
        rangeSize = (lastDate - firstDate) / (1000 * 60 * 60 * 24);
      }
    }
    
    const formattedValue = formatDateForRange(value, rangeSize);
    
    // Adjust text position to prevent cutting off
    let textAnchor = 'middle';
    let xOffset = 0;
    
    // Adjust last tick to not get cut off
    if (index === visibleIndices[visibleIndices.length - 1]) {
      textAnchor = 'end';
      xOffset = -5;
    }
    // Adjust first tick
    if (index === visibleIndices[0]) {
      textAnchor = 'start';
      xOffset = 5;
    }
    
    return (
      <g transform={`translate(${x + xOffset},${y})`}>
        <text
          x={0}
          y={0}
          dy={16}
          textAnchor={textAnchor}
          fill="#b0b0b0"
          fontSize={isMobile ? 9 : 11}
        >
          {formattedValue}
        </text>
      </g>
    );
  };

  const getYAxisDomain = () => {
    if (!data || data.length === 0) return [0, 1000];
    
    let maxVal = 0;
    data.forEach(item => {
      Object.keys(item).forEach(key => {
        if (key !== 'date' && typeof item[key] === 'number') {
          maxVal = Math.max(maxVal, item[key]);
        }
      });
    });
    
    const padding = maxVal * 0.15;
    return [0, maxVal + padding];
  };

  const handleLineClick = (dataKey) => {
    setHiddenLines(prev => ({
      ...prev,
      [dataKey]: !prev[dataKey]
    }));
  };

  // Handle clicking on a specific point
  const handlePointClick = (dataKey, dataPoint, index) => {
    setSelectedPoints(prev => ({
      ...prev,
      [dataKey]: {
        index: index,
        date: dataPoint.date,
        value: dataPoint[dataKey]
      }
    }));
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      let formattedLabel = label;
      try {
        const date = new Date(label);
        if (!isNaN(date.getTime())) {
          formattedLabel = date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric',
            year: 'numeric'
          });
        }
      } catch (e) {}
      
      return (
        <div style={{
          backgroundColor: '#1a1a1a',
          padding: '10px 14px',
          border: '1px solid #aa00ff',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          maxWidth: '280px'
        }}>
          <p style={{ margin: '0 0 8px 0', fontWeight: 'bold', color: '#aa00ff', fontSize: '13px' }}>
            {formattedLabel}
          </p>
          {payload.map((entry, index) => (
            <div key={index} style={{ margin: '4px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{
                width: '10px',
                height: '10px',
                backgroundColor: entry.color,
                borderRadius: '2px'
              }} />
              <span style={{ color: '#e0e0e0', fontSize: '12px', flex: 1 }}>{entry.name}:</span>
              <span style={{ color: '#ffffff', fontWeight: 'bold', fontSize: '12px' }}>
                {valueFormatter(entry.value)}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  const yDomain = getYAxisDomain();
  const dataLength = data?.length || 0;
  const visibleIndices = getVisibleTickIndices(dataLength);

  // Custom dot component that's clickable
  const CustomDot = (props) => {
    const { cx, cy, payload, dataKey, index } = props;
    
    if (!cx || !cy) return null;
    
    const isSelected = selectedPoints[dataKey]?.index === index;
    
    return (
      <circle
        cx={cx}
        cy={cy}
        r={isSelected ? 6 : 0}
        fill="#aa00ff"
        stroke="#ffffff"
        strokeWidth={2}
        style={{ 
          cursor: 'pointer',
          filter: isSelected ? 'drop-shadow(0 0 8px rgba(170, 0, 255, 0.6))' : 'none',
          transition: 'all 0.2s ease',
          outline: 'none'
        }}
        onClick={(e) => {
          e.stopPropagation();
          handlePointClick(dataKey, payload, index);
        }}
      />
    );
  };

  return (
    <div 
      className="multi-line-chart-container"
      style={{ 
        width: '100%', 
        height: '450px', 
        padding: '16px', 
        backgroundColor: '#0a0a0a' 
      }}
    >
      {title && (
        <h3 style={{ 
          marginBottom: '16px', 
          color: '#ffffff', 
          fontSize: '1rem',
          fontWeight: '500'
        }}>
          {title}
        </h3>
      )}
      
      {/* Line selector boxes */}
      <div style={{ 
        display: 'flex', 
        flexWrap: 'wrap', 
        gap: '8px', 
        marginBottom: '16px',
        padding: '10px',
        backgroundColor: '#1a1a1a',
        borderRadius: '8px',
        border: '1px solid #333333'
      }}>
        {lines.slice(0, 10).map((line, index) => {
          const isHovered = hoveredLine === line.dataKey;
          const isHidden = hiddenLines[line.dataKey];
          const selectedPoint = selectedPoints[line.dataKey];
          
          // Apply character limit based on device
          const maxNameLength = isMobile ? 20 : 30;
          const displayName = truncateText(line.name, maxNameLength);
          
          return (
            <div key={line.dataKey} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div
                onClick={() => handleLineClick(line.dataKey)}
                onMouseEnter={() => setHoveredLine(line.dataKey)}
                onMouseLeave={() => setHoveredLine(null)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  backgroundColor: isHovered ? '#2a2a2a' : '#222222',
                  border: `1.5px solid ${isHidden ? '#444444' : LINE_COLORS[index % LINE_COLORS.length]}`,
                  borderRadius: '6px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  opacity: isHidden ? 0.6 : 1,
                  outline: 'none'
                }}
              >
                <div style={{
                  width: '10px',
                  height: '10px',
                  backgroundColor: LINE_COLORS[index % LINE_COLORS.length],
                  borderRadius: '2px',
                }} />
                <span style={{ color: isHidden ? '#888888' : '#ffffff', fontSize: isMobile ? '10px' : '11px' }}>
                  {displayName}
                </span>
              </div>
              {selectedPoint && (
                <div style={{
                  fontSize: '10px',
                  color: '#aa00ff',
                  paddingLeft: '4px'
                }}>
                  {valueFormatter(selectedPoint.value)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Chart container */}
      <div style={{ width: '100%', height: '360px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart 
            data={data} 
            margin={{ top: 5, right: isMobile ? 10 : 15, left: isMobile ? 0 : 5, bottom: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
            
            <XAxis 
              dataKey="date" 
              tick={(props) => renderCustomTick({ ...props, visibleIndices })}
              stroke="#444444"
              tickLine={false}
              axisLine={{ stroke: '#444444' }}
              height={40}
              interval={0}
            />
            
            <YAxis 
              domain={yDomain}
              tick={{ fill: '#b0b0b0', fontSize: isMobile ? 9 : 10 }}
              tickFormatter={valueFormatter}
              stroke="#444444"
              tickLine={false}
              axisLine={{ stroke: '#444444' }}
              width={isMobile ? 40 : 50}
            />
            
            <Tooltip content={<CustomTooltip />} cursor={false} />
            
            {lines.slice(0, 10).map((line, index) => (
              <Line
                key={line.dataKey}
                type="monotone"
                dataKey={line.dataKey}
                name={line.name}
                stroke={LINE_COLORS[index % LINE_COLORS.length]}
                strokeWidth={2}
                dot={<CustomDot />}
                activeDot={{ r: 4, fill: LINE_COLORS[index % LINE_COLORS.length] }}
                hide={hiddenLines[line.dataKey]}
                isAnimationActive={true}
                legendType="none"
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* CSS to kill both tap highlight AND focus outline on Android */}
      <style>{`
        .multi-line-chart-container,
        .multi-line-chart-container *,
        .recharts-wrapper,
        .recharts-surface,
        .recharts-layer,
        .recharts-cartesian-axis,
        .recharts-cartesian-axis-tick,
        .recharts-brush,
        .recharts-brush-slide,
        .recharts-legend-wrapper,
        .recharts-legend-item,
        .recharts-tooltip-wrapper,
        svg,
        svg *,
        g,
        text,
        line,
        path,
        rect,
        circle {
          -webkit-tap-highlight-color: transparent !important;
          outline: none !important;
          outline-color: transparent !important;
          outline-style: none !important;
          outline-width: 0 !important;
          -webkit-focus-ring-color: transparent !important;
        }
        
        /* Specifically target Android Chrome's focus ring */
        *:focus,
        *:active,
        *:focus-visible {
          outline: none !important;
          -webkit-tap-highlight-color: transparent !important;
        }
        
        /* Disable focus ring on SVG elements */
        svg:focus,
        svg *:focus,
        g:focus,
        text:focus,
        circle:focus {
          outline: none !important;
        }
        
        /* Remove focus outline from clickable line selector boxes */
        .multi-line-chart-container div[role="button"],
        .multi-line-chart-container div[style*="cursor: pointer"] {
          outline: none !important;
          -webkit-tap-highlight-color: transparent !important;
        }
      `}</style>
    </div>
  );
};

export default MultiLineChart;
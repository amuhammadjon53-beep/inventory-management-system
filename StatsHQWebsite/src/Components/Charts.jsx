import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush
} from 'recharts';

const InteractiveLineChart = ({ data, lines, title, valueFormatter = (value) => value.toLocaleString() }) => {
  const [hiddenLines, setHiddenLines] = useState({});
  const [isMobile, setIsMobile] = useState(false);

  // Check if mobile on mount and on resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Format date based on time range
  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays <= 31) {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else if (diffDays <= 365) {
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } else {
      return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    }
  };

  // Calculate which indices to show on X-axis (responsive)
  const getVisibleTickIndices = (dataLength) => {
    const maxTicks = isMobile ? 4 : 8;
    
    if (dataLength <= maxTicks) {
      return Array.from({ length: dataLength }, (_, i) => i);
    }
    
    // Show evenly spaced indices, always including first and last
    const step = (dataLength - 1) / (maxTicks - 1);
    const indices = [];
    for (let i = 0; i < maxTicks; i++) {
      indices.push(Math.round(i * step));
    }
    return indices;
  };

  // Custom tick renderer for X-axis to prevent cutoff
  const renderCustomTick = (props) => {
    const { x, y, payload, index, visibleTicks } = props;
    
    if (!visibleTicks.includes(index)) {
      return null;
    }
    
    const value = payload.value;
    const formattedValue = formatDate(value);
    
    // Adjust text position to prevent cutting off
    let textAnchor = 'middle';
    let xOffset = 0;
    
    // Adjust last tick to not get cut off
    if (index === visibleTicks[visibleTicks.length - 1]) {
      textAnchor = 'end';
      xOffset = -10;
    }
    // Adjust first tick
    if (index === visibleTicks[0]) {
      textAnchor = 'start';
      xOffset = 10;
    }
    
    return (
      <g transform={`translate(${x + xOffset},${y})`}>
        <text
          x={0}
          y={0}
          dy={16}
          textAnchor={textAnchor}
          fill="#b0b0b0"
          fontSize={isMobile ? 9 : 10}
        >
          {formattedValue}
        </text>
      </g>
    );
  };

  // Calculate Y-axis domain
  const getYAxisDomain = () => {
    if (!data || data.length === 0 || !lines || lines.length === 0) {
      return [0, 100];
    }

    let minValue = Infinity;
    let maxValue = -Infinity;

    data.forEach(item => {
      lines.forEach(line => {
        const value = item[line.dataKey];
        if (typeof value === 'number' && !isNaN(value)) {
          minValue = Math.min(minValue, value);
          maxValue = Math.max(maxValue, value);
        }
      });
    });

    const padding = (maxValue - minValue) * 0.1;
    return [
      Math.max(0, Math.floor(minValue - padding)),
      Math.ceil(maxValue + padding)
    ];
  };

  const handleLegendClick = (dataKey) => {
    setHiddenLines(prev => ({
      ...prev,
      [dataKey]: !prev[dataKey]
    }));
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          backgroundColor: '#1a1a1a',
          padding: '10px',
          border: '1px solid #aa00ff',
          borderRadius: '8px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          color: '#ffffff'
        }}>
          <p style={{ margin: '0 0 5px 0', fontWeight: 'bold', color: '#ffffff' }}>
            {formatDate(label)}
          </p>
          {payload.map((entry, index) => (
            <p key={index} style={{ margin: '2px 0', color: '#ffffff' }}>
              <span style={{ color: entry.color }}>●</span> {entry.name}: {valueFormatter(entry.value)}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const yDomain = getYAxisDomain();
  const dataLength = data?.length || 0;
  const visibleTicks = getVisibleTickIndices(dataLength);

  return (
    <div 
      className="chart-container"
      style={{ 
        width: '100%', 
        height: '400px', 
        padding: '5px', 
        backgroundColor: '#0a0a0a'
      }}
    >
      {title && <h3 style={{ marginBottom: '10px', color: '#ffffff', fontSize: '14px' }}>{title}</h3>}
      
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 5, right: isMobile ? 20 : 30, left: isMobile ? 0 : -10, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" vertical={false} />
          
          <XAxis
            dataKey="date"
            tick={(props) => renderCustomTick({ ...props, visibleTicks })}
            height={50}
            interval={0}
            tickLine={false}
            axisLine={{ stroke: '#444444' }}
            stroke="#444444"
          />
          
          <YAxis
            domain={yDomain}
            tick={{ fontSize: 9, fill: '#b0b0b0' }}
            tickFormatter={valueFormatter}
            stroke="#444444"
            tickLine={false}
            axisLine={{ stroke: '#444444' }}
            width={40}
          />
          
          <Tooltip content={<CustomTooltip />} />
          
          <Legend
            onClick={(e) => handleLegendClick(e.dataKey)}
            wrapperStyle={{ cursor: 'pointer', color: '#ffffff', fontSize: '10px', paddingTop: '5px' }}
          />
          
          <Brush
            dataKey="date"
            height={20}
            stroke="#aa00ff"
            fill="#1a1a1a"
            tickFormatter={formatDate}
          />
          
          {lines.map((line, index) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              name={line.name}
              stroke={line.color || `hsl(${index * 45}, 70%, 55%)`}
              strokeWidth={hiddenLines[line.dataKey] ? 0 : 1.5}
              dot={false}
              activeDot={{ r: 4, fill: line.color || `hsl(${index * 45}, 70%, 55%)` }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      
      {/* CSS to kill both tap highlight AND focus outline on Android */}
      <style>{`
        .chart-container,
        .chart-container *,
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
        rect {
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
        text:focus {
          outline: none !important;
        }
      `}</style>
    </div>
  );
};

export default InteractiveLineChart;
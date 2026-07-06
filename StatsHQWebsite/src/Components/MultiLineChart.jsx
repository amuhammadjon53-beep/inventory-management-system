import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

// Predefined colors for up to 10 lines (used ONLY as a fallback when a line
// doesn't specify its own `color`)
const LINE_COLORS = [
  '#ff6b6b', // red
  '#00b894', // green (was teal '#4ecdc4')
  '#ffe66d', // yellow
  '#c3447a', // pink
  '#6c5ce7', // purple
  '#00b894', // green
  '#fdcb6e', // orange
  '#e17055', // coral
  '#0984e3', // blue
  '#a29bfe'  // lavender
];

// Resolve the color for a given line: prefer the explicit color passed in
// via the `lines` prop, fall back to the palette by index.
const getLineColor = (line, index) => line.color || LINE_COLORS[index % LINE_COLORS.length];

// IMPORTANT: this must live OUTSIDE the MultiLineChart function body.
// If it's declared inside the component, React gets a brand-new component
// reference on every render, which makes Recharts tear down and remount
// every single dot SVG node on every re-render (e.g. every time you hover
// a legend chip). With multiple charts on screen and up to 90 days of data
// per line, that remount churn is what eventually pins the CPU and gets
// you the "this page is slowing down Firefox" warning.
const CustomDot = (props) => {
  const { cx, cy, dataKey, index, onDotClick, selectedIndex } = props;

  if (!cx || !cy) return null;

  const isSelected = selectedIndex === index;

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
        onDotClick?.(dataKey, props.payload, index);
      }}
    />
  );
};

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
  const [exportingCSV, setExportingCSV] = useState(false);
  const [exportingPDF, setExportingPDF] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const chartRef = useRef(null);
  const exportButtonRef = useRef(null);
  const hasAnimatedRef = useRef({});
  // These refs let the memoized dot renderer below read "live" state at
  // click/render time without needing selectedPoints (or the click handler)
  // in its dependency array — keeping its identity 100% stable across
  // re-renders, which is what stops Recharts from remounting every dot.
  const selectedPointsRef = useRef(selectedPoints);
  selectedPointsRef.current = selectedPoints;
  const hiddenLinesRef = useRef({});

  // Check if mobile on mount and on resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Handle outside click to close menu
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (exportButtonRef.current && !exportButtonRef.current.contains(event.target)) {
        setShowExportMenu(false);
      }
    };

    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [showExportMenu]);

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
  const handlePointClickRef = useRef(handlePointClick);
  handlePointClickRef.current = handlePointClick;

  // A single stable dot-renderer shared across every <Line>. Empty deps
  // means this function's identity never changes across re-renders, so
  // Recharts reconciles existing dot nodes instead of tearing them all
  // down and remounting them on every hover/click/state change.
  const renderDot = useCallback((dotProps) => (
    <CustomDot
      {...dotProps}
      selectedIndex={selectedPointsRef.current[dotProps.dataKey]?.index}
      onDotClick={(dataKey, payload, index) => handlePointClickRef.current(dataKey, payload, index)}
    />
  ), []);

  // Export functions
  const exportToCSV = async () => {
    setExportingCSV(true);
    try {
      if (!data || data.length === 0) {
        console.error('No data to export');
        return;
      }

      // Get visible lines (not hidden)
      const visibleLines = lines.slice(0, 10).filter(line => !hiddenLines[line.dataKey]);
      
      if (visibleLines.length === 0) {
        console.error('No visible lines to export');
        return;
      }

      // Prepare CSV headers
      const headers = ['Date', ...visibleLines.map(line => line.name)];
      
      // Create CSV rows
      const csvRows = [headers];
      
      for (const item of data) {
        // Format date
        let formattedDate = item.date;
        try {
          const date = new Date(item.date);
          if (!isNaN(date.getTime())) {
            formattedDate = date.toLocaleDateString('en-US', { 
              month: 'short', 
              day: 'numeric',
              year: 'numeric'
            });
          }
        } catch (e) {}
        
        const row = [
          `"${String(formattedDate).replace(/"/g, '""')}"`,
          ...visibleLines.map(line => {
            const value = item[line.dataKey];
            return value !== undefined && value !== null ? value : '';
          })
        ];
        csvRows.push(row.join(','));
      }
      
      const csvContent = csvRows.join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      const filename = `${(title || 'multiline_chart').toLowerCase().replace(/\s+/g, '_')}_export.csv`;
      
      link.setAttribute('href', url);
      link.setAttribute('download', filename);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error exporting CSV:', error);
    } finally {
      setExportingCSV(false);
    }
  };

  const exportToPDF = async () => {
    setExportingPDF(true);
    const buttons = chartRef.current?.querySelector('.export-buttons-container');
    try {
      if (!chartRef.current) {
        console.error('Chart ref not available');
        return;
      }

      // Hide buttons temporarily
      if (buttons) buttons.style.visibility = 'hidden';

      // Capture with higher scale for retina quality
      const canvas = await html2canvas(chartRef.current, {
        scale: 2,
        backgroundColor: '#0a0a0a',
        logging: false,
        useCORS: true
      });

      // Restore buttons
      if (buttons) buttons.style.visibility = 'visible';
      
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF({
        unit: 'px',
        format: [canvas.width, canvas.height],
        orientation: canvas.width > canvas.height ? 'landscape' : 'portrait'
      });
      
      pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
      
      const filename = `${(title || 'multiline_chart').toLowerCase().replace(/\s+/g, '_')}_export.pdf`;
      pdf.save(filename);
    } catch (error) {
      // Restore buttons on error
      if (buttons) buttons.style.visibility = 'visible';
      console.error('Error exporting PDF:', error);
    } finally {
      setExportingPDF(false);
    }
  };

  const handleExportOption = async (exportFn) => {
    setShowExportMenu(false);
    await exportFn();
  };

  // Export options array for easy extensibility
  const EXPORT_OPTIONS = [
    {
      label: 'CSV',
      icon: '↓',
      onClick: exportToCSV,
      exporting: exportingCSV
    },
    {
      label: 'PDF',
      icon: '⎙',
      onClick: exportToPDF,
      exporting: exportingPDF
    }
  ];

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

  return (
    <div 
      ref={chartRef}
      className="multi-line-chart-container"
      style={{ 
        width: '100%', 
        height: '450px', 
        padding: '16px', 
        backgroundColor: '#0a0a0a' 
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        {title && (
          <h3 style={{ 
            margin: 0, 
            color: '#ffffff', 
            fontSize: '1rem',
            fontWeight: '500'
          }}>
            {title}
          </h3>
        )}
        
        {/* Export Button with Dropdown Menu */}
        <div className="export-buttons-container" style={{
          position: 'relative',
          display: 'inline-block'
        }} ref={exportButtonRef}>
          <button
            onClick={() => setShowExportMenu(!showExportMenu)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              fontSize: '12px',
              fontWeight: '500',
              background: 'transparent',
              color: '#ffffff',
              border: '1px solid #333333',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              fontFamily: 'inherit'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#aa00ff';
              e.currentTarget.style.color = '#aa00ff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#333333';
              e.currentTarget.style.color = '#ffffff';
            }}
          >
            
            <span className="export-label">Export</span>
            <span>▾</span>
          </button>

          {/* Dropdown Menu */}
          {showExportMenu && (
            <div style={{
              position: 'absolute',
              bottom: '100%',
              right: 0,
              marginBottom: '4px',
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              borderRadius: '8px',
              boxShadow: '0 -4px 16px rgba(0,0,0,0.4)',
              padding: '4px',
              minWidth: '120px',
              animation: 'fadeIn 0.15s ease-out',
              zIndex: 1000
            }}>
              {EXPORT_OPTIONS.map((option) => (
                <button
                  key={option.label}
                  onClick={() => handleExportOption(option.onClick)}
                  disabled={option.exporting}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    width: '100%',
                    padding: '8px 12px',
                    backgroundColor: 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#ffffff',
                    fontSize: '12px',
                    cursor: option.exporting ? 'wait' : 'pointer',
                    transition: 'all 0.15s ease',
                    fontFamily: 'inherit',
                    textAlign: 'left'
                  }}
                  onMouseEnter={(e) => {
                    if (!option.exporting) {
                      e.currentTarget.style.backgroundColor = 'rgba(170, 0, 255, 0.12)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <span style={{ fontSize: '13px' }}>{option.icon}</span>
                  <span style={{ flex: 1 }}>{option.label}</span>
                  {option.exporting && (
                    <span className="export-spinner" style={{
                      display: 'inline-block',
                      width: '10px',
                      height: '10px',
                      border: `2px solid #aa00ff`,
                      borderTopColor: 'transparent',
                      borderRadius: '50%',
                      animation: 'spin 0.6s linear infinite'
                    }} />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      
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
          const color = getLineColor(line, index);
          
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
                  border: `1.5px solid ${isHidden ? '#444444' : color}`,
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
                  backgroundColor: color,
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
            
            {lines.slice(0, 10).map((line, index) => {
              const color = getLineColor(line, index);
              return (
                <Line
                  key={line.dataKey}
                  type="monotone"
                  dataKey={line.dataKey}
                  name={line.name}
                  stroke={color}
                  strokeWidth={2}
                  dot={renderDot}
                  activeDot={{ r: 4, fill: color }}
                  hide={hiddenLines[line.dataKey]}
                  // Only animate the initial draw-in, not every re-render
                  // caused by legend hover, tooltip state, etc. Replaying
                  // the full entrance animation on every re-render is what
                  // compounds into the runaway CPU usage over time.
                  isAnimationActive={hasAnimatedRef.current[line.dataKey] ? false : true}
                  onAnimationEnd={() => { hasAnimatedRef.current[line.dataKey] = true; }}
                  legendType="none"
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* CSS to kill both tap highlight AND focus outline on Android */}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(5px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
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
        
        /* Mobile responsive: hide button labels on small screens */
        @media (max-width: 768px) {
          .export-label {
            display: none;
          }
          .export-buttons-container button {
            padding: 4px 8px;
          }
        }
      `}</style>
    </div>
  );
};

export default MultiLineChart;
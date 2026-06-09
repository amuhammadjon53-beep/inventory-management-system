import React, { useState, useEffect, useRef } from 'react';
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

const EnhancedMultiLineChart = ({ 
  data, 
  availableLines, // All possible lines that can be added
  title, 
  valueFormatter = (value) => value.toLocaleString() 
}) => {
  const [hoveredLine, setHoveredLine] = useState(null);
  const [hiddenLines, setHiddenLines] = useState({});
  const [isMobile, setIsMobile] = useState(false);
  const [selectedPoints, setSelectedPoints] = useState({});
  const [activeLines, setActiveLines] = useState([]); // Currently shown lines (max 5)
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [fadeError, setFadeError] = useState(false);
  const [exportingCSV, setExportingCSV] = useState(false);
  const [exportingPDF, setExportingPDF] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const chartRef = useRef(null);
  const exportButtonRef = useRef(null);

  // Check if mobile on mount and on resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Handle outside click to close export menu
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

  // Initialize with first 5 available lines or fewer
  useEffect(() => {
    if (availableLines && availableLines.length > 0 && activeLines.length === 0) {
      const initialLines = availableLines.slice(0, 5);
      setActiveLines(initialLines);
    }
  }, [availableLines]);

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
      activeLines.forEach(line => {
        const value = item[line.dataKey];
        if (typeof value === 'number' && !hiddenLines[line.dataKey]) {
          maxVal = Math.max(maxVal, value);
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

  // Remove a line from active lines
  const handleRemoveLine = (dataKey) => {
    setActiveLines(prev => prev.filter(line => line.dataKey !== dataKey));
    // Clean up hidden state for removed line
    setHiddenLines(prev => {
      const newState = { ...prev };
      delete newState[dataKey];
      return newState;
    });
    // Clean up selected point for removed line
    setSelectedPoints(prev => {
      const newState = { ...prev };
      delete newState[dataKey];
      return newState;
    });
  };

  // Add a new line
  const handleAddLine = (lineToAdd) => {
    if (activeLines.length >= 5) {
      setErrorMessage('Maximum of 5 lines reached. Remove a line first to add another.');
      setFadeError(true);
      setTimeout(() => {
        setFadeError(false);
        setTimeout(() => setErrorMessage(''), 300);
      }, 2000);
      return;
    }
    
    if (!activeLines.find(line => line.dataKey === lineToAdd.dataKey)) {
      setActiveLines(prev => [...prev, lineToAdd]);
      setShowAddMenu(false);
    }
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

  // Get available lines not currently active
  const getAvailableLinesToAdd = () => {
    if (!availableLines) return [];
    return availableLines.filter(
      availableLine => !activeLines.find(activeLine => activeLine.dataKey === availableLine.dataKey)
    );
  };

  // Export functions
  const exportToCSV = async () => {
    setExportingCSV(true);
    try {
      if (!data || data.length === 0) {
        console.error('No data to export');
        return;
      }

      // Get visible lines (not hidden)
      const visibleLines = activeLines.filter(line => !hiddenLines[line.dataKey]);
      
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
      const filename = `${(title || 'enhanced_chart').toLowerCase().replace(/\s+/g, '_')}_export.csv`;
      
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
      
      const filename = `${(title || 'enhanced_chart').toLowerCase().replace(/\s+/g, '_')}_export.pdf`;
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
  const availableToAdd = getAvailableLinesToAdd();

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
      ref={chartRef}
      className="enhanced-multi-line-chart-container"
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
      
      {/* Error message */}
      {errorMessage && (
        <div style={{
          marginBottom: '12px',
          padding: '8px 12px',
          backgroundColor: fadeError ? 'rgba(170, 0, 255, 0.1)' : 'rgba(170, 0, 255, 0.15)',
          borderLeft: `3px solid #aa00ff`,
          borderRadius: '4px',
          opacity: fadeError ? 0.3 : 0.6,
          transition: 'opacity 0.3s ease',
          fontSize: '12px',
          color: '#aa00ff'
        }}>
          {errorMessage}
        </div>
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
        {activeLines.map((line, index) => {
          const isHovered = hoveredLine === line.dataKey;
          const isHidden = hiddenLines[line.dataKey];
          const selectedPoint = selectedPoints[line.dataKey];
          
          // Apply character limit based on device
          const maxNameLength = isMobile ? 20 : 30;
          const displayName = truncateText(line.name, maxNameLength);
          
          return (
            <div key={line.dataKey} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <div
                  onClick={() => handleLineClick(line.dataKey)}
                  onMouseEnter={() => setHoveredLine(line.dataKey)}
                  onMouseLeave={() => setHoveredLine(null)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 8px',
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
                <button
                  onClick={() => handleRemoveLine(line.dataKey)}
                  style={{
                    backgroundColor: '#2a2a2a',
                    border: '1px solid #555555',
                    color: '#888888',
                    borderRadius: '4px',
                    width: '20px',
                    height: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    fontSize: '12px',
                    transition: 'all 0.2s ease',
                    outline: 'none'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#3a3a3a';
                    e.currentTarget.style.color = '#ff6b6b';
                    e.currentTarget.style.borderColor = '#ff6b6b';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#2a2a2a';
                    e.currentTarget.style.color = '#888888';
                    e.currentTarget.style.borderColor = '#555555';
                  }}
                >
                  ✕
                </button>
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
        
        {/* Add button */}
        {activeLines.length < 5 && availableToAdd.length > 0 && (
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowAddMenu(!showAddMenu)}
              style={{
                backgroundColor: '#2a2a2a',
                border: '1.5px dashed #666666',
                color: '#aa00ff',
                borderRadius: '6px',
                padding: '4px 12px',
                cursor: 'pointer',
                fontSize: isMobile ? '10px' : '11px',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                outline: 'none'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = '#333333';
                e.currentTarget.style.borderColor = '#aa00ff';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = '#2a2a2a';
                e.currentTarget.style.borderColor = '#666666';
              }}
            >
              + Add Line
            </button>
            
            {/* Dropdown menu for adding lines */}
            {showAddMenu && (
              <div style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                marginTop: '8px',
                backgroundColor: '#2a2a2a',
                border: '1px solid #aa00ff',
                borderRadius: '6px',
                minWidth: '180px',
                maxHeight: '200px',
                overflowY: 'auto',
                zIndex: 1000,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)'
              }}>
                {availableToAdd.map((line, idx) => (
                  <div
                    key={line.dataKey}
                    onClick={() => handleAddLine(line)}
                    style={{
                      padding: '8px 12px',
                      cursor: 'pointer',
                      fontSize: '11px',
                      color: '#e0e0e0',
                      borderBottom: idx < availableToAdd.length - 1 ? '1px solid #444444' : 'none',
                      transition: 'background 0.2s ease'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = '#aa00ff';
                      e.currentTarget.style.color = '#ffffff';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = '#2a2a2a';
                      e.currentTarget.style.color = '#e0e0e0';
                    }}
                  >
                    {truncateText(line.name, isMobile ? 25 : 35)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
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
            
            {activeLines.map((line, index) => (
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
        
        .enhanced-multi-line-chart-container,
        .enhanced-multi-line-chart-container *,
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
        .enhanced-multi-line-chart-container div[role="button"],
        .enhanced-multi-line-chart-container div[style*="cursor: pointer"] {
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

export default EnhancedMultiLineChart;
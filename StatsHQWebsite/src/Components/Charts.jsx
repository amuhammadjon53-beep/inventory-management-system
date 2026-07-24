import React, { useState, useEffect, useRef } from 'react';
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
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';

const InteractiveLineChart = ({ data, lines, title, valueFormatter = (value) => value.toLocaleString() }) => {
  const [hiddenLines, setHiddenLines] = useState({});
  const [isMobile, setIsMobile] = useState(false);
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

  // Export functions
  const exportToCSV = async () => {
    setExportingCSV(true);
    try {
      if (!data || data.length === 0) {
        console.error('No data to export');
        return;
      }

      // Get visible lines (not hidden)
      const visibleLines = lines.filter(line => !hiddenLines[line.dataKey]);
      
      if (visibleLines.length === 0) {
        console.error('No visible lines to export');
        return;
      }

      // Prepare CSV headers - include both raw date and formatted date
      const headers = ['Raw Date', 'Formatted Date', ...visibleLines.map(line => line.name)];
      
      // Create CSV rows
      const csvRows = [headers];
      
      for (const item of data) {
        const formattedDate = formatDate(item.date);
        
        const row = [
          `"${String(item.date).replace(/"/g, '""')}"`, // Raw date
          `"${String(formattedDate).replace(/"/g, '""')}"`, // Formatted date
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
      const filename = `${(title || 'chart').toLowerCase().replace(/\s+/g, '_')}_export.csv`;
      
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
      
      const filename = `${(title || 'chart').toLowerCase().replace(/\s+/g, '_')}_export.pdf`;
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

  const yDomain = getYAxisDomain();
  const dataLength = data?.length || 0;
  const visibleTicks = getVisibleTickIndices(dataLength);

  return (
    <div 
      ref={chartRef}
      className="chart-container"
      style={{ 
        width: '100%', 
        height: '400px', 
        padding: '5px', 
        backgroundColor: '#0a0a0a'
      }}
    >
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '10px'
      }}>
        {title && <h3 style={{ margin: 0, color: '#ffffff', fontSize: '14px' }}>{title}</h3>}
        
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

export default InteractiveLineChart;
/**
 * Chart utilities: safe options for empty data, Chinese font support.
 */

const CHINESE_FONT = "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif"

/**
 * Wrap ECharts option with Chinese font and empty data fallback.
 */
export function safeChartOption(option, emptyText = '暂无数据') {
  // Check if all series have no data
  const hasData = option.series?.some(s => {
    if (Array.isArray(s.data)) return s.data.length > 0
    if (s.data && typeof s.data === 'object') return Object.keys(s.data).length > 0
    return true
  })

  if (!hasData || !option.series?.length) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'center',
        style: { text: emptyText, fontSize: 14, fill: '#999', fontFamily: CHINESE_FONT }
      }
    }
  }

  // Apply Chinese font to text elements
  const result = { ...option }
  result.textStyle = { ...(result.textStyle || {}), fontFamily: CHINESE_FONT }

  // Apply to axes
  for (const axisKey of ['xAxis', 'yAxis']) {
    const axes = Array.isArray(result[axisKey]) ? result[axisKey] : [result[axisKey]]
    for (const axis of axes) {
      if (axis?.axisLabel) {
        axis.axisLabel = { ...(axis.axisLabel || {}), fontFamily: CHINESE_FONT }
      }
      if (axis?.name) {
        // axis name style
      }
    }
  }

  // Apply to legend
  if (result.legend?.textStyle) {
    result.legend.textStyle = { ...result.legend.textStyle, fontFamily: CHINESE_FONT }
  }

  // Apply to tooltip
  if (result.tooltip?.textStyle) {
    result.tooltip.textStyle = { ...result.tooltip.textStyle, fontFamily: CHINESE_FONT }
  }

  return result
}

/**
 * Initialize an ECharts instance with auto-resize.
 */
export function initChart(el, option) {
  const echarts = require('echarts')
  const chart = echarts.init(el)

  const ro = new ResizeObserver(() => chart.resize())
  ro.observe(el)

  chart.setOption(safeChartOption(option))
  return chart
}

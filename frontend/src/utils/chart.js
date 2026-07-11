/**
 * ECharts 工具：中文字体 + 自动 resize + 空数据兜底
 */
import * as echarts from 'echarts'

const CHINESE_FONT = "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif"

/**
 * 初始化 ECharts，自动应用中文字体和 resize 监听
 */
export function createChart(el, option) {
  const chart = echarts.init(el)

  // 自动 resize
  const ro = new ResizeObserver(() => chart.resize())
  ro.observe(el)

  // 注入中文字体
  const enriched = injectFont(option)
  chart.setOption(enriched)
  return chart
}

/**
 * 给 option 注入中文字体
 */
function injectFont(opt) {
  if (!opt) return opt
  const result = { ...opt }

  // 全局 textStyle
  result.textStyle = { fontFamily: CHINESE_FONT, ...(result.textStyle || {}) }

  // xAxis / yAxis
  for (const key of ['xAxis', 'yAxis']) {
    const axes = Array.isArray(result[key]) ? result[key] : (result[key] ? [result[key]] : [])
    for (const axis of axes) {
      if (axis?.axisLabel) {
        axis.axisLabel = { fontFamily: CHINESE_FONT, ...(axis.axisLabel || {}) }
      }
    }
  }

  // legend
  if (result.legend) {
    result.legend = { ...result.legend, textStyle: { fontFamily: CHINESE_FONT, ...(result.legend.textStyle || {}) } }
  }

  // tooltip
  if (result.tooltip) {
    result.tooltip = { ...result.tooltip, textStyle: { fontFamily: CHINESE_FONT, ...(result.tooltip.textStyle || {}) } }
  }

  // series labels
  if (result.series) {
    result.series = result.series.map(s => {
      if (s.label) {
        s = { ...s, label: { fontFamily: CHINESE_FONT, ...(s.label || {}) } }
      }
      return s
    })
  }

  return result
}

/**
 * 空数据兜底 option
 */
export function emptyChartOption(text = '暂无数据') {
  return {
    graphic: {
      type: 'text',
      left: 'center',
      top: 'center',
      style: { text, fontSize: 14, fill: '#999', fontFamily: CHINESE_FONT }
    }
  }
}

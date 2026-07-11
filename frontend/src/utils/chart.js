/**
 * ECharts 工具：中文字体 + 自动 resize + 空数据兜底 + 实例管理
 */
import * as echarts from 'echarts'

const CHINESE_FONT = "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif"

// 全局 chart 实例集合
const allCharts = new Set()

// 全局 window resize 监听
let windowResizeTimer = null
window.addEventListener('resize', () => {
  clearTimeout(windowResizeTimer)
  windowResizeTimer = setTimeout(() => {
    allCharts.forEach(chart => {
      if (chart && !chart.isDisposed()) {
        chart.resize()
      }
    })
  }, 200)
})

/**
 * 初始化 ECharts，自动应用中文字体和 resize 监听
 */
export function createChart(el, option) {
  if (!el) return null

  const chart = echarts.init(el)

  // 注册到全局集合（自动 resize）
  allCharts.add(chart)

  // 注入中文字体
  const enriched = injectFont(option)
  chart.setOption(enriched)
  return chart
}

/**
 * 销毁图表实例
 */
export function disposeChart(el) {
  allCharts.forEach(chart => {
    if (chart && !chart.isDisposed()) {
      const container = chart.getDom()
      if (container === el) {
        chart.dispose()
        allCharts.delete(chart)
      }
    }
  })
}

/**
 * 销毁所有图表（用于页面级清理）
 */
export function disposeAllCharts() {
  allCharts.forEach(chart => {
    if (chart && !chart.isDisposed()) {
      chart.dispose()
    }
  })
  allCharts.clear()
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

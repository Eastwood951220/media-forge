const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function formatRecurrence(scheduleType: 'daily' | 'weekly', timeOfDay: string, weekdays: number[]): string {
  if (scheduleType === 'daily') return `每天 ${timeOfDay}`
  const labels = weekdays.map((day) => WEEKDAY_LABELS[day]).filter(Boolean)
  return `${labels.join('、')} ${timeOfDay}`
}

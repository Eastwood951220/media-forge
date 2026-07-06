export const runDetailStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
  pending_crawl: { text: '待爬取', color: 'default' },
  crawled: { text: '已爬取', color: 'processing' },
  crawl_failed: { text: '爬取失败', color: 'error' },
  saved: { text: '已保存', color: 'success' },
  save_failed: { text: '保存失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

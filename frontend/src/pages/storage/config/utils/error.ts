export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export function isFormValidationError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'errorFields' in error
}

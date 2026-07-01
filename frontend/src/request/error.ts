export class BusinessError extends Error {
  code?: string | number
  data?: unknown

  constructor(message: string, code?: string | number, data?: unknown) {
    super(message)
    this.name = 'BusinessError'
    this.code = code
    this.data = data
  }
}

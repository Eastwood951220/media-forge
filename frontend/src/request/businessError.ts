import { HttpStatus } from '@/enums/RespEnum'
import errorCode from '@/request/errorCode'
import type { ApiResponse, PaginatedApiResponse } from './types'

export function getBusinessMessage(data: ApiResponse | PaginatedApiResponse): string {
  const code = data.code ?? HttpStatus.SUCCESS
  return errorCode[code as string | number] || data.msg || errorCode.default
}

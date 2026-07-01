import { message } from 'antd'
import FileSaver from 'file-saver'
import errorCode from '@/request/errorCode'
import { isCancelledError } from './cancel'
import { service } from './instance'
import type { ApiResponse, RequestConfig } from './types'
import { tansParams } from './utils'

function blobValidate(data: Blob): boolean {
  return !data.type.includes('application/json')
}

/**
 * 通用下载方法。
 *
 * 参数会按 application/x-www-form-urlencoded 编码。
 * Blob 校验失败时说明后端返回了 JSON 错误对象，此时读取文本并提示 msg。
 */
export async function download(
  url: string,
  params: Record<string, unknown> = {},
  fileName = 'download',
  config: RequestConfig = {},
): Promise<void> {
  const showError = config.showError !== false
  const closeLoading = showError
    ? message.loading('正在下载数据，请稍候', 0)
    : undefined

  try {
    const resp = await service.post<Blob, Blob>(url, params, {
      ...config,
      transformRequest: [
        (requestParams: Record<string, unknown>) => tansParams(requestParams),
      ],
      headers: {
        ...config.headers,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      responseType: 'blob',
    })

    if (blobValidate(resp)) {
      FileSaver.saveAs(new Blob([resp]), fileName)
      return
    }

    const resText = await new Blob([resp]).text()
    const response = JSON.parse(resText) as ApiResponse
    const errMsg = errorCode[response.code ?? 'default'] || response.msg || errorCode.default

    if (showError) {
      void message.error(errMsg)
    }
  } catch (error) {
    if (isCancelledError(error)) {
      return
    }

    console.error(error)
    if (showError) {
      void message.error('下载文件出现错误，请联系管理员！')
    }
    throw error
  } finally {
    closeLoading?.()
  }
}

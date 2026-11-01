import type { PageActionMessage, PageActionResponse } from './types'

type PageActionLogger = Pick<Console, 'info' | 'error'>

export async function respondToPageActionMessage(
  message: PageActionMessage,
  handle: (message: PageActionMessage) => Promise<PageActionResponse<unknown>>,
  respond: (response: PageActionResponse<unknown>) => void,
  logger: PageActionLogger = console,
): Promise<void> {
  logger.info('[Media Forge page action] received', message.type)
  try {
    const response = await handle(message)
    logger.info(
      '[Media Forge page action] responded',
      message.type,
      response.ok ? 'ok' : response.error.code,
    )
    respond(response)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(
      '[Media Forge page action] background failed',
      message.type,
      errorMessage.replace(/agt_[A-Za-z0-9_-]+/g, '[REDACTED]'),
    )
    respond({
      ok: false,
      error: {
        code: 'background_error',
        message: '扩展后台处理失败，请查看 Service Worker 控制台',
      },
    })
  }
}

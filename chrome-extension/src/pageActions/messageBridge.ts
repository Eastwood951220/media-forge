import type { PageActionMessage, PageActionResponse } from './types'

export type PageActionLogger = Pick<Console, 'info' | 'error'>

function safeErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  return message.replace(/agt_[A-Za-z0-9_-]+/g, '[REDACTED]')
}

export function logPageActionFailure(
  type: PageActionMessage['type'],
  error: unknown,
  logger: PageActionLogger = console,
): void {
  logger.error('[Media Forge page action] workflow failed', type, safeErrorMessage(error))
}

export async function sendPageActionMessage(
  message: PageActionMessage,
  send: (message: PageActionMessage) => Promise<PageActionResponse<unknown>>,
  logger: PageActionLogger = console,
): Promise<PageActionResponse<unknown>> {
  logger.info('[Media Forge page action] send', message.type)
  try {
    const response = await send(message)
    if (!response || typeof response !== 'object' || typeof response.ok !== 'boolean') {
      throw new Error('missing_page_action_response')
    }
    logger.info(
      '[Media Forge page action] response',
      message.type,
      response.ok ? 'ok' : response.error?.code ?? 'unknown_error',
    )
    return response
  } catch (error) {
    logger.error('[Media Forge page action] failed', message.type, safeErrorMessage(error))
    throw error
  }
}

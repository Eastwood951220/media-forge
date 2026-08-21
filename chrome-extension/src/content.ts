export type PageSnapshot = {
  page_kind: 'list' | 'detail'
  url: string
  source_page?: number
  fragments: Record<string, string>
}

function outer(selector: string): string {
  return document.querySelector(selector)?.outerHTML ?? ''
}

export function detectPageKind(): 'list' | 'detail' {
  return location.pathname.startsWith('/v/') ? 'detail' : 'list'
}

function sourcePage(): number {
  const value = new URL(location.href).searchParams.get('page')
  const parsed = Number(value || '1')
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

export function snapshot(): PageSnapshot {
  const pageKind = detectPageKind()
  if (pageKind === 'detail') {
    return {
      page_kind: 'detail',
      url: location.href,
      fragments: {
        detail: outer('.video-detail'),
        title: outer('.video-detail h2.title.is-4, h2.title.is-4'),
        cover: outer('.video-cover'),
        movie_panel: outer('nav.movie-panel-info, .movie-panel-info'),
        tags: outer('#tags'),
        magnets: outer('#magnets-content'),
      },
    }
  }
  return {
    page_kind: 'list',
    url: location.href,
    source_page: sourcePage(),
    fragments: {
      section_title: outer('.section-title'),
      items: Array.from(document.querySelectorAll('div.item'))
        .map((node) => node.outerHTML)
        .join('\n'),
    },
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'collect_snapshot') return false
  sendResponse({ snapshot: snapshot() })
  return true
})

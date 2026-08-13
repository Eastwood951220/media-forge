export interface ViewTransitionLike {
  ready: Promise<void>
  finished: Promise<void>
  updateCallbackDone?: Promise<void>
  skipTransition?: () => void
}

export type StartViewTransition = (
  updateCallback: () => void | Promise<void>,
) => ViewTransitionLike

export interface UseThemeViewTransitionOptions {
  duration?: number
  easing?: string
  toggleTheme: () => void
}
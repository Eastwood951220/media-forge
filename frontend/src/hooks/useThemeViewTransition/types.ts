export type ViewTransitionLike = {
  ready: Promise<void>
  finished?: Promise<void>
  skipTransition?: () => void
}

export type StartViewTransition = (callback: () => void | Promise<void>) => ViewTransitionLike

export type UseThemeViewTransitionOptions = {
  duration?: number
  easing?: string
  toggleTheme: () => void
}
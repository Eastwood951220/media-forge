export type StatusMeta = { text: string; color: string }

export function resolveStatusMeta(
  status: string | undefined,
  labels: Record<string, StatusMeta>,
): StatusMeta {
  if (!status) return { text: '-', color: 'default' }
  return labels[status] ?? { text: status, color: 'default' }
}

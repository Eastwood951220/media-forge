import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App, Form } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import { SavedSecretInput } from './SavedSecretInput'

function setup(loadSavedValue = vi.fn().mockResolvedValue({ value: 'saved-secret' })) {
  const onFinish = vi.fn()
  const view = render(<App><Form onFinish={onFinish} initialValues={{ secret: '' }}>
    <Form.Item name="secret"><SavedSecretInput aria-label="密钥" configured loadSavedValue={loadSavedValue} /></Form.Item>
    <button type="submit">保存</button>
  </Form></App>)
  return { ...view, onFinish, loadSavedValue, eye: () => view.container.querySelector('.ant-input-password-icon')! }
}

describe('SavedSecretInput', () => {
  it('reveals saved values on demand without changing the form or resubmitting the secret', async () => {
    const view = setup()
    expect(view.loadSavedValue).not.toHaveBeenCalled()
    fireEvent.click(view.eye())
    await waitFor(() => expect(screen.getByLabelText('密钥')).toHaveValue('saved-secret'))
    await waitFor(() => expect(screen.getByLabelText('密钥')).toHaveAttribute('type', 'text'))
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => expect(view.onFinish).toHaveBeenCalledWith({ secret: '' }))
    fireEvent.click(view.eye())
    await waitFor(() => expect(screen.getByLabelText('密钥')).toHaveAttribute('type', 'password'))
    expect(screen.getByLabelText('密钥')).toHaveValue('')
    view.unmount()
  })

  it('shows new input without loading the old secret and submits the edit', async () => {
    const view = setup()
    fireEvent.change(screen.getByLabelText('密钥'), { target: { value: 'new-secret' } })
    fireEvent.click(view.eye())
    expect(view.loadSavedValue).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('保存'))
    await waitFor(() => expect(view.onFinish).toHaveBeenCalledWith({ secret: 'new-secret' }))
    view.unmount()
  })

  it('does not overwrite an edit with a delayed saved-value response', async () => {
    let resolve!: (value: { value: string }) => void
    const view = setup(vi.fn(() => new Promise(done => { resolve = done })))
    fireEvent.click(view.eye())
    fireEvent.change(screen.getByLabelText('密钥'), { target: { value: 'new-secret' } })
    await act(async () => resolve({ value: 'old-secret' }))
    expect(screen.getByLabelText('密钥')).toHaveValue('new-secret')
    view.unmount()
  })
})

it('does not cover parent-controlled updates with a pending saved value', async () => {
  let resolve!: (value: { value: string }) => void
  const load = vi.fn(() => new Promise<{ value: string }>(done => { resolve = done }))
  const view = render(<App><SavedSecretInput aria-label="外部密钥" configured value="" loadSavedValue={load} /></App>)
  fireEvent.click(view.container.querySelector('.ant-input-password-icon')!)
  view.rerender(<App><SavedSecretInput aria-label="外部密钥" configured value="updated-outside" loadSavedValue={load} /></App>)
  await act(async () => resolve({ value: 'stale-secret' }))
  expect(screen.getByLabelText('外部密钥')).toHaveValue('updated-outside')
  view.unmount()
})

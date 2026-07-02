import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DashboardPage from '../src/pages/dashboard/DashboardPage'

describe('DashboardPage modern console content', () => {
  it('renders operational dashboard sections', () => {
    render(<DashboardPage />)

    expect(screen.getByRole('heading', { name: 'Operations Console' })).toBeInTheDocument()
    expect(screen.getByText('Media pipeline health')).toBeInTheDocument()
    expect(screen.getByText('Active jobs')).toBeInTheDocument()
    expect(screen.getByText('Queued assets')).toBeInTheDocument()
    expect(screen.getByText('Storage used')).toBeInTheDocument()
    expect(screen.getByText('Recent activity')).toBeInTheDocument()
    expect(screen.getByText('Processing lanes')).toBeInTheDocument()
  })
})

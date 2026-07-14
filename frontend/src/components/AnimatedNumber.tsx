import { useEffect, useRef, useState } from 'react'

interface AnimatedNumberProps {
  value: number
  duration?: number
  separator?: string
  className?: string
}

function AnimatedNumber({ value, duration = 1.5, separator = ',', className }: AnimatedNumberProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const startValue = useRef(0)
  const startTime = useRef<number | null>(null)
  const rafId = useRef<number | null>(null)

  useEffect(() => {
    startValue.current = displayValue
    startTime.current = null

    const animate = (timestamp: number) => {
      if (!startTime.current) {
        startTime.current = timestamp
      }

      const progress = Math.min((timestamp - startTime.current) / (duration * 1000), 1)
      const eased = 1 - Math.pow(1 - progress, 3) // easeOutCubic
      const currentValue = Math.round(startValue.current + (value - startValue.current) * eased)

      setDisplayValue(currentValue)

      if (progress < 1) {
        rafId.current = requestAnimationFrame(animate)
      }
    }

    rafId.current = requestAnimationFrame(animate)

    return () => {
      if (rafId.current) {
        cancelAnimationFrame(rafId.current)
      }
    }
  }, [value, duration])

  const formattedValue = separator ? displayValue.toLocaleString() : displayValue.toString()

  return <span className={className}>{formattedValue}</span>
}

export default AnimatedNumber

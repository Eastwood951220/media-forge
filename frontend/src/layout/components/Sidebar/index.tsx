import { useBreakpoint } from '@/hooks/useBreakpoint'
import DesktopSidebar from './DesktopSidebar'
import MobileDrawer from './MobileDrawer'

function Sidebar() {
  const { isMobile } = useBreakpoint()

  if (isMobile) {
    return <MobileDrawer />
  }

  return <DesktopSidebar />
}

export default Sidebar

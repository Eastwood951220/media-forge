import { Typography } from 'antd'

const { Title, Paragraph } = Typography

function DashboardPage() {
  return (
    <div className="p-8">
      <Title level={1}>Media Forge 🎬</Title>
      <Paragraph>Welcome to Media Forge dashboard.</Paragraph>
    </div>
  )
}

export default DashboardPage

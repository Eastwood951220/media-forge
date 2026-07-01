import { Typography } from 'antd'

const { Title, Paragraph } = Typography

function InitPage() {
  return (
    <div className="p-8">
      <Title level={1}>Initial Setup</Title>
      <Paragraph>Configure your database and Redis connection settings.</Paragraph>
    </div>
  )
}

export default InitPage

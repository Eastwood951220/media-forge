const errorCode: Record<string | number, string> = {
  400: '请求参数错误',
  401: '认证失败，无法访问系统资源',
  403: '当前操作没有权限',
  404: '访问资源不存在',
  409: '数据已存在，请勿重复提交',
  422: '请求参数校验失败',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误',
  default: '系统未知错误，请反馈给管理员',
}

export default errorCode

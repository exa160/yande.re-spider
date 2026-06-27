import axios from 'axios'

// 必要：FastAPI Optional[List[X]] = Query 不识别逗号分隔，必须重复参数 ?a=x&a=y
const paramsSerializer = (params) => {
  const parts = []
  const append = (key, value) => {
    if (value === undefined || value === null) return
    if (Array.isArray(value)) {
      value.forEach((v) => append(key, v))
    } else {
      parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    }
  }
  Object.entries(params || {}).forEach(([k, v]) => append(k, v))
  return parts.join('&')
}

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  paramsSerializer,
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    // 提取错误信息
    const errorInfo = {
      code: error.response?.data?.code || 'UNKNOWN',
      message: error.response?.data?.message || error.message || 'Unknown error',
      detail: error.response?.data?.data?.detail || null
    }
    return Promise.reject(errorInfo)
  }
)

export default api

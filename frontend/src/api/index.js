import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000
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

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

/**
 * 预览图清理
 * @param {'clean_local_previews' | 'clean_all_previews'} mode - 清理模式
 * @param {boolean} dryRun - true 仅评估不删除，false 真实清理
 * @returns {Promise<{code: string, message: string, data: CleanupResult}>}
 */
export async function cleanupPreviews(mode, dryRun) {
  return api({
    url: '/gallery/cache/preview/cleanup',
    method: 'post',
    data: { mode, dry_run: dryRun },
    timeout: 60000,  // 清理操作可能涉及较多文件 IO，延长超时
  })
}

export default api

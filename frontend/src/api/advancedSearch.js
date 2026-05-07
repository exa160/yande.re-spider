/**
 * 高级搜索字符串构建
 * 将查询参数转换为 yande.re API 搜索字符串
 */

/**
 * 解析标签文本中的包含/排除
 * @param {string} text - 标签文本
 * @returns {{ include: string[], exclude: string[] }}
 */
export function parseTags(text) {
  const include = []
  const exclude = []

  if (!text) return { include, exclude }

  text.split(/\s+/).forEach(tag => {
    if (!tag) return
    if (tag.startsWith('-')) {
      const t = tag.substring(1)
      if (t) exclude.push(t)
    } else if (tag.startsWith('+')) {
      const t = tag.substring(1)
      if (t) include.push(t)
    } else {
      include.push(tag)
    }
  })

  return { include, exclude }
}

/**
 * 构建搜索字符串
 * @param {Object} params - 查询参数
 * @param {string} [params.tags] - 标签（支持 +tag -tag 语法）
 * @param {string} [params.author] - 上传者
 * @param {string|string[]} [params.rating] - 评分 (s/q/e)
 * @param {string|string[]} [params.fileType] - 文件格式
 * @param {number} [params.minWidth] - 最小宽度
 * @param {number} [params.maxWidth] - 最大宽度
 * @param {number} [params.minHeight] - 最小高度
 * @param {number} [params.maxHeight] - 最大高度
 * @param {number} [params.minFileSize] - 最小文件大小(KB)
 * @param {number} [params.maxFileSize] - 最大文件大小(KB)
 * @param {number} [params.minScore] - 最小分数
 * @returns {string} - 搜索字符串
 */
export function buildSearchString(params) {
  const parts = []

  // 解析标签
  if (params.tags) {
    const { include, exclude } = parseTags(params.tags)
    parts.push(...include)
    exclude.forEach(tag => parts.push(`-${tag}`))
  }

  // 上传者
  if (params.author) {
    parts.push(`author:${params.author}`)
  }

  // 评分（支持多选）
  if (params.rating) {
    const rating = Array.isArray(params.rating) ? params.rating : [params.rating]
    if (rating.length === 1) {
      parts.push(`rating:${rating[0]}`)
    } else if (rating.length > 1) {
      // 多选时用 OR 连接
      parts.push(`(${rating.map(r => `rating:${r}`).join(' OR ')})`)
    }
  }

  // 文件格式（支持多选）
  if (params.fileType) {
    const types = Array.isArray(params.fileType) ? params.fileType : [params.fileType]
    if (types.length === 1) {
      parts.push(`ext:${types[0]}`)
    } else if (types.length > 1) {
      parts.push(`(${types.map(t => `ext:${t}`).join(' OR ')})`)
    }
  }

  // 宽度
  if (params.minWidth != null) {
    parts.push(`width:>=${params.minWidth}`)
  }
  if (params.maxWidth != null) {
    parts.push(`width:<=${params.maxWidth}`)
  }

  // 高度
  if (params.minHeight != null) {
    parts.push(`height:>=${params.minHeight}`)
  }
  if (params.maxHeight != null) {
    parts.push(`height:<=${params.maxHeight}`)
  }

  // 文件大小 (KB -> bytes 约)
  if (params.minFileSize != null) {
    parts.push(`filesize:>=${params.minFileSize}`)
  }
  if (params.maxFileSize != null) {
    parts.push(`filesize:<=${params.maxFileSize}`)
  }

  // 分数
  if (params.minScore != null) {
    parts.push(`score:>=${params.minScore}`)
  }

  return parts.join(' ')
}

/**
 * 构建 API 请求参数
 * @param {Object} queryParams - 前端查询参数
 * @returns {Object} - API 请求参数
 */
export function buildApiParams(queryParams) {
  const apiTags = buildSearchString({
    tags: queryParams.tags,
    rating: queryParams.rating,
    fileType: queryParams.fileType,
    minWidth: queryParams.minWidth,
    maxWidth: queryParams.maxWidth,
    minHeight: queryParams.minHeight,
    maxHeight: queryParams.maxHeight,
    minFileSize: queryParams.minFileSize,
    maxFileSize: queryParams.maxFileSize,
    minScore: queryParams.minScore,
  })

  return {
    tags: apiTags,
    author: queryParams.author || undefined,
    page: 1,
    page_size: queryParams.pageSize || 20,
    sort_by: queryParams.sortBy || 'created_at',
    sort_order: queryParams.sortOrder || 'desc',
  }
}

export default {
  parseTags,
  buildSearchString,
  buildApiParams
}

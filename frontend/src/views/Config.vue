<template>
  <div class="config-page">
    <!-- 左侧菜单 -->
    <div class="config-menu">
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'api' }"
        @click="activeMenu = 'api'"
      >
        API配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'downloader' }"
        @click="activeMenu = 'downloader'"
      >
        下载器配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'database' }"
        @click="activeMenu = 'database'"
      >
        数据库配置
      </div>
      <!-- Task 19：收藏夹单独分页，置于高级功能之上；3 个新开关 + 5 个迁移偏好全在此 -->
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'favorites' }"
        @click="activeMenu = 'favorites'"
      >
        收藏夹配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'advanced' }"
        @click="activeMenu = 'advanced'"
      >
        高级功能
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'about' }"
        @click="activeMenu = 'about'"
      >
        关于
      </div>
    </div>

    <!-- 右侧内容 -->
    <div class="config-content">
      <!-- API配置 -->
      <div v-show="activeMenu === 'api'" class="config-section">
        <el-form :model="apiConfig" label-width="100px" class="config-form">
          <el-form-item label="重试次数">
            <el-input-number v-model="apiConfig.retry_times" :min="0" :max="500" />
          </el-form-item>
          <el-form-item label="超时时间">
            <el-input-number v-model="apiConfig.timeout" :min="1" :max="300" /> 秒
          </el-form-item>
          <el-form-item label="代理模式">
            <el-segmented
              v-model="apiConfig.proxy_enable"
              :options="proxyModeOptions"
              :direction="segmentedDirection"
              class="proxy-mode-segmented"
            />
          </el-form-item>
          <el-form-item v-if="apiConfig.proxy_enable === true" label="代理地址">
            <el-input v-model="apiConfig.proxy" placeholder="http://host:port 或 socks5://host:port" size="small" />
          </el-form-item>
          <el-form-item v-else-if="apiConfig.proxy_enable === null" label="提示">
            <el-alert type="info" :closable="false" show-icon>
              使用系统环境变量中的代理配置
            </el-alert>
          </el-form-item>
          <el-form-item label="请求头">
            <el-button @click="showHeadersDialog = true" size="small">
              编辑
            </el-button>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveApiConfig" :loading="saving" size="small">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 下载器配置 -->
      <div v-show="activeMenu === 'downloader'" class="config-section">
        <el-form :model="downloaderConfig" label-width="100px" class="config-form">
          <el-form-item label="并发下载数">
            <el-input-number v-model="downloaderConfig.max_concurrent_tasks" :min="1" :max="10" />
          </el-form-item>
          <el-form-item label="分块大小">
            <el-input-number v-model="downloaderConfig.chunk_size" :min="1" :max="102400" /> KB
          </el-form-item>
          <el-form-item label="分段大小">
            <el-input-number v-model="downloaderConfig.split_size" :min="1" :max="1000000" /> MB
          </el-form-item>
          <el-form-item label="重试次数">
            <el-input-number v-model="downloaderConfig.retry_times" :min="0" :max="500" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveDownloaderConfig" :loading="saving" size="small">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 数据库配置 -->
      <div v-show="activeMenu === 'database'" class="config-section">
        <el-form :model="databaseConfig" label-width="100px" class="config-form">
          <el-form-item label="启用数据库">
            <el-switch v-model="databaseConfig.enable" />
          </el-form-item>
          <template v-if="databaseConfig.enable">
            <el-form-item label="主机">
              <el-input v-model="databaseConfig.host" size="small" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="databaseConfig.port" :min="1" :max="65535" size="small" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="databaseConfig.user" size="small" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="databaseConfig.password" type="password" show-password size="small" />
            </el-form-item>
            <el-form-item label="数据库名">
              <el-input v-model="databaseConfig.schema_name" size="small" />
            </el-form-item>
          </template>
          <el-form-item v-else>
            <el-alert type="info" :closable="false" show-icon>
              禁用后将使用 SQLite 本地数据库
            </el-alert>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveDatabaseConfig" :loading="saving" size="small">
              保存
            </el-button>
            <el-button @click="testConnection" :loading="testing" size="small">
              测试连接
            </el-button>
            <el-button @click="resetConfig" size="small">
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 关于 -->
      <div v-show="activeMenu === 'about'" class="config-section about-section">
        <div class="about-content">
          <div class="about-title">Yande.re Local Picture Manager</div>
          <div class="about-version">Version {{ appVersion }}</div>
          <div class="about-desc">Yande.re 本地图片管理工具</div>
          <div class="about-links">
            <a href="https://github.com/exa160/yande.re-spider" target="_blank" class="github-link">
              <svg height="20" width="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.807 5.625-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              GitHub
            </a>
          </div>
          <div class="about-protection" v-if="tamperDetected">
            <el-alert type="warning" :closable="false" show-icon>
              检测到异常操作，如需帮助请提issue
            </el-alert>
          </div>
        </div>
      </div>

      <!-- 高级功能 -->
      <div v-show="activeMenu === 'advanced'" class="config-section">
        <!-- 缓存更新 section -->
        <div class="advanced-section">
          <div class="advanced-title">缓存更新</div>
          <div class="advanced-desc">从 yande.re API 刷新标签和艺术家信息到本地数据库（首次全量，之后增量）</div>

          <div class="cache-stats">
            <div class="stat-item">
              <span class="stat-label">标签缓存</span>
              <span class="stat-value">{{ tagStats.total || 0 }}</span>
              <span class="stat-tip">最大ID: {{ tagStats.max_id || 0 }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">艺术家缓存</span>
              <span class="stat-value">{{ artistStats.total || 0 }}</span>
            </div>
          </div>

          <div class="refresh-controls">
            <div class="refresh-item refresh-item--stacked refresh-item--tag-refresh">
              <div class="refresh-main">
                <div class="refresh-info">
                  <div class="refresh-name">更新标签</div>
                  <div class="refresh-params">
                    <span class="param-tip">从 ID {{ tagStats.max_id || 0 }} 开始增量更新</span>
                    <span class="param-tip" style="color: #E6A23C; margin-left: 8px;">长按全量刷新</span>
                  </div>
                </div>
                <el-button
                  type="primary"
                  @click="handleRefreshTags"
                  @mousedown.native="startLongPress"
                  @mouseup.native="endLongPress"
                  @mouseleave.native="endLongPress"
                  @touchstart.native="startLongPress"
                  @touchend.native="endLongPress"
                  :loading="refreshingTags"
                  size="small"
                >
                  刷新
                </el-button>
              </div>

              <!-- 定时更新并入「更新标签」框：开关与频率/时间/星期/Cron 使用同一套选项行 -->
              <div class="tag-cache-schedule">
                <div class="tag-cache-field tag-cache-toggle">
                  <span class="tag-cache-label">定时更新</span>
                  <span class="tag-cache-summary">{{ tagCacheSummary }}</span>
                  <span v-if="savingTagCache" class="tag-cache-saving">保存中…</span>
                  <el-radio-group
                    v-model="tagCacheForm.enableDailyRefresh"
                    size="small"
                    class="tag-cache-enable"
                    @change="onTagCacheToggle"
                  >
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>

                <div v-if="tagCacheForm.enableDailyRefresh" class="tag-cache-fields">
                  <div class="tag-cache-field">
                    <span class="tag-cache-label">频率</span>
                    <el-radio-group
                      v-model="tagCacheForm.freq"
                      size="small"
                      @change="onTagCacheFreqChange"
                    >
                      <el-radio-button value="daily">每天</el-radio-button>
                      <el-radio-button value="weekly">每周</el-radio-button>
                      <el-radio-button value="custom">自定义</el-radio-button>
                    </el-radio-group>
                  </div>

                  <div v-if="tagCacheForm.freq !== TAG_CACHE_FREQ_CUSTOM" class="tag-cache-field">
                    <span class="tag-cache-label">时间</span>
                    <el-time-picker
                      v-model="tagCacheForm.time"
                      format="HH:mm"
                      value-format="HH:mm"
                      placeholder="选择时间"
                      size="small"
                      class="tag-cache-time-picker"
                      @change="onTagCacheTimeChange"
                    />
                  </div>

                  <div v-if="tagCacheForm.freq === TAG_CACHE_FREQ_WEEKLY" class="tag-cache-field">
                    <span class="tag-cache-label">星期</span>
                    <el-checkbox-group
                      v-model="tagCacheForm.weekdays"
                      size="small"
                      @change="onTagCacheWeekdayChange"
                    >
                      <el-checkbox
                        v-for="d in WEEKDAY_OPTIONS"
                        :key="d.value"
                        :value="d.value"
                      >{{ d.label }}</el-checkbox>
                    </el-checkbox-group>
                  </div>

                  <div v-if="tagCacheForm.freq === TAG_CACHE_FREQ_CUSTOM" class="tag-cache-field">
                    <span class="tag-cache-label">Cron</span>
                    <el-input
                      v-model="tagCacheForm.refreshCron"
                      size="small"
                      class="tag-cache-cron-input"
                      placeholder="分 时 日 月 周"
                      @blur="onTagCacheCronCommit"
                      @keydown.enter="onTagCacheCronCommit"
                    />
                    <a
                      class="tag-cache-cron-link"
                      href="https://crontab.guru/"
                      target="_blank"
                      rel="noopener"
                    >cron 语法参考</a>
                  </div>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">更新艺术家</div>
                <div class="refresh-params">
                  <el-input-number v-model="refreshArtistsParams.max_pages" :min="1" :max="100" size="small" /> 页
                  <span class="param-tip">(每页100条)</span>
                </div>
              </div>
              <el-button
                type="primary"
                @click="handleRefreshArtists"
                :loading="refreshingArtists"
                size="small"
              >
                刷新
              </el-button>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">预览图清理</div>
                <div class="refresh-params">
                  <span class="param-tip">删除 downloads/previews/ 下的缩略图缓存</span>
                </div>
              </div>
              <div class="cleanup-buttons">
                <el-button
                  type="primary"
                  size="small"
                  @click="openCleanupDialog('clean_local_previews')"
                >
                  本地清理
                </el-button>
                <el-button
                  type="warning"
                  size="small"
                  @click="openCleanupDialog('clean_all_previews')"
                >
                  全量清理
                </el-button>
              </div>
            </div>


          </div>
        </div>

        <!-- Task 19：收藏夹独立分页（已从高级里抽出，置于高级之上） -->
      </div>

      <!-- Task 19：收藏夹独立分页（放在高级之上，避免与高级功能混合导致配置散乱） -->
      <div v-show="activeMenu === 'favorites'" class="config-section favorites-section">
        <div class="favorites-inner-section">
          <div class="advanced-title">收藏夹</div>
          <div class="advanced-desc">配置收藏夹按钮显示、我的最爱 / 随机浏览 / 最近下载总开关，以及每文件夹预览图数量</div>

          <div class="refresh-controls">
            <!-- 主页显示收藏夹（入口显隐，收藏夹模块总开关） -->
            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">主页显示收藏夹</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.buttonMode" size="small">
                    <el-radio-button label="hidden">关闭</el-radio-button>
                    <el-radio-button label="shown">开启</el-radio-button>
                    <el-radio-button label="default">默认显示</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <!-- 我的最爱总开关：关闭时后端 include_favorite_status 联动不连表，避免 DB 开销 -->
            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">我的最爱</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.enableMyFavorites" size="small">
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">在线图片收藏自动下载</div>
                <div class="refresh-params">
                  <el-radio-group
                    v-model="favoritesForm.enableFavoriteAutodownload"
                    size="small"
                    :disabled="!favoritesForm.enableMyFavorites"
                  >
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">随机浏览</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.enableRandomBrowse" size="small">
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <!-- 最近下载总开关：独立功能（数据源是 download_task 的已完成记录），
                 与「我的最爱」无父子依赖，因此不启用随父开关禁用 -->
            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">最近下载</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.enableRecentDownloads" size="small">
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">收藏夹大小</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.tileSize" size="small">
                    <el-radio-button label="adaptive">自适应</el-radio-button>
                    <el-radio-button label="4">4张</el-radio-button>
                    <el-radio-button label="6">6张</el-radio-button>
                    <el-radio-button label="8">8张</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">收藏夹预览图顺序</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.previewOrder" size="small">
                    <el-radio-button label="random">随机</el-radio-button>
                    <el-radio-button label="desc">最新优先</el-radio-button>
                    <el-radio-button label="asc">最早优先</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">收藏夹预览包含未下载图片</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.includeOnline" size="small">
                    <el-radio-button :label="false">关闭</el-radio-button>
                    <el-radio-button :label="true">开启</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">每页收藏夹个数</div>
                <div class="refresh-params">
                  <el-radio-group v-model="favoritesForm.folderPageSize" size="small">
                    <el-radio-button :value="8">8</el-radio-button>
                    <el-radio-button :value="12">12</el-radio-button>
                    <el-radio-button :value="20">20</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </div>

            <div class="favorites-save-row">
              <el-button
                type="primary"
                size="small"
                :loading="savingFavorites"
                @click="saveFavorites"
              >
                保存收藏夹配置
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <PreviewCleanupDialog v-model="showCleanupDialog" :mode="selectedCleanupMode" />
    <HeadersEditorDialog
      v-model="showHeadersDialog"
      :headers="apiConfig.headers"
      @save="saveHeaders"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import { tagCacheApi } from '@/api/tagCache'
import PreviewCleanupDialog from '@/components/PreviewCleanupDialog.vue'
import HeadersEditorDialog from '@/components/HeadersEditorDialog.vue'
import { useFavoritesConfig, saveFavoritesConfig } from '@/composables/useFavoritesConfig'

// 编译时注入的版本号 - 单一来源 (vite.config.js define 替换)
const appVersion = __APP_VERSION__

const proxyModeOptions = [
  { label: '关闭', value: false },
  { label: '自定义', value: true },
  { label: '系统代理', value: null },
]

const apiConfig = ref({
  retry_times: 3,
  timeout: 30,
  proxy_enable: null,
  proxy: '',
  headers: {}
})

const downloaderConfig = ref({
  thread_num: 4,
  max_concurrent_tasks: 3,
  chunk_size: 10,
  split_size: 200,
  retry_times: 3
})

const databaseConfig = ref({
  enable: false,
  host: 'localhost',
  port: 3306,
  user: 'root',
  password: '',
  schema_name: 'Pictures'
})

const saving = ref(false)
const activeMenu = ref('api')

// 收藏夹 UI 配置（与 Gallery 共享 singleton composable）
const {
  buttonMode,
  tileSize,
  previewOrder,
  includeOnline,
  folderPageSize,
  enableMyFavorites,
  enableRandomBrowse,
  enableFavoriteAutodownload,
  enableRecentDownloads,
} = useFavoritesConfig()
// 本地表单：用 composable 初值初始化，watch 同步回 composable
// （不直接 v-model 到 composable，避免 Gallery 端外部修改造成循环）
const favoritesForm = reactive({
  buttonMode: buttonMode.value,
  tileSize: tileSize.value,
  previewOrder: previewOrder.value,
  includeOnline: includeOnline.value,
  folderPageSize: folderPageSize.value,
  enableMyFavorites: enableMyFavorites.value,
  enableRandomBrowse: enableRandomBrowse.value,
  enableFavoriteAutodownload: enableFavoriteAutodownload.value,
  enableRecentDownloads: enableRecentDownloads.value,
})
watch(favoritesForm, (val) => {
  if (buttonMode.value !== val.buttonMode) {
    buttonMode.value = val.buttonMode
  }
  if (tileSize.value !== val.tileSize) {
    tileSize.value = val.tileSize
  }
  if (previewOrder.value !== val.previewOrder) {
    previewOrder.value = val.previewOrder
  }
  if (includeOnline.value !== val.includeOnline) {
    includeOnline.value = val.includeOnline
  }
  if (folderPageSize.value !== val.folderPageSize) {
    folderPageSize.value = val.folderPageSize
  }
  if (enableMyFavorites.value !== val.enableMyFavorites) {
    enableMyFavorites.value = val.enableMyFavorites
  }
  if (enableRandomBrowse.value !== val.enableRandomBrowse) {
    enableRandomBrowse.value = val.enableRandomBrowse
  }
  if (enableFavoriteAutodownload.value !== val.enableFavoriteAutodownload) {
    enableFavoriteAutodownload.value = val.enableFavoriteAutodownload
  }
  if (enableRecentDownloads.value !== val.enableRecentDownloads) {
    enableRecentDownloads.value = val.enableRecentDownloads
  }
})
// 保存收藏夹配置（5 个新开关 + 5 个迁移偏好 → PUT /config/favorites）
const savingFavorites = ref(false)
async function saveFavorites() {
  savingFavorites.value = true
  try {
    await saveFavoritesConfig({
      enable_my_favorites: favoritesForm.enableMyFavorites,
      enable_random_browse: favoritesForm.enableRandomBrowse,
      enable_recent_downloads: favoritesForm.enableRecentDownloads,
      enable_favorite_autodownload: favoritesForm.enableFavoriteAutodownload,
      button_mode: favoritesForm.buttonMode,
      tile_size: favoritesForm.tileSize,
      preview_order: favoritesForm.previewOrder,
      include_online: favoritesForm.includeOnline,
      folder_page_size: favoritesForm.folderPageSize,
    })
    ElMessage.success('收藏夹配置已保存')
  } catch (error) {
    ElMessage.error('保存收藏夹配置失败')
  } finally {
    savingFavorites.value = false
  }
}

// 窄屏下代理模式 segmented 垂直堆叠（<540px）
const SEGMENTED_VERTICAL_BREAKPOINT = 540
const segmentedDirection = ref('horizontal')
const mqlSegmented = window.matchMedia(`(max-width: ${SEGMENTED_VERTICAL_BREAKPOINT - 1}px)`)
const updateSegmentedDirection = (e) => {
  segmentedDirection.value = e.matches ? 'vertical' : 'horizontal'
}
updateSegmentedDirection(mqlSegmented)
if (mqlSegmented.addEventListener) {
  mqlSegmented.addEventListener('change', updateSegmentedDirection)
} else {
  // Safari < 14 fallback
  mqlSegmented.addListener(updateSegmentedDirection)
}
const testing = ref(false)
const tamperDetected = ref(false)
const showCleanupDialog = ref(false)
const selectedCleanupMode = ref(null)
const showHeadersDialog = ref(false)

function openCleanupDialog(mode) {
  selectedCleanupMode.value = mode
  showCleanupDialog.value = true
}

// 高级功能 - 缓存更新
const tagStats = ref({ total: 0, max_id: 0 })
const artistStats = ref({ total: 0 })
const refreshingTags = ref(false)
const refreshingArtists = ref(false)
const refreshTagsParams = ref({ after_id: 0 })
const refreshArtistsParams = ref({ page: 1, limit: 100, max_pages: 10 })

// 标签缓存定时更新配置（PUT /config/tag-cache，保存后端立即重挂 APScheduler job）
//
// 交互契约：**选择即保存**。这里没有「保存」按钮，任一控件 change 都直接 PUT。
// 唯一真值是 tagCacheForm.refreshCron（后端只认这个 cron 字符串），
// freq / time / weekdays 是它的 UI 投影：改控件 → 重算 cron → 提交；
// 从后端读回 → 解析 cron → 回填控件。两条路共用 parse/build 两个纯函数。
const TAG_CACHE_FREQ_DAILY = 'daily'
const TAG_CACHE_FREQ_WEEKLY = 'weekly'
const TAG_CACHE_FREQ_CUSTOM = 'custom'

// cron 周字段 0=周日 … 6=周六；UI 按「一…日」顺序展示，故显式给出顺序表
const WEEKDAY_OPTIONS = [
  { value: 1, label: '一' },
  { value: 2, label: '二' },
  { value: 3, label: '三' },
  { value: 4, label: '四' },
  { value: 5, label: '五' },
  { value: 6, label: '六' },
  { value: 0, label: '日' },
]
const WEEKDAY_LABEL = Object.fromEntries(WEEKDAY_OPTIONS.map((d) => [d.value, d.label]))

const tagCacheForm = reactive({
  enableDailyRefresh: true,
  freq: TAG_CACHE_FREQ_DAILY,
  // 初值与后端 TagCacheConfig 默认值一致：load 失败时它就是可信的回滚目标
  time: '04:17',
  weekdays: [1],
  refreshCron: '17 4 * * *',
})
const savingTagCache = ref(false)

const pad2 = (n) => String(n).padStart(2, '0')

// cron → 预设。解析不出来时返回 null，调用方必须回退「自定义」原样展示，
// **不能猜**：猜错等于一次无意的自动保存就把用户的 cron 改掉了。
// 刻意只认「每天 / 每周」两种形态：分 时 必须是具体数字、日 月 必须是 *、
// 周字段只能是 0-6 的数字或数字列表；`0 */2 * * *`、`1-5`、带秒的六段等一律 null。
const parseTagCacheCron = (cron) => {
  const parts = String(cron || '').trim().split(/\s+/)
  if (parts.length !== 5) return null
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts
  if (!/^\d{1,2}$/.test(minute) || !/^\d{1,2}$/.test(hour)) return null
  if (dayOfMonth !== '*' || month !== '*') return null
  const m = Number(minute)
  const h = Number(hour)
  if (m > 59 || h > 23) return null

  if (dayOfWeek === '*') {
    return { freq: TAG_CACHE_FREQ_DAILY, time: `${pad2(h)}:${pad2(m)}`, weekdays: [] }
  }
  const days = dayOfWeek.split(',')
  if (!days.every((d) => /^[0-6]$/.test(d))) return null
  const weekdays = [...new Set(days.map(Number))]
    .sort((a, b) => WEEKDAY_OPTIONS.findIndex((o) => o.value === a)
                  - WEEKDAY_OPTIONS.findIndex((o) => o.value === b))
  if (weekdays.length === 0) return null
  return { freq: TAG_CACHE_FREQ_WEEKLY, time: `${pad2(h)}:${pad2(m)}`, weekdays }
}

// 预设控件 → cron（每周一个都没选时退回每天：空周字段是非法 cron，
// 与其让后端 422 再回滚，不如在生成时就给出合法值）。
// 数字不做补零，与后端默认值「17 4 * * *」及 crontab.guru 惯例一致。
const buildTagCacheCron = () => {
  const [rawHour, rawMinute] = String(tagCacheForm.time || '00:00').split(':')
  const h = Number(rawHour) || 0
  const m = Number(rawMinute) || 0
  const head = `${m} ${h}`
  if (tagCacheForm.freq !== TAG_CACHE_FREQ_WEEKLY) return `${head} * * *`
  const days = [...new Set(tagCacheForm.weekdays)].sort(
    (a, b) => WEEKDAY_OPTIONS.findIndex((o) => o.value === a)
            - WEEKDAY_OPTIONS.findIndex((o) => o.value === b)
  )
  return `${head} * * ${days.length ? days.join(',') : '*'}`
}

// 控件变化后重算 cron（自定义模式下 cron 由输入框直接维护，这里不动它）
const syncCronFromControls = () => {
  if (tagCacheForm.freq === TAG_CACHE_FREQ_CUSTOM) return
  tagCacheForm.refreshCron = buildTagCacheCron()
}

// 后端 cron → UI 控件
const applyTagCacheCron = (cron) => {
  const raw = String(cron || '').trim()
  tagCacheForm.refreshCron = raw
  const parsed = parseTagCacheCron(raw)
  if (!parsed) {
    // 不可解析（如 `0 */2 * * *`）：回退自定义并原样展示，绝不解析成错误的预设
    tagCacheForm.freq = TAG_CACHE_FREQ_CUSTOM
    return
  }
  tagCacheForm.freq = parsed.freq
  tagCacheForm.time = parsed.time
  // 每天形态不携带星期，保留用户此前的星期选择，切到「每周」时才有默认值
  if (parsed.weekdays.length) tagCacheForm.weekdays = [...parsed.weekdays]
}

// 摘要行：随开关 / 频率 / 时间实时变化，避免用户对「到底什么时候会刷」没有预期
const tagCacheSummary = computed(() => {
  if (!tagCacheForm.enableDailyRefresh) return '已关闭'
  if (tagCacheForm.freq === TAG_CACHE_FREQ_CUSTOM) {
    return `自定义 ${tagCacheForm.refreshCron}`
  }
  if (tagCacheForm.freq === TAG_CACHE_FREQ_WEEKLY) {
    const names = [...tagCacheForm.weekdays]
      .sort((a, b) => WEEKDAY_OPTIONS.findIndex((o) => o.value === a)
                    - WEEKDAY_OPTIONS.findIndex((o) => o.value === b))
      .map((d) => WEEKDAY_LABEL[d])
    if (names.length) return `每周${names.join('、')} ${tagCacheForm.time}`
  }
  return `每天 ${tagCacheForm.time}`
})

const loadTagCacheConfig = async () => {
  try {
    const res = await api.get('/config/tag-cache')
    const c = res?.data
    if (!c || typeof c !== 'object') return
    if ('enable_daily_refresh' in c) tagCacheForm.enableDailyRefresh = !!c.enable_daily_refresh
    if (typeof c.refresh_cron === 'string' && c.refresh_cron) applyTagCacheCron(c.refresh_cron)
    // 读回来的这份就是服务端当前状态，记为回滚目标
    tagCacheSynced = takeTagCacheSnapshot()
  } catch (e) {
    console.warn('加载标签缓存配置失败:', e?.message || e)
  }
}

// 自动保存的串行化：
// 1) PUT 成功会触发后端重挂 APScheduler job，并发 PUT 会互相覆盖 → 用 promise 链串行；
// 2) 连续操作合并成「最后一次状态」：每轮真正发请求时读的是**当下**的表单值，
//    中间态不会发出，因此不会出现「先发旧值、后发新值」把结果倒回去；
// 3) 组件卸载后不再回写状态（否则响应回来时组件已销毁，界面与实际配置不符）。
let tagCacheSaveChain = Promise.resolve()
let tagCacheSavePending = false
let tagCacheDisposed = false

const takeTagCacheSnapshot = () => ({
  enableDailyRefresh: tagCacheForm.enableDailyRefresh,
  freq: tagCacheForm.freq,
  time: tagCacheForm.time,
  weekdays: [...tagCacheForm.weekdays],
  refreshCron: tagCacheForm.refreshCron,
})

const restoreTagCacheSnapshot = (s) => {
  tagCacheForm.enableDailyRefresh = s.enableDailyRefresh
  tagCacheForm.freq = s.freq
  tagCacheForm.time = s.time
  tagCacheForm.weekdays = [...s.weekdays]
  tagCacheForm.refreshCron = s.refreshCron
}

// 「服务端已确认的那份状态」：加载成功后 / 每次 PUT 成功后刷新。
// 保存失败要回滚到这里 —— 而不是回滚到本次请求发出去前的表单值
// （那个值正是没存上的坏值，回滚到它等于没回滚）。
let tagCacheSynced = takeTagCacheSnapshot()

const runTagCacheSave = async () => {
  while (tagCacheSavePending) {
    tagCacheSavePending = false
    const snapshot = takeTagCacheSnapshot()
    try {
      await api.put('/config/tag-cache', {
        enable_daily_refresh: snapshot.enableDailyRefresh,
        refresh_cron: snapshot.refreshCron.trim(),
      })
      tagCacheSynced = snapshot
      if (!tagCacheDisposed) ElMessage.success('定时更新配置已保存')
    } catch (error) {
      // cron 非法时后端 Pydantic validator 返回 422，这里把原因透出。
      // 只在「没有更新的意图排队」时回滚：若用户在这期间又改了控件，
      // 回滚会把他的新操作一起冲掉（而新状态本来就会覆盖这次失败的结果）。
      if (!tagCacheDisposed && !tagCacheSavePending) restoreTagCacheSnapshot(tagCacheSynced)
      if (!tagCacheDisposed) {
        ElMessage.error('保存失败：' + (error?.message || 'cron 表达式非法'))
      }
      return // 失败后不再继续合并后续状态，避免连环回滚
    }
  }
}

const saveTagCache = () => {
  tagCacheSavePending = true
  savingTagCache.value = true
  tagCacheSaveChain = tagCacheSaveChain
    .then(runTagCacheSave)
    .catch(() => {})
    .finally(() => { savingTagCache.value = false })
  return tagCacheSaveChain
}

const onTagCacheToggle = () => saveTagCache()

const onTagCacheFreqChange = () => {
  // 从「自定义」切回预设时，用 cron 里能解析出的时间/星期回填控件，
  // 否则控件显示的时间与真正生效的 cron 会各说各话
  if (tagCacheForm.freq !== TAG_CACHE_FREQ_CUSTOM) {
    const parsed = parseTagCacheCron(tagCacheForm.refreshCron)
    if (parsed) {
      tagCacheForm.time = parsed.time
      if (parsed.weekdays.length) tagCacheForm.weekdays = [...parsed.weekdays]
    }
  }
  syncCronFromControls()
  saveTagCache()
}

const onTagCacheTimeChange = (value) => {
  // el-time-picker 的 change 只在确认选择后触发，不是实时输入
  if (value) tagCacheForm.time = value
  syncCronFromControls()
  saveTagCache()
}

const onTagCacheWeekdayChange = () => {
  syncCronFromControls()
  saveTagCache()
}

// 自定义 cron：只在 blur / 回车时保存。挂到 input 上会让半截表达式（如 "0 5"）
// 直接打后端 → validator 422 + 回滚，输入过程被反复打断。
// 用 keydown.enter（ElInput 显式 emit 的 keydown）而不是 keyup，后者要靠冒泡穿透组件根节点。
// 也不在提交时改 freq：用户进「自定义」就是想手写表达式，自动翻回预设反而是惊喜。
const onTagCacheCronCommit = () => {
  tagCacheForm.refreshCron = tagCacheForm.refreshCron.trim()
  saveTagCache()
}

// 长按定时器
const LONG_PRESS_DURATION = 500
let longPressTimer = null

const startLongPress = () => {
  longPressTimer = setTimeout(async () => {
    longPressTimer = null
    try {
      await ElMessageBox.confirm(
        '全量更新将清空现有标签缓存并重新获取所有标签，此操作不可恢复。是否继续？',
        '全量更新确认',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    
    refreshingTags.value = true
    try {
      const result = await tagCacheApi.refreshTags({ full_refresh: true, limit: 0 })
      ElMessage.success(`全量刷新已启动，预计获取 ${result.data.total_updated || '大量'} 标签`)
      await loadCacheStats()
    } catch (error) {
      ElMessage.error('全量更新失败')
    } finally {
      refreshingTags.value = false
    }
  }, LONG_PRESS_DURATION)
}

const endLongPress = () => {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
  }
}

const loadCacheStats = async () => {
  try {
    const [tagsRes, artistsRes] = await Promise.all([
      tagCacheApi.getTagsStats(),
      tagCacheApi.getArtistsStats()
    ])
    tagStats.value = tagsRes.data || {}
    artistStats.value = artistsRes.data || {}
  } catch (error) {
    console.error('Load cache stats error:', error)
  }
}

const handleRefreshTags = async () => {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
    return
  }
  
  refreshingTags.value = true
  try {
    const result = await tagCacheApi.refreshTags({ after_id: tagStats.value.max_id || 0 })
    ElMessage.success(`标签增量更新完成: 更新了 ${result.data.total_updated} 条 (最新ID: ${result.data.last_id})`)
    await loadCacheStats()
  } catch (error) {
    ElMessage.error('标签更新失败')
  } finally {
    refreshingTags.value = false
  }
}

const handleRefreshArtists = async () => {
  refreshingArtists.value = true
  try {
    const result = await tagCacheApi.refreshArtists(refreshArtistsParams.value)
    // 后端异步处理时 data 为 null，显示 message 即可
    if (result.data) {
      ElMessage.success(`艺术家更新完成: 更新了 ${result.data.total_updated} 条 (共 ${result.data.pages_done} 页)`)
    } else {
      ElMessage.success(result.message || '艺术家刷新任务已启动')
    }
    await loadCacheStats()
  } catch (error) {
    ElMessage.error('艺术家更新失败')
  } finally {
    refreshingArtists.value = false
  }
}

// 防修改检测状态
const originalElements = new Map()
let protectionInterval = null
let devToolsOpen = false

// 保存关键元素的原始内容
const saveOriginalContent = () => {
  const elements = document.querySelectorAll('.about-title, .about-version, .about-desc, .github-link')
  elements.forEach((el, index) => {
    originalElements.set(index, {
      content: el.innerHTML,
      attributes: el.getAttribute('class'),
      style: el.getAttribute('style')
    })
  })
}

// 检测开发者工具
const detectDevTools = () => {
  const threshold = 160
  const widthThreshold = window.outerWidth - window.innerWidth > threshold
  const heightThreshold = window.outerHeight - window.innerHeight > threshold
  
  if (widthThreshold || heightThreshold) {
    return true
  }
  
  // 检测 console.log 劫持
  const originalLog = console.log
  let logCalled = false
  console.log = function(...args) {
    logCalled = true
    return originalLog.apply(console, args)
  }
  setTimeout(() => {
    if (logCalled) {
      console.log = originalLog
    }
  }, 1000)
  
  return false
}

// 启动防护
const startProtection = () => {
  // 保存初始状态
  saveOriginalContent()
  
  // 定期检测元素变化
  protectionInterval = setInterval(() => {
    // 检测开发者工具
    if (detectDevTools() && !devToolsOpen) {
      devToolsOpen = true
      tamperDetected.value = true
    }
    
    // 检测元素内容变化
    const elements = document.querySelectorAll('.about-title, .about-version, .about-desc, .github-link')
    elements.forEach((el, index) => {
      const original = originalElements.get(index)
      if (original) {
        const currentContent = el.innerHTML
        const currentClass = el.getAttribute('class')
        const currentStyle = el.getAttribute('style')
        
        if (currentContent !== original.content || 
            currentClass !== original.attributes || 
            currentStyle !== original.style) {
          // 恢复原始内容
          el.innerHTML = original.content
          el.setAttribute('class', original.attributes)
          if (original.style) {
            el.setAttribute('style', original.style)
          } else {
            el.removeAttribute('style')
          }
          tamperDetected.value = true
        }
      }
    })
  }, 500)
}

// 停止防护
const stopProtection = () => {
  if (protectionInterval) {
    clearInterval(protectionInterval)
    protectionInterval = null
  }
}

// 禁用右键
const disableContextMenu = (e) => {
  if (activeMenu.value === 'about') {
    e.preventDefault()
    return false
  }
}

// 监听键盘事件
const handleKeyDown = (e) => {
  if (activeMenu.value !== 'about') return
  
  // 禁用 F12
  if (e.key === 'F12') {
    e.preventDefault()
    return false
  }
  
  // 禁用 Ctrl+Shift+I / Ctrl+Shift+J / Ctrl+Shift+C
  if (e.ctrlKey && e.shiftKey && ['I', 'J', 'C'].includes(e.key)) {
    e.preventDefault()
    return false
  }
  
  // 禁用 Ctrl+U (查看源码)
  if (e.ctrlKey && e.key === 'u') {
    e.preventDefault()
    return false
  }
}

const loadConfig = async () => {
  try {
    const response = await api.get('/config')
    const config = response.data
    apiConfig.value = {
      retry_times: config.yande_api.retry,
      timeout: config.yande_api.timeout,
      proxy_enable: config.yande_api.proxy_enable ?? null,
      proxy: config.yande_api.proxies?.http || '',
      headers: config.yande_api.headers || {}
    }
    downloaderConfig.value = {
      thread_num: config.downloader.thread_num,
      max_concurrent_tasks: config.downloader.max_concurrent_tasks,
      chunk_size: Math.round(config.downloader.chunk_size / 1024),  // 字节 -> KB
      split_size: Math.round(config.downloader.split_size / (1024 * 1024)),  // 字节 -> MB
      retry_times: config.downloader.retry_times
    }
    databaseConfig.value = config.database
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

const saveApiConfig = async () => {
  saving.value = true
  try {
    const payload = {
      retry: apiConfig.value.retry_times,
      timeout: apiConfig.value.timeout,
      proxy_enable: apiConfig.value.proxy_enable,
      proxies: {
        http: apiConfig.value.proxy,
        https: apiConfig.value.proxy
      },
      headers: apiConfig.value.headers
    }
    await api.put('/config/api', payload)
    ElMessage.success('API配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function saveHeaders(newHeaders) {
  saving.value = true
  try {
    await api.put('/config/api', {
      retry: apiConfig.value.retry_times,
      timeout: apiConfig.value.timeout,
      proxy_enable: apiConfig.value.proxy_enable,
      proxies: {
        http: apiConfig.value.proxy,
        https: apiConfig.value.proxy
      },
      headers: newHeaders
    })
    apiConfig.value.headers = newHeaders
    ElMessage.success('请求头已更新')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const saveDownloaderConfig = async () => {
  saving.value = true
  try {
    const payload = {
      thread_num: downloaderConfig.value.thread_num,
      max_concurrent_tasks: downloaderConfig.value.max_concurrent_tasks,
      chunk_size: downloaderConfig.value.chunk_size * 1024,  // KB -> 字节
      split_size: downloaderConfig.value.split_size * 1024 * 1024,  // MB -> 字节
      retry_times: downloaderConfig.value.retry_times
    }
    await api.put('/config/downloader', payload)
    ElMessage.success('下载器配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const saveDatabaseConfig = async () => {
  saving.value = true
  try {
    await api.put('/config/database', databaseConfig.value)
    ElMessage.success('数据库配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const testConnection = async () => {
  testing.value = true
  try {
    const response = await api.post('/config/test-connection', databaseConfig.value)
    if (response.data.success) {
      ElMessage.success('数据库连接成功')
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('连接测试失败')
  } finally {
    testing.value = false
  }
}

const resetConfig = async () => {
  try {
    await api.post('/config/reset?section=api')
    await api.post('/config/reset?section=downloader')
    await api.post('/config/reset?section=database')
    ElMessage.success('配置已重置')
    await loadConfig()
  } catch (error) {
    ElMessage.error('重置失败')
  }
}

onMounted(() => {
  loadConfig()
  // 关于页面防修改保护
  if (activeMenu.value === 'about') {
    startProtection()
    document.addEventListener('contextmenu', disableContextMenu)
    document.addEventListener('keydown', handleKeyDown)
  }
})

// 监听切换到高级功能时加载缓存统计
watch(activeMenu, (newVal) => {
  if (newVal === 'about') {
    startProtection()
    document.addEventListener('contextmenu', disableContextMenu)
    document.addEventListener('keydown', handleKeyDown)
  } else {
    stopProtection()
    document.removeEventListener('contextmenu', disableContextMenu)
    document.removeEventListener('keydown', handleKeyDown)
  }
  if (newVal === 'advanced') {
    loadCacheStats()
    loadTagCacheConfig()
  }
}, { immediate: false })

onUnmounted(() => {
  // 标签缓存走「选择即保存」，响应可能晚于卸载才回来：
  // 标记 disposed 后不再弹提示、不再回滚表单，避免对着已销毁的组件改状态
  tagCacheDisposed = true
  stopProtection()
  document.removeEventListener('contextmenu', disableContextMenu)
  document.removeEventListener('keydown', handleKeyDown)
  if (mqlSegmented.removeEventListener) {
    mqlSegmented.removeEventListener('change', updateSegmentedDirection)
  } else {
    mqlSegmented.removeListener(updateSegmentedDirection)
  }
})
</script>

<style scoped>
.config-page {
  display: flex;
  height: 100%;
  width: 100%;
}

.config-menu {
  width: 140px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  padding: 10px 0;
  background: var(--bg-secondary);
}

.menu-item {
  padding: 10px 15px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.3s;
}

.menu-item:hover {
  color: #409EFF;
  background: var(--bg-primary);
}

.menu-item.active {
  color: #409EFF;
  background: #ecf5ff;
  border-right: 3px solid #409EFF;
}

.config-content {
  flex: 1;
  padding: 15px 20px;
  overflow-y: auto;
}

.config-section {
  max-width: 400px;
}

.config-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.config-form :deep(.el-input-number) {
  width: 120px;
}

/* 关于页面样式 */
.about-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
}

.about-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.about-version {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 20px;
}

.about-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 30px;
  max-width: 400px;
}

.about-links {
  display: flex;
  gap: 20px;
  margin-bottom: 30px;
}

.github-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #409EFF;
  text-decoration: none;
  font-size: 14px;
  transition: opacity 0.3s;
}

.github-link:hover {
  opacity: 0.8;
}

.about-protection {
  margin-top: 20px;
  width: 100%;
  max-width: 300px;
}

/* 高级功能样式 */
.advanced-section {
  max-width: 500px;
}

.advanced-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.advanced-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 20px;
}

.cache-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-tip {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.refresh-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.refresh-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}

.refresh-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.refresh-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.refresh-params {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-tip {
  font-size: 12px;
  color: var(--text-muted);
}

/* 更新标签：主行（说明 + 刷新按钮）+ 定时更新选项区，纵向排列 */
.refresh-item--stacked {
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.refresh-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.tag-cache-schedule {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-color);
}

.tag-cache-toggle {
  align-items: center;
  flex-wrap: nowrap;
}

.tag-cache-enable {
  flex-shrink: 0;
  margin-left: auto;
}

.tag-cache-saving {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.tag-cache-summary {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-cache-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 2px;
}

.tag-cache-field {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tag-cache-label {
  font-size: 12px;
  color: var(--text-muted);
  width: 56px;
  flex-shrink: 0;
}

.tag-cache-time-picker {
  width: 130px;
}

.tag-cache-cron-input {
  width: 170px;
}

.tag-cache-cron-link {
  font-size: 12px;
  /* 用 element-plus 变量取色，暗色模式下自动跟随主题 */
  color: var(--el-color-primary);
  text-decoration: none;
}

.tag-cache-cron-link:hover {
  text-decoration: underline;
}

/* 收藏夹 section 保存按钮 */
.favorites-save-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

/* 暗色模式适配 */
:deep(.dark-mode) .menu-item.active {
  background: #1a1a2e;
  border-right: 3px solid #409EFF;
}

/* 移动端适配 */
@media screen and (max-width: 768px) {
  .config-page {
    flex-direction: column;
  }

  .config-menu {
    width: 100%;
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    padding: 0;
    gap: 0;
  }

  .menu-item {
    flex-shrink: 0;
    padding: 12px 16px;
    border-right: none;
    border-bottom: 3px solid transparent;
  }

  .menu-item.active {
    border-right: none;
    border-bottom: 3px solid #409EFF;
    background: var(--bg-primary);
  }

  .config-content {
    padding: 12px;
    overflow-y: auto;
  }

  .advanced-section {
    max-width: 100%;
  }

  .cache-stats {
    flex-direction: column;
    gap: 12px;
  }

  .refresh-controls {
    gap: 12px;
  }

  .refresh-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .refresh-item .el-button {
    width: 100%;
  }

  .refresh-main {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

<style scoped>
.cleanup-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cleanup-buttons .el-button {
  margin-left: 0;
}

@media screen and (max-width: 768px) {
  .cleanup-buttons {
    width: 100%;
  }
}

/* 代理模式 segmented 撑开容器，去掉 block 后仍保持三按钮单行可读 */
.proxy-mode-segmented {
  min-width: 320px;
  max-width: 100%;
}

.proxy-mode-segmented :deep(.el-segmented__item) {
  white-space: nowrap;
  padding: 0 16px;
}

/* 窄屏垂直堆叠：三段一行 -> 三行一列，释放水平空间 */
@media screen and (max-width: 539px) {
  .proxy-mode-segmented {
    min-width: 0;
    width: 100%;
  }
}
</style>

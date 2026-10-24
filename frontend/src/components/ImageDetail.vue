<template>
  <aside
    class="image-detail"
    :data-layout="layout"
    :style="rootStyle"
    :aria-label="title"
  >
    <header class="detail-head">
      <div class="detail-heading">
        <div class="detail-title">{{ title }}</div>
        <div v-if="subtitle" class="detail-subtitle">{{ subtitle }}</div>
      </div>
      <div class="detail-actions">
        <span v-if="rating" class="detail-rating" :class="ratingClass">{{ rating }}</span>
        <button class="detail-icon" type="button" aria-label="收起详情" @click="$emit('close')">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </header>

    <div class="detail-scroll">
      <template v-if="layout === 'rail'">
        <section
          v-for="section in sections"
          :key="section.label || 'section'"
          class="detail-section"
        >
          <div v-if="section.label" class="detail-section-label">{{ section.label }}</div>
          <div
            v-for="field in section.fields"
            :key="field.label"
            class="detail-row"
          >
            <span class="detail-label">{{ field.label }}</span>
            <a
              v-if="field.href"
              class="detail-value detail-link"
              :href="field.href"
              :title="field.href"
              target="_blank"
              rel="noopener noreferrer"
            >{{ field.value }} ↗</a>
            <span
              v-else
              class="detail-value"
              :class="{ 'detail-value--mono': field.mono }"
              :title="field.value"
            >{{ field.value }}</span>
          </div>
        </section>
      </template>

      <div v-else class="detail-grid">
        <div
          v-for="field in flatFields"
          :key="field.label"
          class="detail-field"
          :class="{ 'detail-field--wide': field.wide }"
        >
          <span class="detail-label">{{ field.label }}</span>
          <a
            v-if="field.href"
            class="detail-value detail-link"
            :href="field.href"
            :title="field.href"
            target="_blank"
            rel="noopener noreferrer"
          >{{ field.value }} ↗</a>
          <span
            v-else
            class="detail-value"
            :class="{ 'detail-value--mono': field.mono }"
            :title="field.value"
          >{{ field.value }}</span>
        </div>
      </div>

      <div v-if="tags.length" class="detail-tags">
        <div class="detail-section-label">标签 ({{ tags.length }})</div>
        <div class="detail-tags-list">
          <span
            v-for="tag in tags"
            :key="tag.text"
            class="detail-tag"
            :style="{ background: tag.bg, borderColor: tag.border }"
          >
            <i class="detail-tag-dot" :style="{ background: tag.dot }"></i>
            <span>{{ tag.text }}</span>
          </span>
        </div>
      </div>
    </div>

    <footer class="detail-foot">
      <div class="detail-actions-row">
        <span
          class="detail-refresh-wrap"
          :title="canRefreshTags
            ? '从 yande.re 拉取最新标签'
            : '仅本地库中包含 tagme 的图片可更新标签'"
        >
          <button
            class="detail-refresh"
            :class="{ 'detail-refresh--loading': refreshingTags }"
            type="button"
            :disabled="!canRefreshTags || refreshingTags"
            @click="$emit('refresh-tags')"
          >
            <el-icon v-if="refreshingTags" class="is-loading"><Loading /></el-icon>
            {{ refreshingTags ? '更新中…' : '更新标签' }}
          </button>
        </span>
        <a
          v-if="postUrl"
          class="detail-action"
          :href="postUrl"
          target="_blank"
          rel="noopener noreferrer"
        >原帖</a>
        <button
          v-if="postUrl"
          class="detail-action"
          type="button"
          @click="$emit('copy-link', postUrl)"
        >复制链接</button>
      </div>
    </footer>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { Close, Loading } from '@element-plus/icons-vue'

const props = defineProps({
  layout: {
    type: String,
    default: 'dock',
    validator: (value) => ['rail', 'dock'].includes(value),
  },
  title: { type: String, default: '详情' },
  subtitle: { type: String, default: '' },
  rating: { type: String, default: '' },
  sections: { type: Array, default: () => [] },
  tags: { type: Array, default: () => [] },
  height: { type: String, default: '' },
  ambientSrc: { type: String, default: '' },
  canRefreshTags: { type: Boolean, default: false },
  refreshingTags: { type: Boolean, default: false },
  postUrl: { type: String, default: '' },
})

defineEmits(['close', 'refresh-tags', 'copy-link'])

const flatFields = computed(() => props.sections.flatMap((section) => section.fields || []))

const ratingClass = computed(() => {
  const rating = String(props.rating || '').toLowerCase()
  if (rating === 'safe') return 'detail-rating--safe'
  if (rating === 'questionable') return 'detail-rating--warn'
  if (rating === 'explicit') return 'detail-rating--danger'
  return 'detail-rating--neutral'
})

const rootStyle = computed(() => {
  const style = {}
  if (props.layout === 'rail' && props.height) style.height = props.height
  if (props.ambientSrc) style['--detail-ambient'] = `url("${props.ambientSrc}")`
  return style
})

</script>

<style scoped>
.image-detail {
  /* 日间模式：浅色玻璃 + 深色文字，作为暗色 lightbox 里的日间 chrome */
  --detail-bg: rgba(255, 255, 255, 0.86);
  --detail-border: rgba(0, 0, 0, 0.10);
  --detail-text: #1f2329;
  --detail-text-soft: #454b54;
  --detail-muted: #5f6772;
  --detail-divider: rgba(0, 0, 0, 0.10);
  --detail-divider-soft: rgba(0, 0, 0, 0.06);
  --detail-chip-bg: rgba(0, 0, 0, 0.045);
  --detail-chip-border: rgba(0, 0, 0, 0.12);
  --detail-chip-hover: rgba(0, 0, 0, 0.08);
  --detail-icon-bg: rgba(0, 0, 0, 0.05);
  --detail-icon-border: rgba(0, 0, 0, 0.12);
  --detail-icon-color: #303133;
  --detail-icon-hover: rgba(0, 0, 0, 0.10);
  --detail-tint-from: rgba(255, 255, 255, 0.02);
  --detail-tint-to: rgba(255, 255, 255, 0.06);
  --detail-link-underline: rgba(0, 0, 0, 0.35);
  --detail-bg-strong: rgba(255, 255, 255, 0.96);
  --detail-ambient-opacity: 0.08;
  --detail-shadow: 0 18px 48px rgba(0, 0, 0, 0.20);
  --rating-safe-text: #2e7d32;
  --rating-warn-text: #8a5a00;
  --rating-danger-text: #b42318;
  --rating-neutral-text: #4a5058;

  position: relative;
  z-index: 12;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: 18px;
  color: var(--detail-text);
  /* 不做 backdrop-filter：图片只作为模糊环境色透上来 */
  background: var(--detail-bg);
  border: 1px solid var(--detail-border);
  box-shadow: var(--detail-shadow);
  isolation: isolate;
  transition: height 0.32s cubic-bezier(0.2, 0.8, 0.2, 1),
    background-color 0.2s ease, border-color 0.2s ease;
}

html.dark-mode .image-detail {
  --detail-bg: rgba(16, 18, 22, 0.30);
  --detail-border: rgba(255, 255, 255, 0.13);
  --detail-text: #ffffff;
  --detail-text-soft: rgba(255, 255, 255, 0.82);
  --detail-muted: rgba(255, 255, 255, 0.70);
  --detail-divider: rgba(255, 255, 255, 0.08);
  --detail-divider-soft: rgba(255, 255, 255, 0.055);
  --detail-chip-bg: rgba(255, 255, 255, 0.07);
  --detail-chip-border: rgba(255, 255, 255, 0.13);
  --detail-chip-hover: rgba(255, 255, 255, 0.14);
  --detail-icon-bg: rgba(255, 255, 255, 0.06);
  --detail-icon-border: rgba(255, 255, 255, 0.12);
  --detail-icon-color: rgba(255, 255, 255, 0.82);
  --detail-icon-hover: rgba(255, 255, 255, 0.14);
  --detail-tint-from: rgba(16, 18, 22, 0.08);
  --detail-tint-to: rgba(16, 18, 22, 0.16);
  --detail-link-underline: rgba(255, 255, 255, 0.42);
  --detail-bg-strong: rgba(0, 0, 0, 0.78);
  --detail-ambient-opacity: 0.24;
  --detail-shadow: 0 18px 48px rgba(0, 0, 0, 0.38);
  --rating-safe-text: #b7f08a;
  --rating-warn-text: #ffd28f;
  --rating-danger-text: #ffb3b3;
  --rating-neutral-text: rgba(255, 255, 255, 0.82);
}

/* 当前图片的模糊环境色。纯视觉层，不承担可读性。 */
.image-detail::before {
  content: '';
  position: absolute;
  inset: -30%;
  z-index: 0;
  background-image: var(--detail-ambient, none);
  background-position: center;
  background-size: cover;
  filter: blur(60px) saturate(1.25);
  opacity: var(--detail-ambient-opacity);
  pointer-events: none;
}

.image-detail::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(180deg, var(--detail-tint-from), var(--detail-tint-to));
  pointer-events: none;
}

.detail-head,
.detail-scroll,
.detail-foot {
  position: relative;
  z-index: 2;
}

.image-detail[data-layout='rail'] {
  flex: 0 0 340px;
  width: 340px;
}

/* 移动端坞与图片同宽；高度随内容展开，让标签完整显示。
   calc(100vh - 16px) 只是极端标签数量下的防溢出兜底。 */
.image-detail[data-layout='dock'] {
  width: 100%;
  max-width: none;
  max-height: calc(100vh - 16px);
}

.image-detail[data-layout='dock'] .detail-scroll {
  -webkit-mask-image: none;
  mask-image: none;
}

.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 8px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--detail-text);
}

.detail-subtitle {
  margin-top: 3px;
  font-size: 11px;
  color: var(--detail-muted);
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* 与瀑布流 / 大图 header 的评级一致：透明填充 + 同色描边的小矩形 */
.detail-rating {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  font-size: 11px;
  line-height: 1.4;
}

.detail-rating--safe {
  color: var(--rating-safe-text);
  border-color: var(--rating-safe-text);
}

.detail-rating--warn {
  color: var(--rating-warn-text);
  border-color: var(--rating-warn-text);
}

.detail-rating--danger {
  color: var(--rating-danger-text);
  border-color: var(--rating-danger-text);
}

.detail-rating--neutral {
  color: var(--rating-neutral-text);
  border-color: var(--rating-neutral-text);
}

.detail-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border-radius: 8px;
  border: 1px solid var(--detail-icon-border);
  background: var(--detail-icon-bg);
  color: var(--detail-icon-color);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.detail-icon:hover {
  background: var(--detail-icon-hover);
  color: var(--detail-text);
}

.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 16px 10px;
  scrollbar-width: thin;
  -webkit-mask-image: linear-gradient(to bottom, #000 calc(100% - 14px), transparent 100%);
  mask-image: linear-gradient(to bottom, #000 calc(100% - 14px), transparent 100%);
}

.detail-section {
  margin-top: 12px;
}

.detail-section:first-child {
  margin-top: 2px;
}

.detail-section-label {
  margin-bottom: 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--detail-muted);
}

.detail-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  padding: 5px 0;
  border-bottom: 1px solid var(--detail-divider-soft);
}

.detail-row:last-child {
  border-bottom: 0;
}

.detail-label {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--detail-muted);
}

.detail-value {
  min-width: 0;
  font-size: 12px;
  color: var(--detail-text);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-value--mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  color: var(--detail-text-soft);
}

.detail-link {
  color: var(--detail-text);
  text-decoration: underline;
  text-decoration-color: var(--detail-link-underline);
  text-underline-offset: 2px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.detail-link:hover {
  text-decoration-color: var(--detail-text);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 18px;
  padding-top: 4px;
}

.detail-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.detail-field--wide {
  grid-column: 1 / -1;
}

.detail-field .detail-value {
  text-align: left;
  white-space: normal;
  overflow-wrap: anywhere;
}

.detail-field .detail-value--mono {
  word-break: break-all;
}

.detail-tags {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--detail-divider);
}

.detail-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 4px;
  background: var(--detail-chip-bg);
  border: 1px solid var(--detail-chip-border);
  font-size: 11px;
  color: var(--detail-text);
}

.detail-tag-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.detail-foot {
  padding: 8px 16px 12px;
  border-top: 1px solid var(--detail-divider);
}

.detail-actions-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-refresh-wrap {
  display: flex;
  flex: 1;
  min-width: 0;
}

.detail-refresh {
  display: inline-flex;
  flex: 1;
  width: 100%;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--detail-chip-border);
  background: var(--detail-chip-bg);
  color: var(--detail-text);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.detail-refresh:hover:not(:disabled) {
  background: var(--detail-chip-hover);
}

.detail-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.detail-refresh--loading:disabled {
  opacity: 0.65;
  cursor: wait;
}

/* 底部次级操作：原帖 / 复制链接，保持小尺寸，不与主操作抢空间 */
.detail-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--detail-chip-border);
  background: var(--detail-chip-bg);
  color: var(--detail-muted);
  font-size: 12px;
  line-height: 1.4;
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.detail-action:hover {
  background: var(--detail-chip-hover);
  color: var(--detail-text);
}

@media (prefers-contrast: more) {
  .image-detail {
    background: var(--detail-bg-strong);
  }

  .image-detail::before {
    opacity: 0.08;
  }
}
</style>

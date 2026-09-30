<template>
  <el-badge
    :value="count"
    :hidden="count <= 0"
    :max="99"
    type="primary"
    class="download-indicator"
  >
    <el-button circle :aria-label="label" @click="$emit('click')">
      <!--
        下载中：把 EP 的 Download 图标拆成「箭头」+「托盘线」两层独立 SVG，
        各自跑 keyframes —— 箭头下落、触底压扁、再回弹，托盘线同步做落地涟漪。
        idle（count=0）时换回原 el-icon，按钮语义不漂移。
        stroke: currentColor → 跟随按钮颜色，hover / 暗色模式自动跟随。
      -->
      <span v-if="count > 0" class="dl-anim" aria-hidden="true">
        <svg class="dl-anim-base" viewBox="0 0 16 16" focusable="false">
          <path d="M4 13.6 H12" />
        </svg>
        <svg class="dl-anim-arrow" viewBox="0 0 16 16" focusable="false">
          <path d="M8 3.2 V10.4 M4.6 7 L8 10.4 L11.4 7" />
        </svg>
      </span>
      <el-icon v-else><Download /></el-icon>
    </el-button>
  </el-badge>
</template>

<script setup>
/**
 * DownloadIndicator —— 工具栏「下载管理」入口
 *
 * 存在的原因：点下载后没有任何全局反馈（卡片上的「下载中」只覆盖当前视野里的
 * 图片，切走就看不见），用户无法确认「到底有没有在下载、有几个在下载」。
 *
 * - `count` = 进行中任务数（口径与卡片上的「下载中」一致，见
 *   useDownloadState.activeCount：queued + pending + downloading，不含 paused）
 * - `count > 0` → 播放「箭头下落 + 触底回弹」动效 + 数字角标
 * - `count === 0` → 回到普通 Download 图标，不留残影
 *
 * 数字用 primary（蓝）而非默认 danger（红）：红色在这个位置会被读成「失败」。
 */
import { Download } from '@element-plus/icons-vue'

defineProps({
  /** 进行中任务数；> 0 时显示角标并播放动效 */
  count: { type: Number, default: 0 },
  /** 无障碍标签（tooltip 由调用方提供） */
  label: { type: String, default: '下载管理' },
})

defineEmits(['click'])
</script>

<style scoped>
.download-indicator :deep(.el-badge__content) {
  /*
   * 角标定位：中心锚在圆形按钮的边框线上（圆周 45° 点），而不是 Element Plus
   * 的默认位置。
   *
   * EP 默认 `.is-fixed` 是 `right: calc(1px + --el-badge-size/2)` +
   * `translateY(-50%) translateX(100%)`，角标中心落在 32px 方框的**右上角**、
   * 在圆外 6~7px —— 顶着 sticky 工具栏上沿，还偏向设置按钮那一侧。改为
   * left/top 百分比锚点：圆周 45° 处 = 50% ± 50%/√2 = 50% ± 35.355%，
   * 与按钮尺寸无关（换 size / 换按钮也不会跑位）。
   * 必须写 `right: auto` 覆盖 EP 的 right；--el-badge-size 一并改小，
   * 否则 EP 内部其它规则仍按默认 18px 那套变量算。
   */
  left: 85.355%;
  top: 14.645%;
  right: auto;
  transform: translate(-50%, -50%);
  --el-badge-size: 14px;

  /* 比 EP 默认（18px）小 4px：18px 角标压在 32px 圆按钮上显得笨重 */
  height: 14px;
  font-size: 10px;
  padding: 0 4px;
  /* 用按钮底色描一圈 → 角标像从按钮上「切」下来的一角，而不是浮在上面 */
  border: 1.5px solid var(--bg-tertiary, #fff);
  font-weight: 500;
}

/* 与 el-icon 同尺寸，保证 idle / 下载中两种状态按钮大小一致 */
.dl-anim {
  position: relative;
  display: inline-block;
  width: 16px;
  height: 16px;
}

.dl-anim-base,
.dl-anim-arrow {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  /* 箭头顶端会探出 16px 视框（约 -6px），不裁切 */
  overflow: visible;
}

/*
 * 1.15s 一个循环：下落（ease-in 加速）→ 触底压扁 → 回弹 → 二次小幅落地 → 回到顶部。
 * 顶点在 0% 与 100% 完全一致，所以循环是无缝的、也不会出现「消失再出现」。
 * 0%/100% 的 scale(.9) 是伪透视：远小近大，强化下落的纵深。
 */
.dl-anim-arrow {
  animation: dl-arrow-fall 1.15s linear infinite;
}

.dl-anim-base {
  animation: dl-base-ripple 1.15s linear infinite;
  transform-origin: 8px 13.6px;
}

@keyframes dl-arrow-fall {
  0% {
    transform: translateY(-6px) scale(0.9);
    animation-timing-function: cubic-bezier(0.6, 0, 0.95, 0.5);
  }
  42% {
    transform: translateY(0) scale(1);
    animation-timing-function: ease-out;
  }
  47% {
    transform: translateY(0) scaleX(1.4) scaleY(0.45);
    animation-timing-function: ease-in;
  }
  52% {
    transform: translateY(0) scale(1);
    animation-timing-function: cubic-bezier(0.25, 0.9, 0.4, 1);
  }
  66% {
    transform: translateY(-2.6px) scale(0.97);
    animation-timing-function: ease-in;
  }
  78% {
    transform: translateY(0) scale(1);
    animation-timing-function: ease-out;
  }
  82% {
    transform: translateY(0) scaleX(1.16) scaleY(0.72);
    animation-timing-function: ease-in;
  }
  86% {
    transform: translateY(0) scale(1);
  }
  100% {
    transform: translateY(-6px) scale(0.9);
  }
}

/* 托盘线：每次触底横向拉宽 + 提亮，模拟「落点震动」 */
@keyframes dl-base-ripple {
  0%, 40% {
    transform: scaleX(1);
    opacity: 0.45;
  }
  48% {
    transform: scaleX(1.45);
    opacity: 1;
  }
  56%, 76% {
    transform: scaleX(1);
    opacity: 0.45;
  }
  83% {
    transform: scaleX(1.2);
    opacity: 0.9;
  }
  90%, 100% {
    transform: scaleX(1);
    opacity: 0.45;
  }
}

/* 用户开了「减少动态效果」就只留静态图标（动效降级，不影响信息） */
@media (prefers-reduced-motion: reduce) {
  .dl-anim-arrow,
  .dl-anim-base {
    animation: none;
  }
}
</style>

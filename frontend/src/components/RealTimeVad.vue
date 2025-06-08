<template>
  <div class="vad-container">
    <h3>实时语音识别 (已停用)</h3>
    <p>此功能已迁移到 "基础录音与回放" 组件中。</p>
  </div>
</template>

<script setup lang="ts">
// All logic has been moved to AudioPlayback.vue
</script>

<style scoped>
.vad-container {
  background-color: #f8f8f8;
  border-radius: 10px;
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
  color: #888;
}

@media (prefers-color-scheme: dark) {
  .vad-container {
    background-color: #333;
    color: #999;
  }
}
</style> 
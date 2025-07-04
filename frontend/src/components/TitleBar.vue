<template>
<div data-tauri-drag-region class="titlebar" ref="titlebar">
  <!-- <div class="titlebar-button" id="titlebar-minimize">
    <img
      src="https://api.iconify.design/mdi:window-minimize.svg"
      alt="minimize"
    />
  </div>
  <div class="titlebar-button" id="titlebar-maximize">
    <img
      src="https://api.iconify.design/mdi:window-maximize.svg"
      alt="maximize"
    />
  </div>
  <div class="titlebar-button" id="titlebar-close">
    <img src="https://api.iconify.design/mdi:close.svg" alt="close" />
  </div> -->
</div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { Window } from '@tauri-apps/api/window';

const appWindow = new Window('main');
const titlebar = ref(null);
let isDragging = false;

// 监听鼠标按下事件
function handleMouseDown() {
  isDragging = true;
  if (titlebar.value) {
    titlebar.value.classList.add('dragging');
  }
}

// 监听鼠标释放事件
function handleMouseUp() {
  if (isDragging && titlebar.value) {
    isDragging = false;
    titlebar.value.classList.remove('dragging');
  }
}

// 监听鼠标离开窗口事件
function handleMouseLeave() {
  if (isDragging && titlebar.value) {
    // 不立即移除，因为用户可能只是暂时将鼠标移出窗口
    setTimeout(() => {
      if (!isDragging) {
        titlebar.value.classList.remove('dragging');
      }
    }, 100);
  }
}

onMounted(() => {
  if (titlebar.value) {
    titlebar.value.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('mouseleave', handleMouseLeave);
  }
});

onUnmounted(() => {
  if (titlebar.value) {
    titlebar.value.removeEventListener('mousedown', handleMouseDown);
    document.removeEventListener('mouseup', handleMouseUp);
    document.removeEventListener('mouseleave', handleMouseLeave);
  }
});
</script>

<style scoped>
.titlebar {
  height: 30px;
  background: transparent;
  user-select: none;
  display: flex;
  justify-content: flex-end;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  transition: background-color 0.5s ease;
}

.titlebar.dragging {
  background-color: rgba(80, 200, 205, 0.2); /* 淡淡的青绿色，透明度20% */
}

.titlebar-button {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 30px;
  height: 30px;
  user-select: none;
  -webkit-user-select: none;
}

.titlebar-button:hover {
  background: #5bbec3;
}
</style> 
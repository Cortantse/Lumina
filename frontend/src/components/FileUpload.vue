<script setup lang="ts">
import { ref, computed } from 'vue';
import { fileUploadService } from '../services/fileUploadService';

// 上传的文件
const file = ref<File | null>(null);

// 引用文件输入元素
const fileInput = ref<HTMLInputElement | null>(null);

// 计算文件大小的可读格式
const fileSize = computed(() => {
  if (!file.value) return '';
  
  const size = file.value.size;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(2)} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
});

// 处理文件选择
const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    file.value = target.files[0];
  }
};

// 重置文件选择
const resetFile = () => {
  file.value = null;
  if (fileInput.value) {
    fileInput.value.value = '';
  }
  fileUploadService.resetStatus();
};

// 上传文件
const uploadFile = async () => {
  if (!file.value) return;
  
  try {
    // 使用正确的文件上传端点
    const result = await fileUploadService.uploadFile(file.value, '/files/upload');
    console.log('上传成功:', result);
    // 如果需要，这里可以做其他成功后的操作
  } catch (error) {
    console.error('上传失败:', error);
    // 错误已经在service中处理了
  }
};

// 处理状态的样式
const processingStatusClass = computed(() => {
  const status = fileUploadService.processingStatus.value?.status;
  if (!status) return '';
  
  switch (status) {
    case 'processing': return 'processing-status';
    case 'completed': return 'success-status';
    case 'failed': return 'error-status';
    default: return '';
  }
});

// 上传状态和处理状态
const { uploadStatus, processingStatus } = fileUploadService;

// 发出关闭事件
const emit = defineEmits(['close']);

// 关闭对话框
const closeDialog = () => {
  emit('close');
};
</script>

<template>
  <div class="file-upload">
    <!-- 右上角退出按钮 -->
    <!-- <div class="close-button" @click="closeDialog">×</div> -->
    
    <!-- 文件选择区域 -->
    <div class="file-select-area" @click="fileInput?.click()">
      <input 
        type="file" 
        ref="fileInput"
        @change="handleFileChange" 
        :disabled="uploadStatus.isUploading || processingStatus?.status === 'processing'"
        style="display: none;"
      />
      <div class="select-prompt">
        <div class="file-icon">📄</div>
        <div v-if="!file" class="prompt-text">选择文件</div>
        <div v-else class="file-info">
          <div class="file-name">{{ file.name }}</div>
          <div class="file-size">{{ fileSize }}</div>
        </div>
      </div>
    </div>
    
    <!-- 上传进度条 -->
    <div v-if="uploadStatus.isUploading" class="progress-container">
      <div class="progress-bar">
        <div class="progress" :style="{ width: uploadStatus.progress + '%' }"></div>
      </div>
      <div class="progress-text">上传进度: {{ uploadStatus.progress }}%</div>
    </div>
    
    <!-- 处理进度条 -->
    <div v-if="processingStatus" class="processing-container">
      <div class="processing-status" :class="processingStatusClass">
        <div class="status-icon" :class="processingStatus.status"></div>
        <div class="status-text">
          {{ processingStatus.message }}
        </div>
      </div>
      
      <div v-if="processingStatus.status === 'processing'" class="progress-bar">
        <div class="progress progress-processing" :style="{ width: processingStatus.progress + '%' }"></div>
      </div>
    </div>
    
    <div v-if="uploadStatus.error" class="error-message">
      {{ uploadStatus.error }}
    </div>
    
    <div v-if="uploadStatus.success && !processingStatus" class="success-message">
      文件上传成功!
    </div>
    
    <!-- 操作按钮 -->
    <div class="actions">
      <button 
        @click="resetFile" 
        :disabled="!file || uploadStatus.isUploading || processingStatus?.status === 'processing'" 
        class="reset-btn"
      >
        重置
      </button>
      <button 
        @click="uploadFile" 
        :disabled="!file || uploadStatus.isUploading || processingStatus?.status === 'processing'" 
        class="upload-btn"
      >
        {{ uploadStatus.isUploading ? '上传中...' : '上传文件' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.file-upload {
  padding: 10px;
  border-radius: 8px;
  background-color: transparent;
  width: 100%;
  box-sizing: border-box;
  position: relative;
}

.close-button {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: rgba(0, 0, 0, 0.1);
  color: #333;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  z-index: 10;
}

.close-button:hover {
  background-color: rgba(0, 0, 0, 0.2);
}

.file-select-area {
  margin: 5px 0;
  padding: 10px;
  border: 2px dashed #ccc;
  border-radius: 8px;
  background-color: var(--color-background, #ffffff);
  cursor: pointer;
  text-align: center;
  transition: all 0.2s ease;
  min-height: 80px;
}

.file-select-area:hover {
  border-color: #4caf50;
  background-color: rgba(76, 175, 80, 0.05);
}

.select-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.file-icon {
  font-size: 24px;
  margin-bottom: 5px;
}

.prompt-text {
  font-size: 14px;
  color: #666;
}

.file-info {
  text-align: center;
  width: 100%;
}

.file-name {
  font-weight: bold;
  word-break: break-all;
  margin-bottom: 3px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
}

.file-size {
  font-size: 12px;
  color: #666;
}

.progress-container,
.processing-container {
  margin: 8px 0;
  width: 100%;
}

.progress-bar {
  width: 100%;
  height: 4px;
  background-color: #eee;
  border-radius: 2px;
  overflow: hidden;
}

.progress {
  height: 100%;
  background-color: #4caf50;
  transition: width 0.3s ease;
}

.progress-processing {
  background-color: #2196F3;
}

.progress-text {
  text-align: center;
  margin-top: 3px;
  font-size: 11px;
  color: #666;
}

.error-message {
  color: #f44336;
  margin: 5px 0;
  padding: 5px;
  font-size: 11px;
  background-color: rgba(244, 67, 54, 0.1);
  border-radius: 4px;
  word-break: break-word;
}

.success-message {
  color: #4caf50;
  margin: 5px 0;
  padding: 5px;
  font-size: 11px;
  background-color: rgba(76, 175, 80, 0.1);
  border-radius: 4px;
}

.processing-status {
  display: flex;
  align-items: center;
  margin-bottom: 5px;
  padding: 5px;
  border-radius: 4px;
  background-color: rgba(0, 0, 0, 0.03);
  font-size: 11px;
  word-break: break-word;
}

.processing-status.processing-status {
  background-color: rgba(33, 150, 243, 0.1);
}

.processing-status.success-status {
  background-color: rgba(76, 175, 80, 0.1);
}

.processing-status.error-status {
  background-color: rgba(244, 67, 54, 0.1);
}

.status-icon {
  min-width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  flex-shrink: 0;
}

.status-text {
  flex: 1;
}

.status-icon.uploaded {
  background-color: #ff9800;
}

.status-icon.processing {
  background-color: #2196F3;
  animation: pulse 1.5s infinite;
}

.status-icon.completed {
  background-color: #4caf50;
}

.status-icon.failed {
  background-color: #f44336;
}

.actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  width: 100%;
}

.upload-btn, .reset-btn {
  flex: 1;
  padding: 6px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background-color 0.2s;
}

.upload-btn {
  background-color: #4caf50;
  color: white;
}

.upload-btn:hover:not(:disabled) {
  background-color: #45a049;
}

.reset-btn {
  background-color: #f0f0f0;
  color: #333;
}

.reset-btn:hover:not(:disabled) {
  background-color: #e0e0e0;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@keyframes pulse {
  0% {
    opacity: 0.6;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.6;
  }
}
</style> 
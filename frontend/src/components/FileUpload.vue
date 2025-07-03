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
</script>

<template>
  <div class="file-upload">
    <h2>文件上传</h2>
    
    <!-- 文件选择区域 -->
    <div class="file-select-area">
      <input 
        type="file" 
        ref="fileInput"
        @change="handleFileChange" 
        :disabled="uploadStatus.isUploading || processingStatus?.status === 'processing'" 
      />
      
      <!-- 显示选择的文件信息 -->
      <div v-if="file" class="file-info">
        <p>文件名: {{ file.name }}</p>
        <p>类型: {{ file.type || '未知' }}</p>
        <p>大小: {{ fileSize }}</p>
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
          <strong>处理状态:</strong> {{ processingStatus.message }}
        </div>
      </div>
      
      <div v-if="processingStatus.status === 'processing'" class="progress-bar">
        <div class="progress progress-processing" :style="{ width: processingStatus.progress + '%' }"></div>
      </div>
      
      <!-- 显示处理结果或错误 -->
      <div v-if="processingStatus.status === 'completed'" class="result-container">
        <div class="result-title">处理结果:</div>
        <div v-if="processingStatus.result" class="result-data">
          <pre>{{ JSON.stringify(processingStatus.result, null, 2) }}</pre>
        </div>
      </div>
      
      <div v-if="processingStatus.status === 'failed' && processingStatus.error" class="error-container">
        <div class="error-title">处理错误:</div>
        <div class="error-message">{{ processingStatus.error }}</div>
      </div>
    </div>
    
    <!-- 上传状态和错误信息 -->
    <div v-if="uploadStatus.error" class="error-message">
      {{ uploadStatus.error }}
    </div>
    
    <div v-if="uploadStatus.success && !processingStatus" class="success-message">
      文件上传成功!
    </div>
    
    <!-- 操作按钮 -->
    <div class="actions">
      <button 
        @click="uploadFile" 
        :disabled="!file || uploadStatus.isUploading || processingStatus?.status === 'processing'" 
        class="upload-btn"
      >
        {{ uploadStatus.isUploading ? '上传中...' : '上传文件' }}
      </button>
      
      <button 
        @click="resetFile" 
        :disabled="uploadStatus.isUploading || processingStatus?.status === 'processing'"
        class="reset-btn"
      >
        重置
      </button>
    </div>
  </div>
</template>

<style scoped>
.file-upload {
  max-width: 500px;
  margin: 0 auto;
  padding: 20px;
  border-radius: 8px;
  background-color: var(--color-background-soft, #f9f9f9);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.file-select-area {
  margin: 20px 0;
  padding: 15px;
  border: 2px dashed #ccc;
  border-radius: 5px;
  background-color: var(--color-background, #ffffff);
}

.file-info {
  margin-top: 15px;
  padding: 10px;
  background-color: rgba(0, 0, 0, 0.03);
  border-radius: 5px;
}

.progress-container,
.processing-container {
  margin: 15px 0;
}

.progress-bar {
  width: 100%;
  height: 10px;
  background-color: #eee;
  border-radius: 5px;
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
  margin-top: 5px;
  font-size: 14px;
}

.error-message {
  color: #f44336;
  margin: 10px 0;
  padding: 10px;
  background-color: rgba(244, 67, 54, 0.1);
  border-radius: 5px;
}

.success-message {
  color: #4caf50;
  margin: 10px 0;
  padding: 10px;
  background-color: rgba(76, 175, 80, 0.1);
  border-radius: 5px;
}

.processing-status {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 5px;
  background-color: rgba(0, 0, 0, 0.03);
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
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin-right: 10px;
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

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.7;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

.result-container,
.error-container {
  margin-top: 15px;
  padding: 10px;
  border-radius: 5px;
  background-color: rgba(0, 0, 0, 0.03);
}

.result-title,
.error-title {
  font-weight: bold;
  margin-bottom: 5px;
}

.result-data {
  max-height: 200px;
  overflow: auto;
  font-size: 12px;
  font-family: monospace;
  background-color: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
}

pre {
  margin: 0;
  white-space: pre-wrap;
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

button {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: background-color 0.2s;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.upload-btn {
  background-color: #2196F3;
  color: white;
}

.upload-btn:hover:not(:disabled) {
  background-color: #1976D2;
}

.reset-btn {
  background-color: #f5f5f5;
  color: #333;
}

.reset-btn:hover:not(:disabled) {
  background-color: #e0e0e0;
}

@media (prefers-color-scheme: dark) {
  .file-upload {
    background-color: var(--color-background-soft, #2a2a2a);
  }
  
  .file-select-area {
    background-color: var(--color-background, #333333);
    border-color: #555;
  }
  
  .file-info {
    background-color: rgba(255, 255, 255, 0.05);
  }
  
  .progress-bar {
    background-color: #444;
  }
  
  .error-message {
    background-color: rgba(244, 67, 54, 0.2);
  }
  
  .success-message {
    background-color: rgba(76, 175, 80, 0.2);
  }
  
  .processing-status {
    background-color: rgba(255, 255, 255, 0.05);
  }
  
  .processing-status.processing-status {
    background-color: rgba(33, 150, 243, 0.2);
  }
  
  .processing-status.success-status {
    background-color: rgba(76, 175, 80, 0.2);
  }
  
  .processing-status.error-status {
    background-color: rgba(244, 67, 54, 0.2);
  }
  
  .result-container,
  .error-container {
    background-color: rgba(255, 255, 255, 0.05);
  }
  
  .result-data {
    background-color: #333;
  }
  
  .reset-btn {
    background-color: #333;
    color: #f0f0f0;
  }
  
  .reset-btn:hover:not(:disabled) {
    background-color: #444;
  }
}
</style> 
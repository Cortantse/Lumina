/**
 * 文件上传服务
 * 提供上传文件到Python后端的功能
 */

import axios, { AxiosProgressEvent } from 'axios';
import { ref } from 'vue';

// 配置基础URL，根据实际后端地址修改
const API_BASE_URL = 'http://localhost:8000/api/v1';

// 上传状态接口
interface UploadStatus {
  progress: number;
  isUploading: boolean;
  error: string | null;
  success: boolean;
}

// 文件处理状态接口
interface FileProcessingStatus {
  status: 'uploaded' | 'processing' | 'completed' | 'failed';
  progress: number;
  message: string;
  file_path?: string;
  result?: any;
  error?: string;
}

/**
 * 文件上传服务
 */
export const fileUploadService = {
  // 上传状态
  uploadStatus: ref<UploadStatus>({
    progress: 0,
    isUploading: false,
    error: null,
    success: false
  }),

  // 文件处理状态
  processingStatus: ref<FileProcessingStatus | null>(null),

  /**
   * 重置上传状态
   */
  resetStatus() {
    this.uploadStatus.value = {
      progress: 0,
      isUploading: false,
      error: null,
      success: false
    };
    this.processingStatus.value = null;
  },

  /**
   * 上传文件到后端
   * @param file 要上传的文件
   * @param endpoint 上传端点，默认为/files/upload
   * @returns 上传结果的Promise
   */
  async uploadFile(file: File, endpoint: string = '/files/upload'): Promise<any> {
    // 重置状态
    this.resetStatus();
    this.uploadStatus.value.isUploading = true;

    // 创建FormData对象
    const formData = new FormData();
    formData.append('file', file);

    try {
      // 发送上传请求，带进度跟踪
      const response = await axios.post(`${API_BASE_URL}${endpoint}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent: AxiosProgressEvent) => {
          if (progressEvent.total) {
            // 计算上传进度百分比
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            this.uploadStatus.value.progress = progress;
          }
        },
      });

      // 上传成功
      this.uploadStatus.value.isUploading = false;
      this.uploadStatus.value.success = true;
      
      // 如果返回了处理ID，初始化处理状态
      if (response.data && response.data.process_id) {
        this.processingStatus.value = {
          status: 'uploaded',
          progress: 0,
          message: '文件已上传，等待处理...'
        };
        
        // 开始轮询处理状态
        this.pollProcessingStatus(response.data.process_id);
      }
      
      return response.data;
    } catch (error: unknown) {
      // 处理上传错误
      this.uploadStatus.value.isUploading = false;
      
      if (axios.isAxiosError(error) && error.response) {
        this.uploadStatus.value.error = `上传失败：${error.response.data.message || error.response.statusText}`;
      } else {
        this.uploadStatus.value.error = '上传失败：网络错误或服务器无响应';
      }
      
      throw error;
    }
  },
  
  /**
   * 轮询文件处理状态
   * @param processId 处理ID
   */
  async pollProcessingStatus(processId: string) {
    const pollInterval = 2000; // 轮询间隔，单位毫秒
    const maxAttempts = 30; // 最大轮询次数
    let attempts = 0;
    
    const checkStatus = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/files/process/status/${processId}`);
        this.processingStatus.value = response.data;
        
        // 如果处理完成或失败，停止轮询
        if (response.data.status === 'completed' || response.data.status === 'failed') {
          return;
        }
        
        // 继续轮询
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(checkStatus, pollInterval);
        } else {
          // 达到最大尝试次数，标记为失败
          if (this.processingStatus.value) {
            this.processingStatus.value.status = 'failed';
            this.processingStatus.value.message = '处理超时，请稍后查看结果';
          }
        }
      } catch (error) {
        console.error('获取文件处理状态失败:', error);
        
        // 出错时也继续尝试轮询，除非达到最大次数
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(checkStatus, pollInterval);
        } else if (this.processingStatus.value) {
          this.processingStatus.value.status = 'failed';
          this.processingStatus.value.message = '无法获取处理状态，请稍后再试';
        }
      }
    };
    
    // 开始轮询
    setTimeout(checkStatus, pollInterval);
  }
}; 
/**
 * 日志工具模块
 * 提供统一的日志记录功能
 */

/**
 * 输出调试日志
 * @param message 日志信息
 * @param data 可选的附加数据
 */
export function logDebug(message: string, data?: any): void {
  const timestamp = new Date().toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
  if (data) {
    console.log(`[${timestamp}] 🔍 ${message}`, data);
  } else {
    console.log(`[${timestamp}] 🔍 ${message}`);
  }
}

/**
 * 输出错误日志
 * @param message 错误信息
 * @param error 可选的错误对象
 */
export function logError(message: string, error?: any): void {
  const timestamp = new Date().toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
  if (error) {
    console.error(`[${timestamp}] ❌ ${message}`, error);
  } else {
    console.error(`[${timestamp}] ❌ ${message}`);
  }
} 
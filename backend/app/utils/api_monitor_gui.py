#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Monitor GUI module - Provides a graphical interface to view the idle/busy status and statistical information of APIs in real-time
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import logging
import os
import sys
import importlib
from importlib import reload
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

import matplotlib
matplotlib.use('Agg')  # Use Agg backend to avoid threading issues
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation
import numpy as np
from PIL import ImageGrab, Image

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables to store the GUI singleton instance
_gui_instance = None
_gui_thread = None
_gui_initialized = threading.Event()
_gui_should_stop = threading.Event()
_data_queue = queue.Queue()

# Define color constants
COLOR_GOOD = "#4CAF50"  # Green
COLOR_WARNING = "#FFC107"  # Yellow
COLOR_ERROR = "#F44336"  # Red
COLOR_NEUTRAL = "#2196F3"  # Blue
COLOR_DARK_BG = "#333333"  # Dark background
COLOR_LIGHT_TEXT = "#FFFFFF"  # Light text
COLOR_GRAPH_BG = "#424242"  # Graph background color

class APIStats:
    """Class to store API statistical information"""
    
    def __init__(self, api_key: str, platform: str, model: str):
        self.api_key = api_key  # API key
        self.platform = platform  # Platform name
        self.model = model  # Model name
        self.short_key = f"...{api_key[-6:]}"  # Shortened API key (for display)
        
        # Load history (timestamp, load value)
        self.load_history: List[Tuple[float, float]] = []
        # Current load (0.0-1.0)
        self.current_load: float = 0.0
        
        # Request statistics
        self.total_requests: int = 0
        self.success_requests: int = 0
        self.failed_requests: int = 0
        
        # 请求数量历史记录 (时间戳, 请求总数)
        self.request_history: List[Tuple[float, int]] = []
        
        # Token usage
        self.total_tokens_used: int = 0
        self.completion_tokens_used: int = 0
        
        # Response time statistics (milliseconds)
        self.avg_response_time: float = 0.0
        self.min_response_time: float = float('inf')
        self.max_response_time: float = 0.0
        
        # Last update time
        self.last_update: float = time.time()
    
    def update_load(self, load_value: float):
        """Update load value"""
        self.current_load = load_value
        # Keep the last 100 data points
        now = time.time()
        self.load_history.append((now, load_value))
        if len(self.load_history) > 100:
            self.load_history = self.load_history[-100:]
        self.last_update = now
    
    def record_request(self, success: bool, tokens: int = 0, completion_tokens: int = 0, response_time_ms: float = 0):
        """Record request result"""
        self.total_requests += 1
        if success:
            self.success_requests += 1
        else:
            self.failed_requests += 1
        
        self.total_tokens_used += tokens
        self.completion_tokens_used += completion_tokens
        
        # 记录请求数量历史
        now = time.time()
        self.request_history.append((now, self.total_requests))
        if len(self.request_history) > 100:
            self.request_history = self.request_history[-100:]
        
        # Update response time statistics
        if response_time_ms > 0:
            if self.avg_response_time == 0:
                self.avg_response_time = response_time_ms
            else:
                # Use exponential moving average
                alpha = 0.1  # Smoothing factor
                self.avg_response_time = (1 - alpha) * self.avg_response_time + alpha * response_time_ms
            
            self.min_response_time = min(self.min_response_time, response_time_ms)
            self.max_response_time = max(self.max_response_time, response_time_ms)
    
    def get_load_color(self) -> str:
        """Return color based on load value"""
        if self.current_load < 0.5:
            return COLOR_GOOD
        elif self.current_load < 0.8:
            return COLOR_WARNING
        else:
            return COLOR_ERROR
    
    def get_success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 0.0
        return self.success_requests / self.total_requests
    
    def get_formatted_load_history(self, max_points: int = 50) -> Tuple[List[float], List[float]]:
        """Get formatted load history data for plotting"""
        if not self.load_history:
            return [], []
        
        # Sample data points if there are too many
        history = self.load_history
        if len(history) > max_points:
            step = len(history) // max_points
            history = history[::step]
        
        # Calculate relative time (in seconds)
        earliest_time = history[0][0]
        times = [(t - earliest_time) for t, _ in history]
        loads = [l for _, l in history]
        
        return times, loads
        
    def get_formatted_request_history(self, max_points: int = 50) -> Tuple[List[float], List[int]]:
        """获取格式化的请求数量历史数据，用于绘图"""
        if not self.request_history:
            return [], []
        
        # 如果数据点太多，进行抽样 - 使用更高效的抽样方法
        history = self.request_history
        if len(history) > max_points:
            # 使用均匀抽样而不是步长抽样，确保关键点不丢失
            indices = np.linspace(0, len(history)-1, max_points, dtype=int)
            history = [history[i] for i in indices]
        
        # 计算相对时间（以秒为单位）
        if not history:
            return [], []
        
        earliest_time = history[0][0]
        times = [(t - earliest_time) for t, _ in history]
        counts = [c for _, c in history]
        
        return times, counts


class ApiMonitorGUI:
    """API Monitor GUI class to display the usage of APIs"""
    
    def __init__(self, use_dark_theme: bool = True):
        """
        Initialize API Monitor GUI
        :param use_dark_theme: Whether to use dark theme
        """
        # Create main window
        self.root = tk.Tk()
        self.root.title("API Monitor Panel")
        self.root.geometry("900x650")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 尝试导入配置模块
        try:
            import app.core.config as config
            self.config_module = config
        except ImportError:
            messagebox.showerror("配置导入错误", "无法导入配置模块，配置编辑功能将不可用。")
            self.config_module = None

        # Set window icon
        try:
            # Try to set icon
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            logger.warning(f"Failed to set window icon: {e}")
        
        # Set style
        self.style = ttk.Style()
        if use_dark_theme:
            # Try to use dark theme
            try:
                self.root.configure(background=COLOR_DARK_BG)
                self.style.theme_use("clam")
                self.style.configure("Treeview", 
                                    background=COLOR_DARK_BG, 
                                    foreground=COLOR_LIGHT_TEXT, 
                                    fieldbackground=COLOR_DARK_BG)
                self.style.configure("TFrame", background=COLOR_DARK_BG)
                self.style.configure("TLabel", background=COLOR_DARK_BG, foreground=COLOR_LIGHT_TEXT)
                self.style.configure("TButton", background=COLOR_NEUTRAL)
                self.style.map('Treeview', background=[('selected', COLOR_NEUTRAL)])
                
                # 配置选项卡样式
                self.style.configure("TNotebook", background=COLOR_DARK_BG)
                self.style.configure("TNotebook.Tab", background=COLOR_DARK_BG, foreground=COLOR_LIGHT_TEXT)
                self.style.map("TNotebook.Tab", background=[("selected", COLOR_NEUTRAL)], 
                             foreground=[("selected", COLOR_LIGHT_TEXT)])
            except Exception as e:
                logger.warning(f"Failed to set dark theme: {e}")
        
        # 创建选项卡控件
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建主监控页
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="API 监控")
        
        # 创建配置编辑页
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text="配置编辑")
        
        # Create title label for monitor page
        title_label = ttk.Label(self.main_frame, text="API Monitor Panel", font=("Arial", 16))
        title_label.pack(pady=10)
        
        # Create separator
        separator = ttk.Separator(self.main_frame, orient="horizontal")
        separator.pack(fill="x", pady=5)
        
        # Create frame for API list and details
        self.split_frame = ttk.Frame(self.main_frame)
        self.split_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Left frame for API list
        self.left_frame = ttk.Frame(self.split_frame)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Add API list title
        list_title = ttk.Label(self.left_frame, text="API List", font=("Arial", 12))
        list_title.pack(pady=(0, 5))
        
        # Create frame for API list
        self.list_frame = ttk.Frame(self.left_frame)
        self.list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create Treeview component to display API list
        self.tree = ttk.Treeview(self.list_frame, columns=("Platform", "Model", "Load", "Success"), show="headings")
        self.tree.heading("Platform", text="Platform")
        self.tree.heading("Model", text="Model")
        self.tree.heading("Load", text="Load Value")
        self.tree.heading("Success", text="Success Rate")
        self.tree.column("Platform", width=80)
        self.tree.column("Model", width=120)
        self.tree.column("Load", width=80)
        self.tree.column("Success", width=150)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_api_selected)
        
        # Right frame for details
        self.right_frame = ttk.Frame(self.split_frame)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # Add details title
        self.detail_title = ttk.Label(self.right_frame, text="API Details", font=("Arial", 12))
        self.detail_title.pack(pady=(0, 5))
        
        # Create details frame
        self.detail_frame = ttk.Frame(self.right_frame)
        self.detail_frame.pack(fill=tk.BOTH, expand=True)
        
        # Frame for load chart
        self.chart_frame = ttk.Frame(self.detail_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create Matplotlib chart
        self.fig = Figure(figsize=(5, 4), dpi=100)
        if use_dark_theme:
            self.fig.patch.set_facecolor(COLOR_GRAPH_BG)
        self.ax = self.fig.add_subplot(111)
        if use_dark_theme:
            self.ax.set_facecolor(COLOR_GRAPH_BG)
            self.ax.spines['bottom'].set_color(COLOR_LIGHT_TEXT)
            self.ax.spines['top'].set_color(COLOR_LIGHT_TEXT)
            self.ax.spines['left'].set_color(COLOR_LIGHT_TEXT)
            self.ax.spines['right'].set_color(COLOR_LIGHT_TEXT)
            self.ax.tick_params(axis='x', colors=COLOR_LIGHT_TEXT)
            self.ax.tick_params(axis='y', colors=COLOR_LIGHT_TEXT)
            self.ax.xaxis.label.set_color(COLOR_LIGHT_TEXT)
            self.ax.yaxis.label.set_color(COLOR_LIGHT_TEXT)
            self.ax.title.set_color(COLOR_LIGHT_TEXT)
        
        self.ax.set_title("API Request History")
        self.ax.set_xlabel("Time (seconds)")
        self.ax.set_ylabel("Request Count")
        # 初始Y轴范围设为0-10
        self.ax.set_ylim(0, 10)
        self.ax.grid(True, alpha=0.3)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Frame for statistics
        self.stats_frame = ttk.Frame(self.detail_frame)
        self.stats_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Initialize statistics labels
        self.stat_labels = {}
        stats_fields = [
            "API Key", "Platform", "Model", "Current Load", "Total Requests", 
            "Successful Requests", "Failed Requests", "Success Rate", 
            "Total Tokens", "Completion Tokens", "Average Response Time", 
            "Min Response Time", "Max Response Time", "Last Update Time"
        ]
        
        # Create statistics grid
        for i, field in enumerate(stats_fields):
            row = i // 2
            col = i % 2
            
            # Field label
            field_label = ttk.Label(self.stats_frame, text=f"{field}:", font=("Arial", 10, "bold"))
            field_label.grid(row=row, column=col*2, sticky="e", padx=5, pady=3)
            
            # Value label
            value_label = ttk.Label(self.stats_frame, text="-", font=("Arial", 10))
            value_label.grid(row=row, column=col*2+1, sticky="w", padx=5, pady=3)
            
            self.stat_labels[field] = value_label
        
        # Adjust column weights
        self.stats_frame.columnconfigure(0, weight=1)
        self.stats_frame.columnconfigure(1, weight=3)
        self.stats_frame.columnconfigure(2, weight=1)
        self.stats_frame.columnconfigure(3, weight=3)
        
        # Bottom status bar
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.status_label = ttk.Label(self.status_frame, text="Ready", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT)
        
        self.last_update_label = ttk.Label(self.status_frame, text="Last update: -", anchor=tk.E)
        self.last_update_label.pack(side=tk.RIGHT)
        
        # Setup config editor
        self.setup_config_editor()
        
        # Store API status data
        self.api_stats: Dict[str, APIStats] = {}
        self.selected_api_key: Optional[str] = None
        
        # Set update timer
        self.update_timer = None
        
        # Thread-safe stop flag
        self.should_stop = threading.Event()
        
        # Data processing queue
        self.data_queue = _data_queue
        
        # Start GUI update thread
        self.start_update_thread()
    
    def setup_config_editor(self):
        """设置配置编辑界面"""
        if self.config_module is None:
            # 如果配置模块无法导入，显示错误提示
            error_label = ttk.Label(self.config_frame, text="无法加载配置模块，请检查配置文件路径。", 
                                    font=("Arial", 12), foreground=COLOR_ERROR)
            error_label.pack(pady=20)
            return
            
        # 创建配置页面标题
        title_label = ttk.Label(self.config_frame, text="配置参数编辑", font=("Arial", 16))
        title_label.pack(pady=10)
        
        # 创建提示文本
        desc_label = ttk.Label(self.config_frame, text="修改下列参数并点击保存按钮来更新配置文件。", font=("Arial", 10))
        desc_label.pack(pady=5)
        
        # 创建参数编辑框架
        params_frame = ttk.Frame(self.config_frame)
        params_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 定义可编辑参数及其元数据
        self.editable_params = {
            "cool_down_time": {
                "label": "冷却时间 (秒)",
                "type": "int",
                "min": 1,
                "max": 300,
                "default": getattr(self.config_module, "cool_down_time", 32),
                "description": "API请求失败后的等待时间"
            },
            "HIGH_SIMILARITY_THRESHOLD": {
                "label": "高相似度阈值",
                "type": "float",
                "min": 0.5,
                "max": 1.0,
                "default": getattr(self.config_module, "HIGH_SIMILARITY_THRESHOLD", 0.92),
                "description": "判定为高相似度的阈值"
            },
            "LOW_SIMILARITY_THRESHOLD": {
                "label": "低相似度阈值",
                "type": "float",
                "min": 0.1,
                "max": 0.7,
                "default": getattr(self.config_module, "LOW_SIMILARITY_THRESHOLD", 0.5),
                "description": "判定为低相似度的阈值"
            },
            "MAX_MATCH_NLI_COUNT": {
                "label": "最大NLI匹配次数",
                "type": "int",
                "min": 10,
                "max": 500,
                "default": getattr(self.config_module, "MAX_MATCH_NLI_COUNT", 100),
                "description": "每个观点最多尝试的NLI匹配次数"
            },
            "MAX_CLUSTER_NLI_COMPARE": {
                "label": "簇NLI匹配次数",
                "type": "int",
                "min": 1,
                "max": 20,
                "default": getattr(self.config_module, "MAX_CLUSTER_NLI_COMPARE", 3),
                "description": "每个簇最多进行NLI匹配的次数"
            },
            "FEATURE_VECTOR_TOP_K_RATIO": {
                "label": "特征向量匹配比例",
                "type": "float",
                "min": 0.1,
                "max": 1.0,
                "default": getattr(self.config_module, "FEATURE_VECTOR_TOP_K_RATIO", 0.3),
                "description": "特征向量匹配时选取的前k比例"
            },
            "MERGE_RELATION_SCORE_THRESHOLD": {
                "label": "合并关系评分阈值",
                "type": "float",
                "min": 0.05,
                "max": 0.5,
                "default": getattr(self.config_module, "MERGE_RELATION_SCORE_THRESHOLD", 0.2),
                "description": "触发簇合并的关系评分阈值"
            },
            "MERGE_MIN_ACCUMULATION": {
                "label": "最小关联积累次数",
                "type": "int",
                "min": 1,
                "max": 20,
                "default": getattr(self.config_module, "MERGE_MIN_ACCUMULATION", 5),
                "description": "达到此值才会触发合并"
            }
        }
        
        # 创建并保存输入控件
        self.config_entries = {}
        
        # 设置网格布局
        for i, (param_name, param_info) in enumerate(self.editable_params.items()):
            # 参数标签
            label = ttk.Label(params_frame, text=param_info["label"] + ":", font=("Arial", 10))
            label.grid(row=i, column=0, sticky="e", padx=5, pady=8)
            
            # 获取当前值
            current_value = getattr(self.config_module, param_name, param_info["default"])
            
            # 创建输入框或滑动条
            if param_info["type"] == "float":
                # 使用Frame包装输入控件和滑动条
                entry_frame = ttk.Frame(params_frame)
                entry_frame.grid(row=i, column=1, sticky="w", padx=5, pady=8)
                
                # 输入框
                var = tk.StringVar(value=str(current_value))
                entry = ttk.Entry(entry_frame, width=8, textvariable=var)
                entry.pack(side=tk.LEFT, padx=(0, 5))
                
                # 滑动条
                scale = ttk.Scale(
                    entry_frame, 
                    from_=param_info["min"], 
                    to=param_info["max"], 
                    length=200,
                    value=current_value
                )
                scale.pack(side=tk.LEFT)
                
                # 设置滑动条与输入框的同步更新
                def update_entry(val, var=var):
                    try:
                        var.set(f"{float(val):.2f}")
                    except Exception as e:
                        logger.error(f"Error in float update_entry: {e}")
                
                def update_scale(name, index, mode, var=var, scale=scale, param_min=param_info["min"], param_max=param_info["max"]):
                    try:
                        val = float(var.get())
                        if val < param_min:
                            val = param_min
                            var.set(f"{val:.2f}")
                        elif val > param_max:
                            val = param_max
                            var.set(f"{val:.2f}")
                        scale.set(val)
                    except ValueError:
                        # 保持滑动条的当前值，而不是重置
                        current_val = scale.get()
                        var.set(f"{current_val:.2f}")
                    except Exception as e:
                        logger.error(f"Error in float update_scale: {e}")
                
                scale.configure(command=update_entry)
                var.trace_add("write", update_scale)
                
                self.config_entries[param_name] = {"var": var, "scale": scale}
            else:  # 整数类型
                # 使用Frame包装输入控件和滑动条
                entry_frame = ttk.Frame(params_frame)
                entry_frame.grid(row=i, column=1, sticky="w", padx=5, pady=8)
                
                # 输入框
                var = tk.StringVar(value=str(current_value))
                entry = ttk.Entry(entry_frame, width=8, textvariable=var)
                entry.pack(side=tk.LEFT, padx=(0, 5))
                
                # 滑动条
                scale = ttk.Scale(
                    entry_frame, 
                    from_=param_info["min"], 
                    to=param_info["max"], 
                    length=200,
                    value=current_value
                )
                scale.pack(side=tk.LEFT)
                
                # 设置滑动条与输入框的同步更新
                def update_entry(val, var=var):
                    try:
                        var.set(str(int(float(val))))
                    except Exception as e:
                        logger.error(f"Error in int update_entry: {e}")
                
                def update_scale(name, index, mode, var=var, scale=scale, param_min=param_info["min"], param_max=param_info["max"]):
                    try:
                        val = int(var.get())
                        if val < param_min:
                            val = param_min
                            var.set(str(val))
                        elif val > param_max:
                            val = param_max
                            var.set(str(val))
                        scale.set(val)
                    except ValueError:
                        # 保持滑动条的当前值，而不是重置
                        current_val = int(scale.get())
                        var.set(str(current_val))
                    except Exception as e:
                        logger.error(f"Error in int update_scale: {e}")
                
                scale.configure(command=update_entry)
                var.trace_add("write", update_scale)
                
                self.config_entries[param_name] = {"var": var, "scale": scale}
            
            # 描述标签
            desc = ttk.Label(params_frame, text=param_info["description"], font=("Arial", 9), foreground="#888888")
            desc.grid(row=i, column=2, sticky="w", padx=10, pady=8)
        
        # 添加按钮框架
        button_frame = ttk.Frame(self.config_frame)
        button_frame.pack(fill=tk.X, pady=15)
        
        # 重置按钮
        reset_btn = ttk.Button(button_frame, text="重置为默认值", command=self.reset_config)
        reset_btn.pack(side=tk.LEFT, padx=20)
        
        # 保存按钮
        save_btn = ttk.Button(button_frame, text="保存配置", command=self.save_config)
        save_btn.pack(side=tk.RIGHT, padx=20)
        
        # 状态标签
        self.config_status_label = ttk.Label(self.config_frame, text="", font=("Arial", 10))
        self.config_status_label.pack(pady=10)
    
    def reset_config(self):
        """重置配置为默认值"""
        for param_name, param_info in self.editable_params.items():
            default_value = param_info["default"]
            if param_name in self.config_entries:
                entry_info = self.config_entries[param_name]
                entry_info["var"].set(str(default_value) if param_info["type"] == "int" else f"{default_value:.2f}")
                entry_info["scale"].set(default_value)
        
        self.config_status_label.config(text="参数已重置为默认值", foreground=COLOR_WARNING)
    
    def save_config(self):
        """保存配置到文件"""
        if self.config_module is None:
            messagebox.showerror("错误", "配置模块不可用，无法保存配置。")
            return
            
        try:
            # 获取配置文件路径
            module_path = self.config_module.__file__
            if not module_path:
                raise ValueError("无法确定配置文件路径")
                
            # 读取配置文件内容
            with open(module_path, 'r', encoding='utf-8') as file:
                content = file.read()
                
            # 更新每个参数的值
            for param_name, entry_info in self.config_entries.items():
                param_type = self.editable_params[param_name]["type"]
                try:
                    if param_type == "int":
                        new_value = int(entry_info["var"].get())
                    else:  # float
                        new_value = float(entry_info["var"].get())
                        
                    # 构建替换模式 - 寻找类似于: param_name = 值 的模式
                    import re
                    pattern = rf"{param_name}\s*=\s*[0-9.]+\s*(?:#.*)?$"
                    replacement = f"{param_name}={new_value}  # 修改于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    
                    # 执行替换
                    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
                    
                    # 更新内存中的模块属性
                    setattr(self.config_module, param_name, new_value)
                    
                except (ValueError, TypeError) as e:
                    messagebox.showerror("参数错误", f"参数 '{param_name}' 值无效: {str(e)}")
                    return
            
            # 写入文件
            with open(module_path, 'w', encoding='utf-8') as file:
                file.write(content)
                
            # 查找sys.modules中所有已导入的模块
            import sys
            config_module_id = id(self.config_module)
            config_module_name = self.config_module.__name__
            updated_modules = []
            
            # 检查所有模块，查找其中引用了配置模块的
            for module_name, module_obj in list(sys.modules.items()):
                if module_obj is None:
                    continue
                
                # 检查模块的所有属性是否引用了配置模块
                for attr_name in dir(module_obj):
                    try:
                        attr_value = getattr(module_obj, attr_name)
                        # 如果属性是配置模块的引用（检查ID或名称）
                        if (id(attr_value) == config_module_id or 
                            (hasattr(attr_value, '__name__') and attr_value.__name__ == config_module_name)):
                            # 记录找到引用的模块
                            if module_name != config_module_name:  # 避免记录配置模块自身
                                updated_modules.append(module_name)
                            break
                    except:
                        continue
            
            # 对于sys.modules中的每个模块，重新加载配置模块
            # 这确保了所有通过import方式导入的模块都能看到更新后的值
            reload(self.config_module)
            
            # 打印信息
            if updated_modules:
                logger.info(f"找到 {len(updated_modules)} 个引用配置模块的模块")
                logger.info(f"配置更新将影响: {', '.join(updated_modules[:10])}" + 
                           (f" 和其他 {len(updated_modules)-10} 个模块" if len(updated_modules) > 10 else ""))
            
            # 更新状态
            self.config_status_label.config(
                text=f"配置已保存并生效！({datetime.now().strftime('%H:%M:%S')})",
                foreground=COLOR_GOOD
            )
            
            # 日志记录
            logger.info(f"配置已更新并保存到 {module_path}")
            
        except Exception as e:
            error_msg = f"保存配置时出错: {str(e)}"
            messagebox.showerror("保存错误", error_msg)
            logger.error(error_msg, exc_info=True)
            self.config_status_label.config(text=f"保存失败: {str(e)}", foreground=COLOR_ERROR)
    
    def start_update_thread(self):
        """Start GUI update thread"""
        def update_loop():
            """Update loop to check for data updates in the queue every few seconds"""
            update_count = 0
            while not self.should_stop.is_set():
                try:
                    # Process all messages in the queue
                    while not self.data_queue.empty():
                        try:
                            msg_type, data = self.data_queue.get_nowait()
                            self.process_queue_message(msg_type, data)
                            self.data_queue.task_done()
                        except queue.Empty:
                            break
                    
                    # 降低GUI更新频率，每3次循环才更新一次GUI
                    if update_count % 3 == 0:
                        # Update GUI
                        self.update_gui(update_count % 6 == 0)  # 每6次循环才更新图表
                        
                        # Update status time display
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.last_update_label.config(text=f"Last update: {now}")
                    
                    update_count += 1
                    # 防止计数器过大
                    if update_count > 1000:
                        update_count = 0
                        
                except Exception as e:
                    logger.error(f"GUI update thread error: {e}", exc_info=True)
                
                # 增加更新间隔至3秒，减少CPU使用
                time.sleep(3)
        
        # Start update thread
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
    
    def process_queue_message(self, msg_type: str, data: Dict[str, Any]):
        """Process messages in the queue"""
        try:
            if msg_type == "load_update":
                # Update API load
                api_key = data.get("api_key")
                if api_key:
                    load_value = data.get("load", 0.0)
                    self.update_api_load(api_key, load_value)
            
            elif msg_type == "api_info":
                # Add new API information
                api_key = data.get("api_key")
                platform = data.get("platform", "Unknown")
                model = data.get("model", "Unknown")
                
                if api_key and api_key not in self.api_stats:
                    self.add_api(api_key, platform, model)
            
            elif msg_type == "request_result":
                # Update request result
                api_key = data.get("api_key")
                if api_key and isinstance(api_key, str) and api_key in self.api_stats:
                    success = data.get("success", False)
                    tokens = data.get("tokens", 0)
                    completion_tokens = data.get("completion_tokens", 0)
                    response_time = data.get("response_time", 0)
                    
                    self.api_stats[api_key].record_request(
                        success, tokens, completion_tokens, response_time
                    )
            elif msg_type == "model_update":
                # 更新API模型信息
                api_key = data.get("api_key")
                new_model = data.get("model")
                if api_key and new_model and api_key in self.api_stats:
                    # 1. 更新内部API统计对象中的模型名称
                    self.api_stats[api_key].model = new_model
                    
                    # 2. 更新Treeview中的模型显示
                    #    我们假设Treeview的item的tags属性存储了api_key
                    for item_id in self.tree.get_children():
                        item_data = self.tree.item(item_id)
                        tags = item_data.get("tags", []) # 获取tags，默认为空列表
                        
                        # 从tags中提取api_key (处理tags为字符串或列表/元组的情况)
                        key_from_tag = None
                        if isinstance(tags, str):
                            key_from_tag = tags
                        elif isinstance(tags, (list, tuple)) and tags: # 检查是否非空
                            key_from_tag = tags[0] # 假设api_key是第一个tag

                        if key_from_tag == api_key:
                            current_values = list(self.tree.item(item_id, "values"))
                            # Treeview列: "Platform", "Model", "Load", "Success"
                            if len(current_values) > 1: # 确保值列表足够长
                                current_values[1] = new_model # 更新Model列 (索引1)
                                self.tree.item(item_id, values=tuple(current_values))
                            break # 找到并更新后退出循环
                    
                    # 3. 如果当前选中的API是这个被更新的API，则刷新详情面板
                    if self.selected_api_key == api_key:
                        self.update_api_details(api_key)
            elif msg_type == "status":
                # Update status bar message
                status_text = data.get("text", "")
                if status_text:
                    self.status_label.config(text=status_text)
                    
            elif msg_type == "reload_config":
                # 重新加载配置文件
                if self.config_module:
                    try:
                        reload(self.config_module)
                        self.update_config_display()
                        self.status_label.config(text="配置已重新加载")
                    except Exception as e:
                        logger.error(f"Failed to reload config: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing queue message ({msg_type}): {e}", exc_info=True)
    
    def update_config_display(self):
        """更新配置参数显示"""
        if not hasattr(self, 'config_entries') or not self.config_module:
            return
            
        for param_name, entry_info in self.config_entries.items():
            try:
                current_value = getattr(self.config_module, param_name, 
                                      self.editable_params[param_name]["default"])
                param_type = self.editable_params[param_name]["type"]
                
                if param_type == "int":
                    entry_info["var"].set(str(current_value))
                else:  # float
                    entry_info["var"].set(f"{current_value:.2f}")
                    
                entry_info["scale"].set(current_value)
            except Exception as e:
                logger.warning(f"Failed to update config display for {param_name}: {e}")
    
    def add_api(self, api_key: str, platform: str, model: str):
        """Add new API to the list"""
        if not isinstance(api_key, str):
            logger.warning(f"Attempting to add non-string type API key: {type(api_key)}")
            return
            
        if api_key not in self.api_stats:
            # 统一平台名称显示格式
            if platform.lower() == "openai":
                platform = "OpenAI"
            elif platform.lower() == "deepinfra":
                platform = "DeepInfra"
            elif platform.lower() == "deepseek":
                platform = "DeepSeek"
            elif platform.lower() == "ali":
                platform = "Ali"
            elif platform.lower() == "jamba":
                platform = "Jamba"
            elif platform.lower() == "mistral":
                platform = "Mistral"
            elif platform.lower() == "command":
                platform = "Command"
            elif platform.lower() == "google":
                platform = "Google"
                
            stats = APIStats(api_key, platform, model)
            self.api_stats[api_key] = stats
            
            # Add to Treeview
            short_key = stats.short_key
            tree_id = self.tree.insert("", "end", text=short_key, values=(platform, model, "0%", "0%"))
            # Ensure using string type tag instead of tuple to avoid type errors
            self.tree.item(tree_id, tags=api_key)
    
    def update_api_load(self, api_key: str, load_value: float):
        """Update API load value"""
        if api_key and isinstance(api_key, str) and api_key in self.api_stats:
            self.api_stats[api_key].update_load(load_value)
    
    def update_gui(self, update_chart=False):
        """Update GUI elements
        Args:
            update_chart: 是否更新图表，减少图表更新频率可降低CPU使用
        """
        try:
            # 限制每次处理的项目数，避免大量项目时的性能问题
            max_items_per_update = 20
            items_processed = 0
            
            # Update API list
            for item_id in self.tree.get_children():
                # 限制每次更新的项目数
                if items_processed >= max_items_per_update:
                    break
                    
                # Get the tag associated with this item
                item_data = self.tree.item(item_id)
                tags = item_data.get("tags", None)
                
                # If no tag, skip this item
                if not tags or not isinstance(tags, (str, list, tuple)):
                    continue
                
                # Handle the case where tag is a string or a list/tuple
                api_key = tags if isinstance(tags, str) else tags[0] if tags else None
                
                # If unable to extract api_key, skip
                if not api_key:
                    continue
                    
                stats = self.api_stats.get(api_key)
                if stats:
                    # 显示为绝对值而非百分比
                    load_value = f"{stats.current_load:.3f}"
                    success_rate = f"{stats.get_success_rate() * 100:.1f}% ({stats.success_requests}/{stats.total_requests})"
                    self.tree.item(item_id, values=(stats.platform, stats.model, load_value, success_rate))
                
                items_processed += 1
            
            # If an API is selected, update details (但不一定更新图表)
            if self.selected_api_key and isinstance(self.selected_api_key, str) and self.selected_api_key in self.api_stats:
                self.update_api_details(self.selected_api_key, update_chart)
                
        except Exception as e:
            logger.error(f"Error updating GUI: {e}", exc_info=True)
    
    def update_api_details(self, api_key: str, update_chart=True):
        """Update API details panel"""
        if not api_key or not isinstance(api_key, str):
            return
            
        stats = self.api_stats.get(api_key)
        if not stats:
            return
        
        # 更新统计标签
        # 确保这里会使用更新后的 stats.model
        for field, value_source_is_stats_attr, formatter in [
            ("API Key", lambda s: s.short_key, None),
            ("Platform", lambda s: s.platform, None),
            ("Model", lambda s: s.model, None), # 使用更新后的模型
            ("Current Load", lambda s: f"{s.current_load:.3f}", None),
            ("Total Requests", lambda s: str(s.total_requests), None),
            ("Successful Requests", lambda s: str(s.success_requests), None),
            ("Failed Requests", lambda s: str(s.failed_requests), None),
            ("Success Rate", lambda s: f"{s.get_success_rate() * 100:.1f}%", None),
            ("Total Tokens", lambda s: f"{s.total_tokens_used:,}", None),
            ("Completion Tokens", lambda s: f"{s.completion_tokens_used:,}", None)
        ]:
            if field in self.stat_labels:
                self.stat_labels[field].config(text=value_source_is_stats_attr(stats))
        
        # Response time statistics - handled separately due to conditional checks
        if "Average Response Time" in self.stat_labels:
            if stats.avg_response_time > 0:
                self.stat_labels["Average Response Time"].config(text=f"{stats.avg_response_time:.1f} ms")
            else:
                self.stat_labels["Average Response Time"].config(text="-")
        
        if "Min Response Time" in self.stat_labels:
            if stats.min_response_time < float('inf'):
                self.stat_labels["Min Response Time"].config(text=f"{stats.min_response_time:.1f} ms")
            else:
                self.stat_labels["Min Response Time"].config(text="-")
        
        if "Max Response Time" in self.stat_labels:
            self.stat_labels["Max Response Time"].config(
                text=f"{stats.max_response_time:.1f} ms" if stats.max_response_time > 0 else "-"
            )
        
        # Last update time
        if "Last Update Time" in self.stat_labels:
            last_update_time = datetime.fromtimestamp(stats.last_update).strftime("%H:%M:%S")
            self.stat_labels["Last Update Time"].config(text=last_update_time)
        
        # Update chart (可选，降低更新频率)
        if update_chart:
            self.update_chart(api_key)
    
    def update_chart(self, api_key: str):
        """Update load history chart"""
        if not api_key or not isinstance(api_key, str):
            return
            
        stats = self.api_stats.get(api_key)
        if not stats:
            return
        
        # 减少图表绘制的计算量
        try:
            # Clear old chart
            self.ax.clear()
            
            # Get request history data
            times, counts = stats.get_formatted_request_history(max_points=30)  # 减少数据点
            
            if times and counts:
                # Plot new data - 简化绘图操作
                self.ax.plot(times, counts, marker='o', markersize=3, linestyle='-', color=COLOR_NEUTRAL)
                
                # 移除填充区域以减少绘图复杂度
                # self.ax.fill_between(times, counts, alpha=0.3, color=COLOR_NEUTRAL)
                
                # Set dynamic Y axis scale based on data
                if counts:
                    max_count = max(counts)
                    # 设置一个合理的上限，确保图表可读性
                    y_max = max(1, max_count * 1.2)  # 至少为1，或者最大值的1.2倍
                    self.ax.set_ylim(0, y_max)
                else:
                    self.ax.set_ylim(0, 10)
                    
                self.ax.grid(True, alpha=0.3)
                
                # Set title and labels
                self.ax.set_title(f"API Request History ({stats.short_key})")
                self.ax.set_xlabel("Time (seconds)")
                self.ax.set_ylabel("Request Count")
            else:
                # Show placeholder when no data
                self.ax.text(0.5, 0.5, "No historical data", ha='center', va='center', transform=self.ax.transAxes)
                self.ax.set_title(f"API Request History ({stats.short_key})")
                self.ax.set_xlabel("Time (seconds)")
                self.ax.set_ylabel("Request Count")
                self.ax.set_ylim(0, 10)
                
            # 关闭自动调整以提高性能
            self.fig.tight_layout(pad=2.0)
            # 减少重复绘制
            self.canvas.draw_idle()
        except Exception as e:
            logger.error(f"Error updating chart: {e}", exc_info=True)
    
    def on_api_selected(self, event):
        """Handle API selection event"""
        selection = self.tree.selection()
        if selection:
            item_id = selection[0]
            
            # Get the tag associated with this item
            item_data = self.tree.item(item_id)
            tags = item_data.get("tags", None)
            
            # If no tag, return directly
            if not tags or not isinstance(tags, (str, list, tuple)):
                return
            
            # Handle the case where tag is a string or a list/tuple
            api_key = tags if isinstance(tags, str) else tags[0] if tags else None
            
            # If unable to extract api_key, return
            if not api_key:
                return
                
            self.selected_api_key = api_key
            self.update_api_details(api_key)
    
    def on_closing(self):
        """Handle window closing event"""
        try:
            # 保存GUI截图
            self.save_screenshot()
            
            # Set stop flag
            self.should_stop.set()
            global _gui_should_stop
            _gui_should_stop.set()
            
            # Wait for update thread to exit
            if hasattr(self, 'update_thread') and self.update_thread.is_alive():
                self.update_thread.join(timeout=1.0)
            
            # Close window
            self.root.destroy()
        except Exception as e:
            logger.error(f"Error during GUI closing: {e}", exc_info=True)
            self.root.destroy()  # 确保窗口关闭，即使出错
    
    def save_screenshot(self):
        """保存GUI窗口截图"""
        try:
            # 确保截图保存目录存在
            screenshot_dir = os.path.join(os.getcwd(), "logs", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # 创建带时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(screenshot_dir, f"api_monitor_{timestamp}.png")
            
            # 获取窗口位置和大小
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            
            try:
                # 优化截图性能
                screenshot = ImageGrab.grab(
                    bbox=(x, y, x + width, y + height),
                    include_layered_windows=False,  # 不包含分层窗口以提高性能
                    all_screens=False  # 只截取主屏幕
                )
                
                # 降低图像大小以减少内存占用和保存时间
                max_size = 1200
                if width > max_size or height > max_size:
                    # 计算缩放比例
                    ratio = min(max_size / width, max_size / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    # 使用整数3代替Image.BICUBIC常量
                    screenshot = screenshot.resize((new_width, new_height), resample=3)
                
                # 使用优化的保存设置
                screenshot.save(filename, optimize=True, quality=85)
            except Exception as inner_e:
                logger.warning(f"Screenshot optimization failed, using fallback method: {inner_e}")
                # 回退到普通方法
                screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
                screenshot.save(filename)
            
            logger.info(f"Screenshot saved to {filename}")
            
            # 更新状态栏
            self.status_label.config(text=f"Screenshot saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}", exc_info=True)
    
    def run(self):
        """Start GUI main loop"""
        try:
            self.root.mainloop()
        except Exception as e:
            logger.error(f"GUI main loop error: {e}", exc_info=True)
        finally:
            self.should_stop.set()
            global _gui_should_stop
            _gui_should_stop.set()


def _gui_thread_func():
    """GUI thread function"""
    global _gui_instance
    try:
        # Create and start GUI
        _gui_instance = ApiMonitorGUI(use_dark_theme=True)
        
        # Notify main thread that GUI is initialized
        _gui_initialized.set()
        
        # Run GUI main loop
        _gui_instance.run()
    except Exception as e:
        logger.error(f"GUI thread error: {e}", exc_info=True)
        # Set initialized flag even if there's an error to avoid main thread waiting indefinitely
        _gui_initialized.set()
    finally:
        # Clean up global variables
        _gui_instance = None


def start_monitor(wait_initialized=False):
    """
    Start API monitor GUI
    :param wait_initialized: Whether to wait for GUI initialization to complete
    :return: Whether the start was successful
    """
    # --- MODIFICATION TO DISABLE GUI ---
    # To turn off the API Monitor GUI, we simply return here and do not start the thread.
    # All other functions in this module that try to send data to the GUI
    # will check if the GUI thread is running and will become no-ops.
    # logger.info("API Monitor GUI functionality is disabled via start_monitor modification.")
    return True # Indicates that the operation is handled (by disabling the GUI).
    # --- END MODIFICATION ---

    # Original code effectively becomes unreachable:
    global _gui_thread, _gui_initialized, _gui_should_stop
    
    # If a GUI is already running, return success immediately
    if _gui_thread is not None and _gui_thread.is_alive():
        return True

    
    # Reset events
    _gui_initialized.clear()
    _gui_should_stop.clear()
    
    try:
        # Create and start GUI thread
        _gui_thread = threading.Thread(target=_gui_thread_func, daemon=True)
        _gui_thread.start()
        
        if wait_initialized:
            # Wait for GUI initialization to complete, up to 5 seconds
            initialized = _gui_initialized.wait(timeout=5.0)
            return initialized
        return True
    except Exception as e:
        logger.error(f"Failed to start API Monitor GUI: {e}")
        return False


def stop_monitor():
    """Stop API monitor GUI"""
    global _gui_should_stop, _gui_thread, _gui_instance
    
    if _gui_thread is not None and _gui_thread.is_alive():
        # Set stop flag
        _gui_should_stop.set()
        
        # If GUI instance exists, send close signal through the queue
        if _gui_instance is not None:
            try:
                _data_queue.put(("status", {"text": "Closing..."}))
            except:
                pass
        
        # Wait for thread to exit
        _gui_thread.join(timeout=2.0)
        return not _gui_thread.is_alive()
    return True


def update_api_load(api_key, load_value):
    """
    Update API load value
    :param api_key: API key
    :param load_value: Load value (0.0-1.0)
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            # 确保api_key是字符串类型
            if api_key is None or not isinstance(api_key, str):
                logger.warning(f"Invalid API key type in update_api_load: {type(api_key)}")
                return False
                
            _data_queue.put(("load_update", {
                "api_key": api_key,
                "load": load_value
            }))
            return True
        except:
            return False
    return False


def register_api(api_key, platform, model):
    """
    Register API information
    :param api_key: API key
    :param platform: Platform name
    :param model: Model name
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            # 确保api_key是字符串类型
            if api_key is None or not isinstance(api_key, str):
                logger.warning(f"Invalid API key type in register_api: {type(api_key)}")
                return False
                
            _data_queue.put(("api_info", {
                "api_key": api_key,
                "platform": platform,
                "model": model
            }))
            return True
        except:
            return False
    return False


def record_request(api_key, success, tokens=0, completion_tokens=0, response_time_ms=0.0, current_model=None):
    """
    Record request result
    :param api_key: API key
    :param success: Whether the request was successful
    :param tokens: Total tokens used
    :param completion_tokens: Completion tokens used
    :param response_time_ms: Response time (milliseconds)
    :param current_model: The actual model used for this request (optional)
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            # 确保api_key是字符串类型
            if api_key is None or not isinstance(api_key, str):
                logger.warning(f"Invalid API key type in record_request: {type(api_key)}")
                return False
                
            _data_queue.put(("request_result", {
                "api_key": api_key,
                "success": success,
                "tokens": tokens,
                "completion_tokens": completion_tokens,
                "response_time": response_time_ms
            }))

            # If current_model is provided, queue a model_update message
            if current_model:
                _data_queue.put(("model_update", {
                    "api_key": api_key,
                    "model": current_model
                }))
            
            return True
        except Exception as e:
            logger.error(f"Error queueing message in record_request: {e}")
            return False
    return False


def update_status(text):
    """
    Update status bar message
    :param text: Status message
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            _data_queue.put(("status", {"text": text}))
            return True
        except:
            return False
    return False


def is_monitor_running():
    """
    Check if the monitor GUI is running
    :return: Whether it is running
    """
    return _gui_thread is not None and _gui_thread.is_alive()


def update_detail_text(self, stats):
    """Update detail text"""
    if not hasattr(self, 'detail_text'):
        return
            
    # Clear existing text
    self.detail_text.config(state=tk.NORMAL)
    self.detail_text.delete(1.0, tk.END)
    
    # Add basic information
    self.detail_text.insert(tk.END, "Basic Information\n", "section")
    self.detail_text.insert(tk.END, f"Platform: {stats.platform}\n", "normal")
    self.detail_text.insert(tk.END, f"Model: {stats.model}\n", "normal")
    self.detail_text.insert(tk.END, f"API Key: {stats.short_key}\n", "normal")
    self.detail_text.insert(tk.END, f"Current Load: {stats.current_load:.2f}\n", "normal")
    
    # Add request statistics
    self.detail_text.insert(tk.END, "\nRequest Statistics\n", "section")
    total_requests = stats.success_requests + stats.failed_requests
    self.detail_text.insert(tk.END, f"Total Requests: {total_requests}\n", "normal")
    self.detail_text.insert(tk.END, f"Successful: {stats.success_requests} ({stats.get_success_rate():.1%})\n", "normal")
    self.detail_text.insert(tk.END, f"Failed: {stats.failed_requests}\n", "normal")
    
    # Add response time statistics
    self.detail_text.insert(tk.END, "\nResponse Time (ms)\n", "section")
    self.detail_text.insert(tk.END, f"Average: {stats.avg_response_time:.1f}\n", "normal")
    self.detail_text.insert(tk.END, f"Min: {stats.min_response_time:.1f}\n", "normal")
    self.detail_text.insert(tk.END, f"Max: {stats.max_response_time:.1f}\n", "normal")
    
    # Add last update time
    if stats.last_update:
        last_update = datetime.fromtimestamp(stats.last_update).strftime('%Y-%m-%d %H:%M:%S')
        self.detail_text.insert(tk.END, f"\nLast Updated: {last_update}\n", "normal")
    
    # Disable editing
    self.detail_text.config(state=tk.DISABLED)


def reload_config():
    """
    触发配置重新加载
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            _data_queue.put(("reload_config", {}))
            return True
        except:
            return False
    return False 

def update_api_model(api_key, new_model):
    """
    更新API的模型信息
    :param api_key: API密钥
    :param new_model: 新的模型名称
    """
    if _gui_thread is not None and _gui_thread.is_alive():
        try:
            _data_queue.put(("model_update", {
                "api_key": api_key,
                "model": new_model
            }))
            return True
        except:
            return False
    return False 
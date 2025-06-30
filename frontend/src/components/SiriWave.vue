<script setup lang="ts">
import { ref } from 'vue';
import { TresCanvas, useRenderLoop } from '@tresjs/core';
import * as THREE from 'three';

// =============== 可调超参数区 ===============
const props = withDefaults(
  defineProps<{
    mode?: 'idle' | 'listening' | 'speaking';
    /**
     * 空闲状态下形变强度，数值越大球体表面起伏越明显。
     * 推荐范围：0.05 ~ 0.3，越大越活跃。
     * 视觉效果：控制空闲时球体表面的波动幅度
     */
    idleIntensity?: number;
    /**
     * 听语音时形变强度，数值越大球体表面起伏越明显。
     * 推荐范围：0.1 ~ 0.5，越大越活跃。
     * 视觉效果：控制听语音时球体表面的波动幅度
     */
    listeningIntensity?: number;
    /**
     * 说话时形变强度，数值越大球体表面起伏越明显。
     * 推荐范围：0.3 ~ 0.7，越大越活跃。
     * 视觉效果：控制说话时球体表面的波动幅度
     */
    speakingIntensity?: number;
  }>(),
  {
    mode: 'idle',
    idleIntensity: 0.3,      // 空闲状态形变强度
    listeningIntensity: 0.5, // 听语音时形变强度
    speakingIntensity: 0.75,  // 说话时形变强度
  }
);

/**
 * HUE_RANGES 色相范围：
 * 每个状态下的色相区间，决定球体主色调。
 * 色相值说明：0.0=红色, 0.17=黄色, 0.33=绿色, 0.5=青色, 0.67=蓝色, 0.83=紫色, 1.0=红色
 * 
 * 当前设置：
 * - idle: 深邃蓝绿（0.52~0.55），偏向深沉、安静的色调
 * - listening: 青蓝（0.5~0.52），清爽、专注的色调
 * - speaking: 亮青蓝（0.48~0.5），明亮、活跃的色调
 *
 * 调整建议：
 * - 调整区间宽度：区间越宽，色彩变化越丰富；区间越窄，色彩越稳定
 * - 调整区间位置：数值越小越偏绿，数值越大越偏蓝
 * - 推荐总范围：0.4~0.7（青绿到蓝色区间）
 */
const HUE_RANGES = {   // 这里调色是大头
  idle:      new THREE.Vector2(0.545, 0.57),   // 深邃蓝绿
  listening: new THREE.Vector2(0.528, 0.55),    // 青蓝
  speaking:  new THREE.Vector2(0.512, 0.535),    // 亮青蓝
};

const shader = {
  uniforms: {
    u_time:      { value: 0    },  // 动画时间，自动传入
    u_intensity: { value: 0.0  },  // 形变强度，由props控制
    u_brightness:{ value: 1.0  },  // 全局亮度系数，范围0~1
    u_sphereScale:{ value: 1.0 },  // 球体缩放，控制呼吸效果
    u_currentHueRange: { value: new THREE.Vector2().copy(HUE_RANGES.idle) }, // 当前色相范围
    u_targetHueRange:  { value: new THREE.Vector2().copy(HUE_RANGES.idle) }, // 目标色相范围
    u_transitionProgress: { value: 1.0 }, // 过渡进度，0~1
  },
  vertexShader: `
    // ========== Vertex Shader 参数说明 ==========
    // u_intensity: 形变强度，受 props 控制，影响球体表面起伏程度
    // u_sphereScale: 球体缩放，控制整体大小和呼吸效果
    // u_time: 动画时间，驱动噪声和形变动画
    // v_noise: 输出到fragment shader的噪声值，用于颜色和光照计算
    
    uniform float u_time;
    uniform float u_intensity;
    uniform float u_sphereScale;
    varying vec3 v_normal;
    varying vec3 v_position;
    varying float v_noise;
    
    // Simplex Noise 函数（用于生成自然的表面起伏）
    vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
    vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
    vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
    float snoise(vec3 v) {
      const vec2 C = vec2(1.0/6.0, 1.0/3.0);
      const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
      vec3 i = floor(v + dot(v, C.yyy));
      vec3 x0 = v - i + dot(i, C.xxx);
      vec3 g = step(x0.yzx, x0.xyz);
      vec3 l = 1.0 - g;
      vec3 i1 = min(g.xyz, l.zxy);
      vec3 i2 = max(g.xyz, l.zxy);
      vec3 x1 = x0 - i1 + C.xxx;
      vec3 x2 = x0 - i2 + C.yyy;
      vec3 x3 = x0 - D.yyy;
      i = mod289(i);
      vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0))
        + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
      float n_ = 0.142857142857;
      vec3 ns = n_ * D.wyz - D.xzx;
      vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
      vec4 x_ = floor(j * ns.z);
      vec4 y_ = floor(j - 7.0 * x_);
      vec4 x = x_ * ns.x + ns.yyyy;
      vec4 y = y_ * ns.x + ns.yyyy;
      vec4 h = 1.0 - abs(x) - abs(y);
      vec4 b0 = vec4(x.xy, y.xy);
      vec4 b1 = vec4(x.zw, y.zw);
      vec4 s0 = floor(b0)*2.0 + 1.0;
      vec4 s1 = floor(b1)*2.0 + 1.0;
      vec4 sh = -step(h, vec4(0.0));
      vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
      vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
      vec3 p0 = vec3(a0.xy,h.x);
      vec3 p1 = vec3(a0.zw,h.y);
      vec3 p2 = vec3(a1.xy,h.z);
      vec3 p3 = vec3(a1.zw,h.w);
      vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
      p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
      vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
      m = m * m;
      return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
    }

    void main() {
      v_normal = normalize(normal);
      v_position = position;
      
      // ========== 多层噪声合成 ==========
      // 可调参数：噪声层的频率和时间速度
      // 频率越高，细节越多；时间速度越快，动画越快
      float large_noise = snoise(position * 1.0 + u_time * 0.05);   // 大尺度噪声：频率1.0，速度0.05
      float medium_noise = snoise(position * 3.0 + u_time * 0.2);   // 中尺度噪声：频率3.0，速度0.2
      float small_noise = snoise(position * 8.0 + u_time * 0.5);    // 小尺度噪声：频率8.0，速度0.5
      float micro_noise = snoise(position * 15.0 + u_time * 0.7);   // 微尺度噪声：频率15.0，速度1.0
      
      // ========== 噪声权重混合 ==========
      // 可调参数：各层噪声的权重，总和应接近1.0
      // 权重越大，该层噪声的影响越明显
      v_noise = large_noise * 0.5 + medium_noise * 0.3 + small_noise * 0.15 + micro_noise * 0.05;
      
      // ========== 顶点位移计算 ==========
      // 可调参数：位移强度系数（当前为0.5）
      // 数值越大，表面起伏越明显
      vec3 displaced = position + normal * v_noise * u_intensity * 0.5;
      vec3 scaled = displaced * u_sphereScale;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(scaled, 1.0);
    }
  `,
  fragmentShader: `
    // ========== Fragment Shader 参数说明 ==========
    // u_brightness: 全局亮度系数，受动画控制，影响整体明暗
    // u_currentHueRange: 当前色相范围，状态转换的起始色相
    // u_targetHueRange: 目标色相范围，状态转换的目标色相
    // u_transitionProgress: 状态切换时的过渡进度，0~1，经过EaseInOutQuad处理
    // v_noise: 从vertex shader传入的噪声值，用于颜色变化和光照细节
    
    varying vec3 v_normal;
    varying vec3 v_position;
    varying float v_noise;
    uniform float u_brightness;
    uniform vec2 u_currentHueRange;
    uniform vec2 u_targetHueRange;
    uniform float u_transitionProgress;
    uniform float u_time;

    // ========== 可调参数：色相动画速度 ==========
    // 数值越大，色彩在色相范围内的往复变化越快
    // 推荐范围：0.01~0.1
    // 当前值：0.03，较慢的色相变化，营造平静感
    const float HUE_SPEED = 0.01;

    // HSV转RGB函数
    vec3 hsv2rgb(vec3 c) {
      vec3 rgb = clamp(abs(mod(c.x*6.0+vec3(0.0,4.0,2.0),6.0)-3.0)-1.0, 0.0, 1.0);
      return c.z * mix(vec3(1.0), rgb, c.y);
    }

    void main() {
      // ================= EaseInOutQuad Cross-Fade 状态过渡 =================
      // 1. 区间插值（EaseInOutQuad 已在JS端计算并写入 uniform）
      vec2 hueRange = mix(u_currentHueRange, u_targetHueRange, u_transitionProgress);

      // 2. 周期动画取值：在色相范围内往复摆动
      float hueAnim = sin(u_time * HUE_SPEED) * 0.5 + 0.5;

      // 3. 最终色相：在过渡后区间里再做一次线性插值
      // 可调参数：v_noise * 0.1 控制噪声对色相的影响程度
      // 推荐范围：0.05~0.2，数值越大色彩变化越丰富
      float hue = mix(hueRange.x, hueRange.y, hueAnim + v_noise * 0.06);

      // ========== 色彩饱和度和明度设置 ==========
      // 可调参数：饱和度范围 mix(0.6, 0.75, u_brightness)
      // 第一个值：最低饱和度，推荐0.4~0.7
      // 第二个值：最高饱和度，推荐0.6~0.9
      // 当前设置：0.65~0.8，色彩鲜明但不过分艳丽
      float saturation = mix(0.65, 0.75, u_brightness);
      
      // 可调参数：明度范围 mix(0.6, 0.85, u_brightness)
      // 第一个值：最低明度，推荐0.5~0.7
      // 第二个值：最高明度，推荐0.8~1.0
      // 当前设置：0.65~0.85，保持中高明度，避免过亮
      float value = mix(0.65, 0.85, u_brightness);

      vec3 baseColor = hsv2rgb(vec3(hue, saturation, value));

      // ========== Lambert 漫反射光照 ==========
      // 可调参数：光源方向 vec3(0.0, 0.0, 1.0)
      // 当前设置：正对摄像机的光源，可以调整为其他方向
      // 例如：vec3(0.5, 0.5, 1.0) 会产生斜向光照效果
      vec3 lightDir = normalize(vec3(0.0, 0.0, 1.0));  
      float diff = max(dot(v_normal, lightDir), 0.0);  
      
      // 可调参数：亮度调制范围 mix(0.85, 1.15, diff)
      // 第一个值：背光面亮度系数，推荐0.7~0.9
      // 第二个值：受光面亮度系数，推荐1.1~1.3
      // 当前设置：0.85~1.15，适中的光照对比
      baseColor *= mix(0.75, 1.35, diff);  

      // ========== 噪声明暗层次 ==========
      // 可调参数：噪声强度 v_noise * 0.1
      // 推荐范围：0.05~0.2
      // 数值越大，表面明暗变化越明显，细节越丰富
      // 当前设置：0.1，适中的噪声细节
      // 把 0.14 ↓ 到 0.08，保留细节但弱化“颗粒”感
      baseColor += baseColor * v_noise * 0.08;


      // ========== 方案B：基于距离的径向渐变（解决正面块感）==========
      // 计算从球心到当前像素的距离，用于创建径向渐变效果
      float distanceFromCenter = length(v_position);
      
      // 可调参数：径向渐变的强度和范围
      // 第一个参数：渐变起始位置，推荐范围 0.3~0.7
      // 第二个参数：渐变结束位置，推荐范围 1.0~1.5
      // 当前设置：从0.5到1.2的平滑过渡
      float radialGradient = smoothstep(0.5, 1.2, distanceFromCenter);
      
      // 可调参数：径向亮度调制范围
      // 第一个值：中心区域亮度系数，推荐0.8~1.2
      // 第二个值：边缘区域亮度系数，推荐1.1~1.5
      // 当前设置：中心1.0，边缘1.3，创造从内到外的亮度提升
      baseColor *= mix(1.0, 1.3, radialGradient);
      
      // 添加基于视角的额外亮度调制
      vec3 viewDir = normalize(cameraPosition - v_position);
      float viewDot = max(dot(viewDir, v_normal), 0.0);
      
      // 可调参数：视角亮度增强
      // 推荐范围：0.1~0.3，数值越大正面越亮
      // 当前设置：0.2，适中的正面增亮效果
      baseColor += baseColor * viewDot * 0.2;

      // ========== Fresnel 边缘高光效果 ==========
      // viewDir 已在上面定义，这里直接使用
      float fresnel = 1.0 - max(dot(viewDir, v_normal), 0.0);
      
      // 可调参数：Fresnel 指数 pow(fresnel, 2.5)
      // 推荐范围：1.5~4.0
      // 数值越大，边缘高光越锐利；数值越小，边缘高光越柔和
      // 当前设置：2.5，适中的边缘锐利度
      fresnel = pow(fresnel, 2.5);

      // ========== 发光色设置 ==========
      // 可调参数：色相偏移 hue + 0.05
      // 推荐范围：0.02~0.1，控制发光色与主色的色相差异
      // 可调参数：饱和度系数 saturation * 0.9
      // 推荐范围：0.5~1.0，控制发光色的饱和度
      // 可调参数：明度提升 value + 0.1
      // 推荐范围：0.05~0.2，控制发光色比主色亮多少
      vec3 glowColor = hsv2rgb(vec3(hue + 0.1, saturation * 0.9, value + 0.1));

      // ========== 主色与边缘光混合 ==========
      // 可调参数：混合强度 fresnel * 0.8
      // 推荐范围：0.5~1.0
      // 数值越大，边缘发光效果越明显
      vec3 finalColor = mix(baseColor, glowColor, fresnel * 0.6);

      // ========== 全局亮度调整 ==========
      // 可调参数：亮度曲线 u_brightness * (0.7 + 0.9 * u_brightness)
      // 第一个系数：基础亮度系数，推荐0.6~0.8
      // 第二个系数：亮度增强系数，推荐0.7~1.2
      // 当前设置：0.7 + 0.9，适中的亮度对比
      finalColor *= u_brightness * (0.7 + 0.95 * u_brightness);

      // ========== 内部柔光效果 ==========
      float innerGlow = 1.0 - fresnel;
      // 可调参数：内部发光强度 u_brightness * 0.65
      // 推荐范围：0.3~1.0
      // 数值越大，内部发光越明显
      finalColor += glowColor * innerGlow * u_brightness * 0.65;

      // ========== 最终透明度 ==========
      // 可调参数：透明度 0.8
      // 推荐范围：0.7~1.0
      // 当前设置：0.8，略微透明，增加层次感
      float alpha = 1.0;
      gl_FragColor = vec4(finalColor, alpha);
    }
  `,
};

const canvasRef = ref();
let smoothIntensity = 0, smoothBrightness = 0, smoothScale = 1.0;

// [状态管理重构]：引入更鲁棒的状态管理，防止过渡动画被异常打断
let currentMode = props.mode;       // 当前已经稳定呈现的模式
let targetMode = props.mode;        // 用户期望切换到的目标模式
let isTransitioning = false;        // 是否正在进行颜色过渡
let transitionProgress = 1.0;       // 颜色过渡的进度（0.0 -> 1.0）

/**
 * generateSimulatedSpeech: 语音模拟函数
 * 可根据需要自定义语音模拟的复杂度和节奏。
 * 
 * 可调参数说明：
 * - fundamental: 基础频率，影响主要的语音节奏
 * - harmonic1/2: 谐波频率，增加语音的复杂性
 * - noise: 噪声成分，模拟语音的随机性
 * - pausePattern: 停顿模式，模拟说话时的间歇
 */
// @ts-ignore
function generateSimulatedSpeech(time: number): number { 
  // 可调参数：基础频率 2.2，推荐范围 1.5~3.0
  const fundamental = Math.sin(time * 2.2) * 0.5 + 0.5;
  // 可调参数：谐波频率 4.5 和 7.8，推荐范围 3.0~10.0
  const harmonic1 = Math.sin(time * 4.5) * 0.3;
  const harmonic2 = Math.sin(time * 7.8) * 0.2;
  // 可调参数：噪声频率 13.1 和 17.3，推荐范围 10.0~20.0
  const noise = Math.sin(time * 13.1) * Math.sin(time * 17.3) * 0.1;
  const combined = fundamental + harmonic1 + harmonic2 + noise;
  // 可调参数：停顿阈值 0.7，推荐范围 0.5~0.8，数值越大停顿越少
  const pausePattern = Math.sin(time * 0.7) > 0.7 ? 0.3 : 1.0;
  return Math.max(0, Math.min(1, combined * pausePattern));
}

const { onLoop } = useRenderLoop();

onLoop(({ elapsed }: { elapsed: number }) => {
  if (!canvasRef.value) return;
  shader.uniforms.u_time.value = elapsed;
  // const sim = generateSimulatedSpeech(elapsed);

  // ========== [状态管理重构] 状态切换逻辑 ==========
  // 1. 检测用户是否请求了新的模式
  if (targetMode !== props.mode) {
    targetMode = props.mode;
    // 2. 如果当前没有在进行过渡，则立即开始一个新的过渡
    if (!isTransitioning) {
      isTransitioning = true;
      transitionProgress = 0.0;
      // 将当前稳定状态的颜色作为"起始色"
      shader.uniforms.u_currentHueRange.value.copy(HUE_RANGES[currentMode]);
      // 将新模式的颜色作为"目标色"
      shader.uniforms.u_targetHueRange.value.copy(HUE_RANGES[targetMode]);
    }
  }

  // 3. 如果正在过渡，则更新过渡动画的进度
  if (isTransitioning) {
    /**
     * 可调参数：颜色过渡的速度控制
     * 实现"先快后慢"的自然过渡曲线
     * 
     * 调整建议：
     * - 如果希望整体过渡更快，可以将所有速度值乘以1.5~2.0
     * - 如果希望整体过渡更慢，可以将所有速度值乘以0.5~0.8
     * - 如果希望更平滑的过渡，可以减少速度差异（让三个阶段速度更接近）
     */
    let transitionSpeed = 0.01; // 初始速度，推荐范围：0.005~0.02
    
    // 实现先快后慢的过渡曲线
    if (transitionProgress < 0.3) {
      // 前30%：快速启动，推荐范围：0.015~0.04
      transitionSpeed = 0.025;
    } else if (transitionProgress < 0.7) {
      // 中间40%：正常速度，推荐范围：0.01~0.025
      transitionSpeed = 0.015;
    } else {
      // 后30%：缓慢收尾，推荐范围：0.005~0.015
      transitionSpeed = 0.008;
    }
    
    // 1) 更新 rawProgress（0->1）
    transitionProgress = Math.min(1.0, transitionProgress + transitionSpeed);

    // 2) 用 EaseInOutQuad 生成平滑进度
    //    f(t) = t<0.5 ? 2t² : -1+(4-2t)*t
    //    可以替换为其他缓动函数，如：
    //    - EaseInOutCubic: t<0.5 ? 4*t³ : 1-Math.pow(-2*t+2,3)/2
    //    - EaseInOutSine: -(Math.cos(Math.PI*t)-1)/2
    const easeInOutQuad = (t: number) =>
      t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

    // 3) 写入 shader，用于 fragmentShader 里直接 mix
    shader.uniforms.u_transitionProgress.value = easeInOutQuad(transitionProgress);

    // 4. 当过渡完成时
    if (transitionProgress >= 1.0) {
      transitionProgress = 1.0;
      isTransitioning = false;
      
      // 将当前稳定模式更新为我们刚刚过渡到的目标模式
      currentMode = targetMode;
      shader.uniforms.u_currentHueRange.value.copy(HUE_RANGES[currentMode]);

      // 5. 检查在过渡期间，用户是否又选择了其他模式（"排队"处理）
      if (currentMode !== props.mode) {
        // 如果是，则无缝衔接，立即开始下一段过渡
        targetMode = props.mode;
        isTransitioning = true;
        transitionProgress = 0.0;
        shader.uniforms.u_currentHueRange.value.copy(HUE_RANGES[currentMode]);
        shader.uniforms.u_targetHueRange.value.copy(HUE_RANGES[targetMode]);
      }
    }
  } else {
    // 当没有过渡时，确保 u_transitionProgress 为 1.0
    shader.uniforms.u_transitionProgress.value = 1.0;
  }

  // ========== 球体物理动画参数 ==========
  // [动画同步]：物理形变动画始终跟随用户的最新选择（targetMode），以保证操作的响应感
  let tI = 0, tS = 1.0;
  
  /**
   * 可调参数：呼吸动画频率
   * 数值越大，呼吸频率越高
   * 推荐范围：0.2 ~ 0.4
   * 当前值：0.3，较快的呼吸节奏
   */
  const breathingFrequency = 0.2;
  const b = Math.sin(elapsed * breathingFrequency) * 0.5 + 0.6;
  
  /**
   * 可调参数：亮度基线和变化幅度
   * 第一个数值：基础亮度 (推荐 0.5 ~ 0.7)
   * 第二个数值：呼吸亮度变化幅度 (推荐 0.1 ~ 0.2)
   * 当前设置：基础0.6，变化幅度0.15
   */
  const tB = 0.6 + b * 0.15;

  /**
   * 可调参数：不同状态的球体基础大小
   * 数值越大，球体越大
   * 推荐范围：0.8 ~ 1.3
   * 
   * 当前设置：
   * - idle: 0.9 (较小，体现内敛、安静)
   * - listening: 1.0 (标准大小，体现专注、接收)
   * - speaking: 1.15 (较大，体现活跃、表达)
   */
  const STATE_BASE_SCALES = {
    idle: 0.9,       // 空闲状态：较小，内敛
    listening: 1.0,  // 听语音状态：标准大小，专注
    speaking: 1.2,  // 说话状态：较大，活跃表达
  };

  if (targetMode === 'idle') {
    /**
     * 空闲状态参数：
     * 第一个系数：基础形变强度 (推荐 0.6 ~ 0.8)
     * 第二个系数：呼吸形变变化幅度 (推荐 0.2 ~ 0.4)
     * 当前设置：基础0.7，变化幅度0.3
     */
    tI = props.idleIntensity * (0.7 + b * 0.3);
    /**
     * 球体呼吸缩放幅度 (推荐 0.01 ~ 0.03)
     * 基础大小 + 呼吸变化
     * 当前设置：基础0.9，呼吸幅度0.04
     */
    tS = STATE_BASE_SCALES.idle + b * 0.04;
  } else if (targetMode === 'listening') {
    /**
     * 听语音状态参数：
     * 直接使用传入的listeningIntensity值，不再与模拟数据混合
     * 这样可以直接反映实际麦克风输入的强度
     */
    tI = props.listeningIntensity;
    /**
     * 缩放变化幅度
     * 基于传入的强度值计算适当的缩放
     */
    tS = STATE_BASE_SCALES.listening + (props.listeningIntensity - props.idleIntensity) * 0.2;
  } else if (targetMode === 'speaking') {
    /**
     * 说话状态参数：
     * 直接使用传入的speakingIntensity值，不再与模拟数据混合
     * 这样可以直接反映实际音频播放的强度
     */
    tI = props.speakingIntensity;
    /**
     * 缩放变化幅度
     * 基于传入的强度值计算适当的缩放
     */
    tS = STATE_BASE_SCALES.speaking + (props.speakingIntensity - props.idleIntensity) * 0.1;
  }

  /**
   * 可调参数：动画平滑系数
   * 数值越大，动画越跟手；数值越小，动画越柔和
   * 推荐范围：0.03 ~ 0.08
   * 
   * 当前设置：全部0.1，较快的响应速度
   * 如果希望更柔和的动画，可以降低到0.04~0.06
   * 如果希望更跟手的动画，可以提高到0.1~0.12
   */
  const smoothingIntensity = 0.1;   // 形变强度平滑系数
  const smoothingBrightness = 0.1;  // 亮度平滑系数
  const smoothingScale = 0.1;       // 缩放平滑系数
  
  smoothIntensity  += (tI - smoothIntensity)  * smoothingIntensity;
  smoothBrightness += (tB - smoothBrightness) * smoothingBrightness;
  smoothScale      += (tS - smoothScale)      * smoothingScale;

  shader.uniforms.u_intensity.value    = smoothIntensity;
  shader.uniforms.u_brightness.value   = smoothBrightness;
  shader.uniforms.u_sphereScale.value  = smoothScale;
});
</script>

<template>
  <div class="siri-wave-wrapper">
    <TresCanvas ref="canvasRef" :alpha="true" :antialias="true">
      <TresPerspectiveCamera :position="[0,0,4]" :fov="50" />
      <!-- 
        可调参数：环境光强度
        影响：整体亮度，数值越大整个场景越亮
        推荐范围：0.1 ~ 0.3
        当前值：0.2，适中的环境光
      -->
      <TresAmbientLight :intensity="0.2" />
      <!-- 
        可调参数：主光源强度和位置
        intensity：影响高光效果，推荐范围 0.2 ~ 0.4
        position：光源位置，当前[5,5,5]为右上前方光源
        可以调整为其他位置，如[0,5,5]为正上前方
      -->
      <TresDirectionalLight :position="[5,5,5]" :intensity="0.25" />
      <TresMesh>
        <!-- 
          可调参数：球体几何体设置
          第一个数值：球体半径，推荐范围 1.0 ~ 1.5
          第二个数值：细分度，影响球体表面的平滑程度
          - 128: 较低细分，性能好但可能有棱角
          - 256: 中等细分，平衡性能和质量 (当前设置)
          - 512: 高细分，最平滑但性能消耗大
          
          当前设置：半径1.0，细分度256
        -->
        <TresIcosahedronGeometry :args="[0.9,256]" />
        <TresShaderMaterial
          v-bind="shader"
          :transparent="false"
          :side="1"
          :depth-test="true"
          :depth-write="true"
        />
      </TresMesh>
    </TresCanvas>
  </div>
</template>

<style scoped>
.siri-wave-wrapper { 
  width: 100%; 
  height: 100%; 
  position: relative; 
}
</style> 
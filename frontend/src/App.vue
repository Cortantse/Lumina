<script setup lang="ts">
import { ref } from "vue";
import { invoke } from "@tauri-apps/api/core";
import AudioPlayback from "./components/AudioPlayback.vue";
import SystemAudioRecorder from "./components/SystemAudioRecorder.vue";
import ScreenshotManager from "./components/ScreenshotManager.vue";
import TitleBar from "./components/TitleBar.vue";

const greetMsg = ref("");
const name = ref("");

async function greet() {
  // Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
  greetMsg.value = await invoke("greet", { name: name.value });
}
</script>

<template>
  <TitleBar />
  <main class="container" data-tauri-drag-region>

    <!-- <div class="feature-section">
      <SystemAudioRecorder />
    </div> -->


    <AudioPlayback />


    <ScreenshotManager />

    <!-- <div class="feature-section">
      <h2>实时 VAD (语音活动检测)</h2>
      <RealTimeVad />
    </div>

    <div class="feature-section">
      <h2>VAD语音段回放</h2>
      <VadPlayback />
    </div> -->

  </main>
</template>

<style scoped>
.feature-section {
  margin: 20px 0;
  padding: 20px;
  background-color: transparent;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.siri-section {
  text-align: center;
}

.siri-controls {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 20px;
}

.siri-controls button.active {
  background-color: #007aff;
  color: white;
  border-color: #007aff;
}

.siri-container {
  height: 300px;
  width: 100%;
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.logos {
  margin: 30px 0;
}

.logo.vite:hover {
  filter: drop-shadow(0 0 2em #747bff);
}

.logo.vue:hover {
  filter: drop-shadow(0 0 2em #249b73);
}
</style>
<style>
:root {
  font-family: Inter, Avenir, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 24px;
  font-weight: 400;

  color: #0f0f0f;
  background-color: transparent;

  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  -webkit-text-size-adjust: 100%;
}

.container {
  margin: 0;
  padding-top: 42px; /* 增加顶部填充以适应标题栏高度 */
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: center;
  background-color: transparent;
}

.logo {
  height: 6em;
  padding: 1.5em;
  will-change: filter;
  transition: 0.75s;
}

.logo.tauri:hover {
  filter: drop-shadow(0 0 2em #24c8db);
}

.row {
  display: flex;
  justify-content: center;
}

a {
  font-weight: 500;
  color: #646cff;
  text-decoration: inherit;
}

a:hover {
  color: #535bf2;
}

h1 {
  text-align: center;
}

input,
button {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 0.6em 1.2em;
  font-size: 1em;
  font-weight: 500;
  font-family: inherit;
  color: #0f0f0f;
  background-color: transparent;
  transition: border-color 0.25s;
  box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
}

button {
  cursor: pointer;
}

button:hover {
  border-color: #396cd8;
}
button:active {
  border-color: #396cd8;
  background-color: transparent;
}

input,
button {
  outline: none;
}

#greet-input {
  margin-right: 5px;
}

@media (prefers-color-scheme: dark) {
  :root {
    color: #f6f6f6;
    background-color: transparent;
  }

  .feature-section {
    background-color: transparent;
  }

  a:hover {
    color: #24c8db;
  }

  input,
  button {
    color: #ffffff;
    background-color: transparent;
  }
  button:active {
    background-color: transparent;
  }
}
</style>
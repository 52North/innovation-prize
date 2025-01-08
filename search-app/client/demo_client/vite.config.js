import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import EnvironmentPlugin from 'vite-plugin-environment'

export default defineConfig({
  base: process.env.CLIENT_BASE_PATH || "/",
  resolve: {
    alias: {
      vue: '@vue/compat',
    },
  },
  plugins: [vue(), EnvironmentPlugin(['VUE_APP_BACKEND_API_URL']),],
});

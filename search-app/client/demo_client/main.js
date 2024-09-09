import Vue, { createApp } from '@vue/compat';
import { BootstrapVue, BootstrapVueIcons } from 'bootstrap-vue';
import App from './App.vue'
import 'bootstrap/dist/css/bootstrap.css';
import 'bootstrap-vue/dist/bootstrap-vue.css';


Vue.use(BootstrapVue);
Vue.use(BootstrapVueIcons);
const app = createApp(App);
app.mount('#app');

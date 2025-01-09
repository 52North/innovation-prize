<template>
	<!-- 
  <Navbar />
  -->
	<div class="app">
		<Sidebar />

		<Content>
			<div v-if="apiError" class="error-message">
				Unable to reach the API. Please check your connection.
			</div>
		</Content>

	</div>
</template>


<script>
import Navbar from "./components/Navbar.vue";
import Sidebar from "./components/Sidebar.vue";
import Content from "./components/Content.vue";
import axios from 'axios';
import Cookies from 'js-cookie';
import config from './config';

export default {
	components: {
		Navbar,
		Sidebar,
		Content,
	},
	name: 'App',
	async created() {
		await this.initializeSession();
	},
	methods: {
		async initializeSession() {
			const sessionCookie = Cookies.get('session_id');

			if (!sessionCookie) {

				try {
					const response = await axios.post(`${config.BACKEND_API_URL}/create_session`, {}, {
						withCredentials: true // This is important for cross-origin requests with credentials
					});
					console.log("Registered with ", response.data);

					// The server should set the cookie automatically
					// You don't need to manually set it using Cookies.set()

					this.apiError = false;
				} catch (error) {
					console.error('Error creating session:', error);
					this.apiError = true;
				}
			}
		}
	}
	};
</script>

<style lang="scss">
:root {
	--primary: #4ade80;
	--primary-alt: #22c55e;
	--grey: #64748b;
	--dark: #1e293b;
	--dark-alt: #334155;
	--light: #f1f5f9;
	--sidebar-width: 300px;
}

* {
	margin: 0;
	padding: 0;
	box-sizing: border-box;
	font-family: 'Fira sans', sans-serif;
}

body {
	background: var(--light);
}

button {
	cursor: pointer;
	appearance: none;
	border: none;
	outline: none;
	background: none;
}

.app {
	display: flex;

	main {
		flex: 1 1 0;
		padding: 2rem;

		@media (max-width: 1024px) {
			padding-left: 6rem;
		}
	}
}
</style>



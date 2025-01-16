# Demo Client based on VueJS

## Requirements:

Install Node.js version 18.3 or higher

## Installation

Intall the Vue-cli with 
```bash
npm install -g @vue/cli
```

Install the dependencies with
```bash
cd <.../search-app/client/demo_client>
npm install
```

Start the app with
```bash
npm run dev
```

The application will connect backend API http://localhost:8000 by default.
To connect a different backend, copy `sample.env` to `.env` and configure `VUE_APP_BACKEND_API_URL`.
If necessary to connect a backend which is not served samesite, make sure the backend [allows cross site requests](https://enable-cors.org/).
